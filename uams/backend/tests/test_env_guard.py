"""启动环境守卫单元测试（不连接正式库）。"""
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

import scripts.env_guard as guard
from scripts.env_guard import GuardError, MODE_DATABASES, read_base_url, target_url

BASE = make_url(
    "mysql+pymysql://user:p%40ss%3Aword@127.0.0.1:3306/uams?charset=utf8mb4"
)


def test_mode_database_mapping():
    assert MODE_DATABASES == {
        "production": "uams",
        "testing": "uams_test",
        "restore": "uams_restore_20261027",
    }


@pytest.mark.parametrize("mode", sorted(MODE_DATABASES))
def test_url_rebuild_changes_only_database(mode):
    url = target_url(mode, base_url=BASE)
    assert url.database == MODE_DATABASES[mode]
    assert url.drivername == BASE.drivername
    assert url.username == BASE.username
    assert url.password == BASE.password
    assert url.host == BASE.host and url.port == BASE.port
    assert url.query == BASE.query


def test_unknown_mode_rejected():
    with pytest.raises(GuardError) as exc:
        target_url("staging", base_url=BASE)
    assert exc.value.code == guard.EXIT_USAGE


def test_missing_env_file_does_not_fall_back(tmp_path: Path):
    with pytest.raises(GuardError) as exc:
        read_base_url(tmp_path / "missing.env")
    assert exc.value.code == guard.EXIT_CONFIG


def test_identity_mismatch_rejected(monkeypatch):
    monkeypatch.setattr(
        guard, "inspect_database", lambda url: ("uams", "e4f5a6b7c8d9", "e4f5a6b7c8d9")
    )
    with pytest.raises(GuardError) as exc:
        guard.validate("testing", base_url=BASE)
    assert exc.value.code == guard.EXIT_IDENTITY


def test_version_mismatch_rejected(monkeypatch):
    monkeypatch.setattr(
        guard, "inspect_database", lambda url: ("uams_test", "old", "head")
    )
    with pytest.raises(GuardError) as exc:
        guard.validate("testing", base_url=BASE)
    assert exc.value.code == guard.EXIT_VERSION
