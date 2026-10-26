"""邮箱规范化与格式校验（FIX-001）。

统一入口：所有学生/教师/用户新增、编辑、导入都先经过这里。
规则：
  - None / 空字符串 / 纯空格 -> None（数据库存 NULL）
  - 非空值先 strip，再校验格式和长度
  - 不做大小写改写；数据库 utf8mb4_0900_ai_ci 唯一索引本身大小写不敏感
"""

import re

EMAIL_MAX_LENGTH = 100

# 本地部分：允许常见的 RFC 5322 字符，点号不能出现在开头/结尾/连续出现。
_LOCAL_PART = (
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
)
# 域名标签：字母/数字开头结尾，中间允许连字符；最后一段 TLD 至少 2 个字母。
_DOMAIN_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_EMAIL_RE = re.compile(
    rf"^{_LOCAL_PART}@(?:{_DOMAIN_LABEL}\.)+[A-Za-z]{{2,}}$"
)


def normalize_email(value: str | None) -> str | None:
    """把可选的邮箱输入规范化为 ``str | None``。

    - ``None``、``""``、``"   "`` 一律返回 ``None``；
    - 非空字符串去除首尾空白后校验；
    - 格式或长度不合法时抛 ``ValueError``（Pydantic 会转成 422，
      Service 层会转成 400 业务错误）。
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("邮箱格式不正确")
    email = value.strip()
    if not email:
        return None
    if len(email) > EMAIL_MAX_LENGTH:
        raise ValueError(f"邮箱长度不能超过 {EMAIL_MAX_LENGTH} 个字符")
    if not _EMAIL_RE.fullmatch(email):
        raise ValueError("邮箱格式不正确")
    return email
