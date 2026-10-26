"""自动化测试环境：强制连接隔离库 uams_test，绝不连接正式库（F-18）。"""
import os
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
_env = (BACKEND / ".env").read_text(encoding="utf-8")
_url = re.search(r"^DATABASE_URL=(.+)$", _env, re.M).group(1).strip()
_test_url = _url.rsplit("/", 1)[0] + "/uams_test?charset=utf8mb4"
os.environ["DATABASE_URL"] = _test_url

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def isolated_db_guard():
    """双重保险：测试库必须是 uams_test，并清理测试期间产生的审计日志。"""
    from sqlalchemy import text

    from app.db.session import engine

    with engine.connect() as conn:
        assert conn.execute(text("SELECT DATABASE()")).scalar() == "uams_test"
        baseline = conn.execute(
            text("SELECT COALESCE(MAX(id), 0) FROM operation_logs")
        ).scalar()
    yield
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM operation_logs WHERE id > :i"), {"i": baseline}
        )
