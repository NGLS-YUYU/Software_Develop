"""冒烟测试：验证基础设施可用。"""

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.db.session import engine
from app.main import app

client = TestClient(app)

EXPECTED_TABLES = {
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
}


def test_health_endpoint():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"


def test_rbac_tables_exist():
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= tables, f"缺少表: {EXPECTED_TABLES - tables}"


def test_tables_are_innodb_utf8mb4():
    """DATABASE.md §1 要求所有表 InnoDB + utf8mb4。"""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT TABLE_NAME, ENGINE, TABLE_COLLATION "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN :names"
            ).bindparams(names=tuple(EXPECTED_TABLES))
        ).all()
    assert len(rows) == len(EXPECTED_TABLES)
    for name, engine_name, collation in rows:
        assert engine_name == "InnoDB", f"{name} 引擎为 {engine_name}"
        assert collation.startswith("utf8mb4"), f"{name} 排序规则为 {collation}"


def test_user_check_constraints():
    """非法 user_type 必须被数据库拒绝。"""
    from sqlalchemy.exc import IntegrityError, OperationalError

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(
                text(
                    "INSERT INTO users (username, password_hash, real_name, user_type) "
                    "VALUES ('__ck_test__', 'x', '测试', 'INVALID_TYPE')"
                )
            )
            trans.rollback()
            raise AssertionError("CHECK 约束未生效：非法 user_type 被写入")
        except (IntegrityError, OperationalError):
            trans.rollback()  # 预期：被数据库拒绝
