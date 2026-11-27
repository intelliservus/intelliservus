from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

from .request_context import RequestContext


class JsonLogger:
    """单行 JSON 结构化日志，字段与事实源 §13.2 对齐。"""

    def __init__(self, service: str, stream: TextIO | None = None) -> None:
        self._service = service
        self._stream = stream if stream is not None else sys.stdout

    def log(
        self,
        level: str,
        code: str,
        msg: str,
        context: RequestContext | None = None,
        **fields: Any,
    ) -> None:
        record: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": level,
            "service": self._service,
            "trace_id": context.trace_id if context else "",
            "span_id": context.span_id if context else "",
            "request_id": context.request_id if context else "",
            "tenant_id": context.tenant_id if context else None,
            "workspace_id": context.workspace_id if context else None,
            "user_id": context.user_id if context else None,
            "code": code,
            "msg": msg,
        }
        record.update(fields)
        self._stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._stream.flush()

    def info(
        self, code: str, msg: str, context: RequestContext | None = None, **fields: Any
    ) -> None:
        self.log("info", code, msg, context, **fields)

    def warn(
        self, code: str, msg: str, context: RequestContext | None = None, **fields: Any
    ) -> None:
        self.log("warn", code, msg, context, **fields)

    def error(
        self, code: str, msg: str, context: RequestContext | None = None, **fields: Any
    ) -> None:
        self.log("error", code, msg, context, **fields)
