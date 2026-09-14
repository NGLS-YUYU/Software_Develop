"""初始化 RBAC 基础数据：权限、角色、管理员账号。

幂等：可重复执行，不会产生重复记录（DATABASE.md §15）。

    python -m scripts.seed_rbac
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.role import Permission, Role, RoleCode, RolePermission, UserRole  # noqa: E402
from app.models.user import User, UserType  # noqa: E402

# --- 权限定义：(code, name, module) ---
PERMISSIONS: list[tuple[str, str, str]] = [
    # 基础数据
    ("college:read", "查看学院", "basic"),
    ("college:write", "维护学院", "basic"),
    ("major:read", "查看专业", "basic"),
    ("major:write", "维护专业", "basic"),
    ("class:read", "查看班级", "basic"),
    ("class:write", "维护班级", "basic"),
    ("classroom:read", "查看教室", "basic"),
    ("classroom:write", "维护教室", "basic"),
    # 人员
    ("student:read", "查看学生", "student"),
    ("student:write", "维护学生", "student"),
    ("student:export", "导出学生", "student"),
    ("teacher:read", "查看教师", "teacher"),
    ("teacher:write", "维护教师", "teacher"),
    # 课程
    ("course:read", "查看课程", "course"),
    ("course:write", "维护课程", "course"),
    ("curriculum:read", "查看培养方案", "curriculum"),
    ("curriculum:write", "维护培养方案", "curriculum"),
    # 开课排课
    ("teaching:read", "查看教学任务", "teaching"),
    ("teaching:write", "维护教学任务", "teaching"),
    ("schedule:read", "查看排课", "schedule"),
    ("schedule:write", "维护排课", "schedule"),
    # 选课
    ("selection:read", "查看选课", "selection"),
    ("selection:write", "选课/退课", "selection"),
    ("selection:manage", "管理选课", "selection"),
    # 成绩
    ("grade:read", "查看成绩", "grade"),
    ("grade:write", "录入成绩", "grade"),
    ("grade:submit", "提交成绩", "grade"),
    ("grade:approve", "审核成绩", "grade"),
    ("grade:export", "导出成绩", "grade"),
    # 考试
    ("exam:read", "查看考试", "exam"),
    ("exam:write", "维护考试", "exam"),
    # 评价
    ("evaluation:read", "查看评价", "evaluation"),
    ("evaluation:write", "提交评价", "evaluation"),
    ("evaluation:manage", "管理评价", "evaluation"),
    # 公告
    ("announcement:read", "查看公告", "announcement"),
    ("announcement:write", "发布公告", "announcement"),
    # 统计与审计
    ("statistics:read", "查看统计", "statistics"),
    ("audit:read", "查看操作日志", "audit"),
]

# --- 角色 → 权限（CLAUDE.md §9 权限隔离原则）---
ROLE_DEFS: dict[str, tuple[str, str, list[str]]] = {
    RoleCode.STUDENT: (
        "学生",
        "查看教学信息、选课、查看课表/成绩/考试",
        [
            "course:read",
            "curriculum:read",
            "schedule:read",
            "selection:read",
            "selection:write",
            "grade:read",
            "exam:read",
            "evaluation:read",
            "evaluation:write",
            "announcement:read",
        ],
    ),
    RoleCode.TEACHER: (
        "教师",
        "查看授课任务与学生名单、录入并提交成绩",
        [
            "course:read",
            "class:read",
            "student:read",
            "teaching:read",
            "schedule:read",
            "selection:read",
            "grade:read",
            "grade:write",
            "grade:submit",
            "exam:read",
            "evaluation:read",
            "announcement:read",
        ],
    ),
    RoleCode.ACADEMIC_ADMIN: (
        "教务管理员",
        "维护教学基础数据、开课、排课、考试、成绩审核",
        [code for code, _, _ in PERMISSIONS],  # 全部权限
    ),
}

# --- 初始账号：(username, real_name, user_type, role_code, password) ---
INITIAL_USERS: list[tuple[str, str, str, str, str]] = [
    ("admin", "系统管理员", UserType.ADMIN, RoleCode.ACADEMIC_ADMIN, "admin123"),
]


def seed_permissions(db: Session) -> dict[str, Permission]:
    existing = {p.code: p for p in db.execute(select(Permission)).scalars()}
    created = 0
    for code, name, module in PERMISSIONS:
        if code in existing:
            perm = existing[code]
            perm.name, perm.module = name, module  # 允许更新描述
        else:
            perm = Permission(code=code, name=name, module=module)
            db.add(perm)
            existing[code] = perm
            created += 1
    db.flush()
    print(f"  权限: 新增 {created}，共 {len(existing)}")
    return existing


def seed_roles(db: Session, perms: dict[str, Permission]) -> dict[str, Role]:
    existing = {r.code: r for r in db.execute(select(Role)).scalars()}
    created = 0
    for code, (name, desc, perm_codes) in ROLE_DEFS.items():
        if code in existing:
            role = existing[code]
        else:
            role = Role(code=code, name=name, description=desc, is_builtin=True)
            db.add(role)
            existing[code] = role
            created += 1
        db.flush()

        current = {
            rp.permission_id
            for rp in db.execute(
                select(RolePermission).where(RolePermission.role_id == role.id)
            ).scalars()
        }
        added = 0
        for pc in perm_codes:
            pid = perms[pc].id
            if pid not in current:
                db.add(RolePermission(role_id=role.id, permission_id=pid))
                added += 1
        db.flush()
        print(f"  角色 {code}: {'新建' if code not in existing or created else '已存在'}，新增授权 {added}")
    return existing


def seed_users(db: Session, roles: dict[str, Role]) -> None:
    for username, real_name, user_type, role_code, password in INITIAL_USERS:
        user = db.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()
        if user is None:
            user = User(
                username=username,
                password_hash=hash_password(password),
                real_name=real_name,
                user_type=user_type,
            )
            db.add(user)
            db.flush()
            print(f"  用户 {username}: 新建（初始密码 {password}）")
        else:
            print(f"  用户 {username}: 已存在，跳过（不覆盖密码）")

        role = roles[role_code]
        link = db.execute(
            select(UserRole).where(
                UserRole.user_id == user.id, UserRole.role_id == role.id
            )
        ).scalar_one_or_none()
        if link is None:
            db.add(UserRole(user_id=user.id, role_id=role.id))
            db.flush()


def main() -> None:
    print("初始化 RBAC 数据...")
    with SessionLocal() as db:
        perms = seed_permissions(db)
        roles = seed_roles(db, perms)
        seed_users(db, roles)
        db.commit()
    print("完成。")
    print("\n⚠ 初始密码仅供开发使用，正式环境必须立即修改。")


if __name__ == "__main__":
    main()
