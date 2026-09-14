"""用户数据访问（CLAUDE.md §11：Repository 只负责数据库访问）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.role import Role
from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        stmt = (
            select(User)
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .where(User.id == user_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_username(self, username: str) -> User | None:
        # 预加载角色与权限，避免登录后逐个懒加载（PRD §14：避免 N+1）
        stmt = (
            select(User)
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .where(User.username == username)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def save(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user
