"""Pydantic 邮箱字段类型（FIX-001）。

在请求模型入口统一把空字符串/纯空格转成 None，并校验格式。
Service 层仍会再规范化一次，确保直接调用 Service/导入时行为一致。
"""

from typing import Annotated

from pydantic import BeforeValidator

from app.core.email import normalize_email

EmailField = Annotated[str | None, BeforeValidator(normalize_email)]
