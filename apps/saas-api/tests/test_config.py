from __future__ import annotations

import pytest

from saas_api.common.config import ConfigError, load_config

VALID = {
    "DATABASE_URL": "postgres://user:pass@localhost:5432/platform",
    "JWT_SECRET": "a" * 32,
    "ALLOWED_ORIGINS": "http://localhost:8080",
}


def test_parses_full_config() -> None:
    config = load_config(VALID)

    assert config.port == 3000
    assert config.allowed_origins == ["http://localhost:8080"]
    assert config.cookie_secure is True
    assert config.app_env == "development"


def test_missing_database_url() -> None:
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        load_config({**VALID, "DATABASE_URL": ""})


def test_short_jwt_secret() -> None:
    with pytest.raises(ConfigError, match="JWT_SECRET"):
        load_config({**VALID, "JWT_SECRET": "short"})


def test_missing_allowed_origins() -> None:
    env = {key: value for key, value in VALID.items() if key != "ALLOWED_ORIGINS"}

    with pytest.raises(ConfigError, match="ALLOWED_ORIGINS"):
        load_config(env)


def test_cookie_secure_false() -> None:
    config = load_config({**VALID, "COOKIE_SECURE": "false"})

    assert config.cookie_secure is False
