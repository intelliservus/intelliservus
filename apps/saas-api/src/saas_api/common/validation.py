from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

# pydantic 的 EmailStr 拒绝 .test 等保留域；class-validator 的 @IsEmail() 接受，需对齐。
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$")


def _validate_email(value: str) -> str:
    if not EMAIL_RE.match(value):
        raise ValueError("email must be a valid email address")
    return value


Email = Annotated[str, AfterValidator(_validate_email)]
