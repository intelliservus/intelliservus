from __future__ import annotations

from typing import Any

STATUS_CODES: dict[int, str] = {
    400: "PARAM_INVALID",
    401: "AUTH_TOKEN_INVALID",
    403: "AUTH_FORBIDDEN",
    404: "RESOURCE_NOT_FOUND",
    409: "RESOURCE_CONFLICT",
    422: "SCHEMA_VALIDATION_FAILED",
    429: "RATE_LIMITED",
    503: "SYS_DEPENDENCY_UNAVAILABLE",
}


class AppError(Exception):
    """带错误码的业务异常，由统一异常处理器转成 §12.2 的错误信封。"""

    def __init__(self, status: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = {} if details is None else details
