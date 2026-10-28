"""登录错误码、停用与锁定策略测试（uams_test）。"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.role import Role, RoleCode, UserRole
from app.models.user import User, UserStatus
from app.services.auth import AuthService


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _make_user(password: str = "GoodPass123", status: str = UserStatus.ACTIVE) -> int:
    username = f"PYTEST_LOGIN_{uuid4().hex[:8]}"
    with SessionLocal() as db:
        role = db.execute(
            select(Role).where(Role.code == RoleCode.STUDENT)
        ).scalar_one()
        user = User(
            username=username,
            password_hash=hash_password(password),
            real_name="pytest login",
            user_type="STUDENT",
            status=status,
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        return user.id


def _cleanup(uid: int) -> None:
    with SessionLocal() as db:
        db.execute(delete(UserRole).where(UserRole.user_id == uid))
        db.execute(delete(User).where(User.id == uid))
        db.commit()


def _login(client: TestClient, username: str, password: str):
    return client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )


def test_login_success(client):
    uid = _make_user()
    try:
        username = _username(uid)
        r = _login(client, username, "GoodPass123")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["access_token"]
        assert body["home_route"] == "/student/dashboard"
        assert body["roles"] == ["STUDENT"]
    finally:
        _cleanup(uid)


def test_wrong_password_and_unknown_user_share_response(client):
    uid = _make_user()
    try:
        wrong = _login(client, _username(uid), "wrong-password")
        unknown = _login(client, f"NO_SUCH_{uuid4().hex[:8]}", "whatever")
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json()["code"] == unknown.json()["code"] == "AUTH_INVALID_CREDENTIALS"
        assert wrong.json()["message"] == unknown.json()["message"]
    finally:
        _cleanup(uid)


def test_disabled_account(client):
    uid = _make_user(status=UserStatus.DISABLED)
    try:
        r = _login(client, _username(uid), "GoodPass123")
        assert r.status_code == 403, r.text
        assert r.json()["code"] == "AUTH_ACCOUNT_DISABLED"
    finally:
        _cleanup(uid)


def test_lockout_after_repeated_failures(client):
    uid = _make_user()
    try:
        username = _username(uid)
        for _ in range(settings.MAX_LOGIN_FAILURES - 1):
            r = _login(client, username, "bad")
            assert r.status_code == 401, r.text
            assert r.json()["code"] == "AUTH_INVALID_CREDENTIALS"
        # 触发锁定的当次立即返回锁定状态，并带剩余时间
        r = _login(client, username, "bad")
        assert r.status_code == 423, r.text
        body = r.json()
        assert body["code"] == "AUTH_ACCOUNT_LOCKED"
        assert 0 < body["retry_after_seconds"] <= settings.LOGIN_LOCK_MINUTES * 60
        assert body["locked_until"]
        # 锁定期间即使密码正确也拒绝
        r2 = _login(client, username, "GoodPass123")
        assert r2.status_code == 423
        with SessionLocal() as db:
            user = db.get(User, uid)
            assert user.status == UserStatus.LOCKED
            assert user.locked_until is not None
            assert user.failed_login_count == 0
    finally:
        _cleanup(uid)


def test_empty_credentials_are_validation_error(client):
    r = _login(client, "", "")
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_internal_error_returns_500(monkeypatch):
    def boom(self, username, password):
        raise RuntimeError("pytest forced failure")

    monkeypatch.setattr(AuthService, "authenticate", boom)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "whatever"},
        )
    assert r.status_code == 500


def _username(uid: int) -> str:
    with SessionLocal() as db:
        return db.get(User, uid).username
