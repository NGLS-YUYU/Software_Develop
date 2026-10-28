#!/usr/bin/env python3
"""UAMS 运行环境守卫。

职责：
- 从 backend/.env 读取基础数据库连接（只读取，不改写）；
- 按运行模式只替换数据库名，保留驱动、主机、端口、账号、密码、查询参数；
- 用真实连接执行 SELECT DATABASE()，确认与模式映射一致；
- 对比数据库 alembic_version 与项目 head，版本不一致时拒绝启动；
- ``exec`` 子命令把校验后的 DATABASE_URL 放入子进程环境后 exec 目标命令。

安全：
- 不在终端打印连接串、密码或 JWT；
- 不使用字符串切割拼 URL（使用 SQLAlchemy URL 解析/重建）；
- 任何配置缺失、连接失败、库名不符、版本不符都以非零码退出。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = BACKEND / ".env"

MODE_DATABASES: dict[str, str] = {
    "production": "uams",
    "testing": "uams_test",
    "restore": "uams_restore_20261027",
}

EXIT_CONFIG = 2
EXIT_VERSION = 3
EXIT_CONNECTION = 4
EXIT_IDENTITY = 5
EXIT_USAGE = 6


class GuardError(Exception):
    def __init__(self, message: str, code: int, info: dict[str, str] | None = None):
        super().__init__(message)
        self.code = code
        self.info = info


def _env_file_path(env_file: str | os.PathLike[str] | None = None) -> Path:
    if env_file:
        return Path(env_file)
    override = os.environ.get("UAMS_ENV_FILE")
    return Path(override) if override else DEFAULT_ENV_FILE


def read_base_url(env_file: str | os.PathLike[str] | None = None) -> URL:
    """从 .env 读取 DATABASE_URL；缺失时明确报错，绝不回退到内置默认值。"""
    path = _env_file_path(env_file)
    if not path.is_file():
        raise GuardError(f"未找到配置文件：{path}", EXIT_CONFIG)
    raw = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "DATABASE_URL":
            raw = value.strip().strip('"').strip("'")
            break
    if not raw:
        raise GuardError(f"{path} 中未配置 DATABASE_URL", EXIT_CONFIG)
    try:
        url = make_url(raw)
    except Exception as exc:  # noqa: BLE001
        raise GuardError(f"DATABASE_URL 格式非法：{type(exc).__name__}", EXIT_CONFIG)
    if not url.drivername.startswith("mysql"):
        raise GuardError("DATABASE_URL 必须使用 MySQL 驱动", EXIT_CONFIG)
    if not url.host or not url.username:
        raise GuardError("DATABASE_URL 缺少主机或用户名", EXIT_CONFIG)
    return url


def target_url(
    mode: str,
    *,
    base_url: URL | None = None,
    env_file: str | os.PathLike[str] | None = None,
) -> URL:
    """只替换数据库名，其余连接参数原样保留。"""
    if mode not in MODE_DATABASES:
        raise GuardError(f"未知运行环境：{mode}", EXIT_USAGE)
    base = base_url or read_base_url(env_file)
    if not base.database:
        raise GuardError("DATABASE_URL 缺少数据库名", EXIT_CONFIG)
    # URL.set() 会重新编码特殊字符，避免手工切割造成密码解析错误。
    return base.set(database=MODE_DATABASES[mode])


def inspect_database(url: URL) -> tuple[str, str, str]:
    """返回 (实际库名, 当前 alembic 版本, 项目 head)。"""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    try:
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "alembic"))
        heads = ScriptDirectory.from_config(cfg).get_heads()
    except Exception as exc:  # noqa: BLE001
        raise GuardError(f"读取 Alembic head 失败：{type(exc).__name__}", EXIT_CONFIG)
    if len(heads) != 1:
        raise GuardError(f"Alembic 存在 {len(heads)} 个 head，拒绝启动", EXIT_CONFIG)
    head = heads[0]

    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            actual = conn.execute(text("SELECT DATABASE()")).scalar()
            current = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
        engine.dispose()
    except Exception as exc:  # noqa: BLE001
        raise GuardError(
            f"数据库连接失败：{type(exc).__name__}: {str(exc).splitlines()[0][:180]}",
            EXIT_CONNECTION,
        )
    return str(actual or ""), str(current or "MISSING"), head


def validate(
    mode: str,
    *,
    base_url: URL | None = None,
    env_file: str | os.PathLike[str] | None = None,
) -> dict[str, str]:
    expected = MODE_DATABASES.get(mode)
    if expected is None:
        raise GuardError(f"未知运行环境：{mode}", EXIT_USAGE)
    url = target_url(mode, base_url=base_url, env_file=env_file)
    actual, current, head = inspect_database(url)
    info = {
        "mode": mode,
        "database": actual,
        "expected": expected,
        "current": current,
        "head": head,
    }
    if actual != expected:
        raise GuardError(
            f"数据库身份不符：模式 {mode} 要求 {expected}，实际连接 {actual}",
            EXIT_IDENTITY,
            info,
        )
    if current != head:
        raise GuardError(
            f"数据库版本不匹配：当前 {current}，目标 head {head}；请先单独申请并执行迁移",
            EXIT_VERSION,
            info,
        )
    return info


def _print_info(info: dict[str, str], match: int) -> None:
    print(
        "mode={mode} db={database} current={current} head={head} match={match}".format(
            match=match, **info
        )
    )


def cmd_check(args: argparse.Namespace) -> int:
    try:
        info = validate(args.mode, env_file=args.env_file)
    except GuardError as exc:
        # 输出已获得的元数据，便于启动器展示当前/目标版本；不输出连接串。
        if exc.info:
            _print_info(exc.info, 0)
        print(str(exc), file=sys.stderr)
        return exc.code
    _print_info(info, 1)
    return 0


def cmd_exec(args: argparse.Namespace) -> int:
    if not args.command:
        print("exec 缺少目标命令", file=sys.stderr)
        return EXIT_USAGE
    try:
        info = validate(args.mode, env_file=args.env_file)
        url = target_url(args.mode, env_file=args.env_file)
    except GuardError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code

    env = os.environ.copy()
    env["DATABASE_URL"] = url.render_as_string(hide_password=False)
    env["APP_ENV"] = info["mode"]
    env.pop("UAMS_ENV_FILE", None)
    # 不打印 URL；exec 后进程环境中的 DATABASE_URL 与已校验目标一致。
    os.execvpe(args.command[0], args.command, env)
    return 0  # pragma: no cover


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UAMS 运行环境守卫")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("mode", choices=sorted(MODE_DATABASES))
        p.add_argument("--env-file", default=None, help=argparse.SUPPRESS)

    check = sub.add_parser("check", help="校验环境与数据库")
    add_common(check)
    check.set_defaults(func=cmd_check)

    ex = sub.add_parser("exec", help="校验后以目标数据库环境执行命令")
    add_common(ex)
    ex.add_argument("command", nargs=argparse.REMAINDER)
    ex.set_defaults(func=cmd_exec)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = list(getattr(args, "command", None) or [])
    if command and command[0] == "--":
        command = command[1:]
    args.command = command
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
