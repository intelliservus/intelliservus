from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from ...common.validation import Email


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: str = Field(min_length=8)
    tenant_id: uuid.UUID | None = None
