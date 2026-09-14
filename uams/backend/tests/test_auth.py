"""认证与权限测试。

覆盖 CLAUDE.md §29 要求的正常/异常/权限/边界场景。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db.session import SessionLocal
from app.main import app
from app.models.role import Role, RoleCode, UserRole
from app.models.user import User, UserStatus, UserType

client = TestClient(app)
LOGIN = f"{settings.API_V1_PREFIX}/auth/login"
ME = f"{settings.API_V1_PREFIX}/auth/me"
CHANGE_PWD = f"{settings.API_V1_PREFIX}/auth/change-password"

TEST_USER = "__pytest_stu__"
TEST_PWD = "test123456"


@pytest.fixture
def student_user():
    """建一个学生账号，用完删除。"""
    with SessionLocal() as db:
        db.execute(delete(User).where(User.username == TEST_USER))
        db.commit()

        user = User(
            username=TEST_USER,
            password_hash=hash_password(TEST_PWD),
            real_name="测试学生",
            user_type=UserType.STUDENT,
        )
        db.add(user)
        db.flush()
        role = db.execute(
            select(Role).where(Role.code == RoleCode.STUDENT)
        ).scalar_one()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        uid = user.id

    yield uid

    with SessionLocal() as db:
        db.execute(delete(UserRole).where(UserRole.user_id == uid))
        db.execute(delete(User).where(User.id == uid))
        db.commit()


def login(username: str, password: str):
    return client.post(LOGIN, json={"username": username, "password": password})


# --- 密码哈希 ---


def test_password_hash_roundtrip():
    h = hash_password("abc123")
    assert h != "abc123"
    assert h.startswith("$2")
    assert verify_password("abc123", h)
    assert not verify_password("abc124", h)


def test_password_hash_is_salted():
    """相同密码两次哈希结果必须不同。"""
    assert hash_password("same") != hash_password("same")


def test_verify_rejects_malformed_hash():
    assert verify_password("x", "not-a-bcrypt-hash") is False


# --- 登录：正常场景 ---


def test_login_success(student_user):
    r = login(TEST_USER, TEST_PWD)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["token_type"] == "bearer"
    assert d["access_token"]
    assert d["user"]["username"] == TEST_USER
    assert RoleCode.STUDENT in d["roles"]
    assert "selection:write" in d["permissions"]
    # PRD §11.2：按角色跳转
    assert d["home_route"] == "/student/dashboard"


def test_login_returns_no_password(student_user):
    d = login(TEST_USER, TEST_PWD).json()
    assert "password" not in d["user"]
    assert "password_hash" not in d["user"]


# --- 登录：异常场景 ---


def test_login_wrong_password(student_user):
    r = login(TEST_USER, "wrong-password")
    assert r.status_code == 401
    assert r.json()["code"] == "AUTH_INVALID_CREDENTIALS"


def test_login_unknown_user():
    r = login("__no_such_user__", "whatever")
    assert r.status_code == 401
    # 不泄露"用户不存在"，与密码错误返回同一错误码
    assert r.json()["code"] == "AUTH_INVALID_CREDENTIALS"


def test_login_empty_username():
    r = login("", "x")
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_login_locks_after_max_failures(student_user):
    """CLAUDE.md §23：登录失败限制。"""
    for _ in range(settings.MAX_LOGIN_FAILURES):
        login(TEST_USER, "bad")

    r = login(TEST_USER, TEST_PWD)  # 即使密码正确也应被拒
    assert r.status_code == 423
    assert r.json()["code"] == "AUTH_ACCOUNT_LOCKED"


def test_login_disabled_account(student_user):
    with SessionLocal() as db:
        u = db.get(User, student_user)
        u.status = UserStatus.DISABLED
        db.commit()

    r = login(TEST_USER, TEST_PWD)
    assert r.status_code == 403
    assert r.json()["code"] == "AUTH_ACCOUNT_DISABLED"


# --- /me 与 token ---


def test_me_requires_token():
    r = client.get(ME)
    assert r.status_code == 401
    assert r.json()["code"] == "AUTH_INVALID_TOKEN"


def test_me_rejects_garbage_token():
    r = client.get(ME, headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_me_with_valid_token(student_user):
    token = login(TEST_USER, TEST_PWD).json()["access_token"]
    r = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    d = r.json()
    assert d["user"]["username"] == TEST_USER
    assert RoleCode.STUDENT in d["roles"]


# --- 权限隔离（CLAUDE.md §9）---


def test_student_lacks_admin_permissions(student_user):
    """学生不得拥有成绩审核、学生维护等教务权限。"""
    perms = set(login(TEST_USER, TEST_PWD).json()["permissions"])
    forbidden = {
        "grade:approve",
        "student:write",
        "course:write",
        "teaching:write",
        "audit:read",
    }
    assert not (perms & forbidden), f"学生不应拥有: {perms & forbidden}"


def test_admin_has_approve_permission():
    r = login("admin", "admin123")
    assert r.status_code == 200, "seed 脚本是否已执行？"
    d = r.json()
    assert "grade:approve" in d["permissions"]
    assert d["home_route"] == "/admin/dashboard"


# --- 改密 ---


def test_change_password_wrong_old(student_user):
    token = login(TEST_USER, TEST_PWD).json()["access_token"]
    r = client.post(
        CHANGE_PWD,
        json={"old_password": "wrong", "new_password": "newpass123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


def test_change_password_success(student_user):
    token = login(TEST_USER, TEST_PWD).json()["access_token"]
    r = client.post(
        CHANGE_PWD,
        json={"old_password": TEST_PWD, "new_password": "newpass123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204
    assert login(TEST_USER, TEST_PWD).status_code == 401       # 旧密码失效
    assert login(TEST_USER, "newpass123").status_code == 200   # 新密码可用
