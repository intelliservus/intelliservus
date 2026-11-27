from __future__ import annotations

import asyncio
import io
import json
from typing import Any

from psycopg_pool import AsyncConnectionPool

from saas_api.common.logging import JsonLogger
from saas_api.modules.support_adapter.repositories import OutboxEvent, OutboxRepository
from saas_api.modules.support_adapter.service import ProcessingError
from saas_api.worker import MAX_ATTEMPTS, Worker
from support import execute, fetch_one, seed_support_event, vendor_payload


class RecordingService:
    def __init__(self, outcome: str = "pending_mapping") -> None:
        self.outcome = outcome
        self.processed: list[str] = []

    async def process(self, event: OutboxEvent) -> str:
        self.processed.append(event.id)
        return self.outcome


class FailingService:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def process(self, event: OutboxEvent) -> str:
        self.calls += 1
        raise self.exc


def worker_of(
    pool: AsyncConnectionPool,
    service: Any,
    log_stream: io.StringIO,
    *,
    worker_id: str = "worker-test",
    **overrides: Any,
) -> Worker:
    return Worker(
        pool,
        service,
        JsonLogger("test", log_stream),
        worker_id=worker_id,
        **overrides,
    )


async def test_idle_worker_logs_backoff_and_stops(
    app_pool: AsyncConnectionPool, log_stream: io.StringIO, clean_db: None
) -> None:
    worker = worker_of(
        app_pool,
        RecordingService(),
        log_stream,
        poll_initial_seconds=0.01,
        poll_max_seconds=0.02,
    )
    stop = asyncio.Event()

    task = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(0.1)
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)

    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    idle = [record for record in records if record["code"] == "WORKER_IDLE"]
    assert idle
    assert idle[0]["delay_seconds"] == 0.02


async def test_concurrent_workers_do_not_double_process(
    app_pool: AsyncConnectionPool,
    admin_pool: AsyncConnectionPool,
    log_stream: io.StringIO,
    clean_db: None,
) -> None:
    await seed_support_event(app_pool, vendor_payload())
    await seed_support_event(app_pool, vendor_payload(id=13))
    service = RecordingService()

    first, second = (
        worker_of(app_pool, service, log_stream, worker_id="worker-a"),
        worker_of(app_pool, service, log_stream, worker_id="worker-b"),
    )

    results = await asyncio.gather(first.process_once(), second.process_once())

    assert results == [True, True]
    assert len(service.processed) == 2
    assert len(set(service.processed)) == 2
    completed = await fetch_one(
        admin_pool,
        "SELECT count(*) AS total FROM integration.outbox_events WHERE status = 'completed'",
    )
    assert completed == {"total": 2}


async def test_event_moves_to_dead_letter_after_max_attempts(
    app_pool: AsyncConnectionPool,
    admin_pool: AsyncConnectionPool,
    log_stream: io.StringIO,
    clean_db: None,
) -> None:
    event = await seed_support_event(app_pool, vendor_payload())
    service = FailingService(RuntimeError("boom"))
    worker = worker_of(
        app_pool,
        service,
        log_stream,
        backoff_seconds=(0.0, 0.0, 0.0, 0.0, 0.0),
        jitter_ratio=0.0,
    )

    for _ in range(MAX_ATTEMPTS):
        assert await worker.process_once() is True

    row = await fetch_one(
        admin_pool,
        "SELECT status, attempt, last_error, payload FROM integration.outbox_events",
    )
    assert row is not None
    assert row["status"] == "dead_letter"
    assert row["attempt"] == MAX_ATTEMPTS
    assert "boom" in row["last_error"]
    assert row["payload"]["support_event_id"] == event.payload["support_event_id"]
    assert service.calls == MAX_ATTEMPTS


async def test_permanent_error_goes_straight_to_dead_letter(
    app_pool: AsyncConnectionPool,
    admin_pool: AsyncConnectionPool,
    log_stream: io.StringIO,
    clean_db: None,
) -> None:
    await seed_support_event(app_pool, vendor_payload())
    worker = worker_of(
        app_pool, FailingService(ProcessingError("bad payload", permanent=True)), log_stream
    )

    assert await worker.process_once() is True

    row = await fetch_one(
        admin_pool, "SELECT status, attempt FROM integration.outbox_events"
    )
    assert row == {"status": "dead_letter", "attempt": 1}


async def test_stale_processing_events_are_reclaimed(
    app_pool: AsyncConnectionPool,
    admin_pool: AsyncConnectionPool,
    log_stream: io.StringIO,
    clean_db: None,
) -> None:
    await seed_support_event(app_pool, vendor_payload())
    async with app_pool.connection() as conn:
        async with conn.transaction():
            assert await OutboxRepository(conn).claim_one("stopped-worker") is not None
    await execute(
        admin_pool,
        "UPDATE integration.outbox_events SET locked_at = now() - interval '10 minutes'",
    )
    worker = worker_of(app_pool, RecordingService(), log_stream, lease_seconds=60)

    assert await worker.reclaim_stale() == 1

    row = await fetch_one(admin_pool, "SELECT status, locked_by FROM integration.outbox_events")
    assert row == {"status": "pending", "locked_by": None}
