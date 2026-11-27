from __future__ import annotations

import asyncio
import random
import signal
import socket
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from psycopg_pool import AsyncConnectionPool

from .common.config import Settings, load_config
from .common.logging import JsonLogger
from .database.pool import create_pool
from .database.transaction import tenant_context
from .modules.support_adapter.mapping import UnmappedResolver
from .modules.support_adapter.repositories import OutboxEvent, OutboxRepository
from .modules.support_adapter.service import ProcessingError, SupportAdapterService

SERVICE_NAME = "saas-worker"
MAX_ATTEMPTS = 5
DEFAULT_BACKOFF_SECONDS = (2.0, 4.0, 8.0, 16.0, 32.0)


class Worker:
    def __init__(
        self,
        pool: AsyncConnectionPool,
        service: SupportAdapterService,
        logger: JsonLogger,
        *,
        worker_id: str,
        poll_initial_seconds: float = 0.05,
        poll_max_seconds: float = 5.0,
        backoff_seconds: Sequence[float] = DEFAULT_BACKOFF_SECONDS,
        jitter_ratio: float = 0.2,
        lease_seconds: int = 300,
    ) -> None:
        self._pool = pool
        self._service = service
        self._logger = logger
        self._worker_id = worker_id
        self._poll_initial = poll_initial_seconds
        self._poll_max = poll_max_seconds
        self._backoff = backoff_seconds
        self._jitter_ratio = jitter_ratio
        self._lease_seconds = lease_seconds

    async def reclaim_stale(self) -> int:
        async with tenant_context(self._pool, None) as conn:
            reclaimed = await OutboxRepository(conn).reclaim_stale(
                older_than_seconds=self._lease_seconds
            )
        if reclaimed:
            self._logger.warn(
                "WORKER_STALE_RECLAIMED",
                "reclaimed events left processing by a stopped worker",
                None,
                count=reclaimed,
            )
        return reclaimed

    async def process_once(self) -> bool:
        async with tenant_context(self._pool, None) as conn:
            event = await OutboxRepository(conn).claim_one(self._worker_id)
        if event is None:
            return False

        try:
            outcome = await self._service.process(event)
        except Exception as exc:  # noqa: BLE001 - 分类后写入重试或死信
            await self._record_failure(event, exc)
            return True

        async with tenant_context(self._pool, None) as conn:
            await OutboxRepository(conn).mark_completed(event.id)
        self._logger.info(
            "WORKER_EVENT_COMPLETED",
            "outbox event completed",
            None,
            event_id=event.id,
            event_type=event.event_type,
            outcome=outcome,
        )
        return True

    async def run(self, stop: asyncio.Event) -> None:
        delay = self._poll_initial
        while not stop.is_set():
            if await self.process_once():
                delay = self._poll_initial
                continue
            delay = min(delay * 2, self._poll_max)
            self._logger.info(
                "WORKER_IDLE",
                "no pending outbox events",
                None,
                delay_seconds=round(delay, 3),
            )
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except TimeoutError:
                pass

    async def _record_failure(self, event: OutboxEvent, exc: Exception) -> None:
        permanent = isinstance(exc, ProcessingError) and exc.permanent
        error = f"{type(exc).__name__}: {exc}"[:500]
        if permanent or event.attempt >= MAX_ATTEMPTS:
            async with tenant_context(self._pool, None) as conn:
                await OutboxRepository(conn).mark_dead_letter(event.id, error=error)
            self._logger.error(
                "WORKER_EVENT_DEAD_LETTER",
                "outbox event moved to dead letter",
                None,
                event_id=event.id,
                event_type=event.event_type,
                attempt=event.attempt,
                error=error,
            )
            return

        available_at = self._next_available_at(event.attempt)
        async with tenant_context(self._pool, None) as conn:
            await OutboxRepository(conn).mark_retry(
                event.id, available_at=available_at, error=error
            )
        self._logger.warn(
            "WORKER_EVENT_RETRY",
            "outbox event scheduled for retry",
            None,
            event_id=event.id,
            attempt=event.attempt,
            available_at=available_at.isoformat(),
            error=error,
        )

    def _next_available_at(self, attempt: int) -> datetime:
        base = self._backoff[min(attempt - 1, len(self._backoff) - 1)]
        jitter = base * random.uniform(-self._jitter_ratio, self._jitter_ratio)
        return datetime.now(UTC) + timedelta(seconds=max(0.0, base + jitter))


async def _run(settings: Settings, logger: JsonLogger, worker_id: str) -> None:
    pool = create_pool(settings.database_url)
    await pool.open()
    worker = Worker(
        pool,
        SupportAdapterService(pool, UnmappedResolver(), logger),
        logger,
        worker_id=worker_id,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        logger.info("WORKER_STARTED", "worker started", None, worker_id=worker_id)
        await worker.reclaim_stale()
        await worker.run(stop)
    finally:
        await pool.close()
        logger.info("WORKER_STOPPED", "worker stopped", None, worker_id=worker_id)


async def _check(settings: Settings) -> None:
    pool = create_pool(settings.database_url, min_size=1, max_size=1)
    await pool.open()
    try:
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
    finally:
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    settings = load_config()
    if "--check" in args:
        asyncio.run(_check(settings))
        return 0
    asyncio.run(_run(settings, JsonLogger(SERVICE_NAME), socket.gethostname()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
