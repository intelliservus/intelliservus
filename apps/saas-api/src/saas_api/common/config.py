from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, field_validator

SERVICE_NAME = "saas-api"

AppEnv = Literal["development", "test", "production"]


class ConfigError(RuntimeError):
    """启动配置不合法。"""


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_env: AppEnv = "development"
    port: int = 3000
    database_url: str
    jwt_secret: str
    allowed_origins: list[str]
    cookie_secure: bool = True
    webhook_secrets: list[str] = []
    webhook_max_body_bytes: int = 1_048_576
    webhook_timestamp_tolerance_seconds: int = 300

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_length(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return value

    @field_validator("allowed_origins")
    @classmethod
    def _origins_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("ALLOWED_ORIGINS is required")
        return value


def load_config(env: Mapping[str, str] | None = None) -> Settings:
    source = dict(os.environ if env is None else env)
    problems: list[str] = []

    database_url = source.get("DATABASE_URL", "")
    if not database_url:
        problems.append("DATABASE_URL is required")

    jwt_secret = source.get("JWT_SECRET", "")
    if not jwt_secret:
        problems.append("JWT_SECRET is required")
    elif len(jwt_secret) < 32:
        problems.append("JWT_SECRET must be at least 32 characters")

    raw_origins = source.get("ALLOWED_ORIGINS", "")
    origins = [item.strip() for item in raw_origins.split(",") if item.strip()]
    if not origins:
        problems.append("ALLOWED_ORIGINS is required")

    raw_secrets = source.get("CHATWOOT_WEBHOOK_SECRETS", "")
    webhook_secrets = [item.strip() for item in raw_secrets.split(",") if item.strip()]

    webhook_max_body_bytes = _positive_int(source, "WEBHOOK_MAX_BODY_BYTES", 1_048_576, problems)
    webhook_tolerance = _positive_int(
        source, "WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS", 300, problems
    )

    if problems:
        raise ConfigError("Invalid configuration: " + "; ".join(problems))

    return Settings(
        app_env=cast(AppEnv, source.get("APP_ENV", "development")),
        port=int(source.get("PORT", "3000")),
        database_url=database_url,
        jwt_secret=jwt_secret,
        allowed_origins=origins,
        cookie_secure=source.get("COOKIE_SECURE", "true") == "true",
        webhook_secrets=webhook_secrets,
        webhook_max_body_bytes=webhook_max_body_bytes,
        webhook_timestamp_tolerance_seconds=webhook_tolerance,
    )


def _positive_int(
    source: Mapping[str, str], key: str, default: int, problems: list[str]
) -> int:
    raw = source.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        problems.append(f"{key} must be an integer")
        return default
    if value <= 0:
        problems.append(f"{key} must be positive")
        return default
    return value
