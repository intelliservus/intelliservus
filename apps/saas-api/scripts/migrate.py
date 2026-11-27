from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
VERSION_TABLE = "schema_migrations"
DOWN_MARKER = "-- Down Migration"


def _database_name(dsn: str) -> str:
    return urlparse(dsn).path.lstrip("/")


def _up_sql(text: str) -> str:
    index = text.find(DOWN_MARKER)
    return text if index == -1 else text[:index]


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    database = _database_name(dsn)
    if not database.startswith("platform") and os.environ.get("MIGRATE_ALLOW_NON_PLATFORM") != "1":
        print(f"refusing to migrate non-platform database: {database}", file=sys.stderr)
        return 2

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print("no migrations found", file=sys.stderr)
        return 2

    with psycopg.connect(dsn) as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
              version    text PRIMARY KEY,
              applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        conn.commit()

        applied = {
            row[0] for row in conn.execute(f"SELECT version FROM {VERSION_TABLE}").fetchall()
        }

        for path in files:
            version = path.stem
            if version in applied:
                print(f"skip  {version}")
                continue
            with conn.transaction():
                # psycopg 只接受 LiteralString 形式的原生 SQL；迁移文件内容来自仓库，可信任
                conn.execute(_up_sql(path.read_text(encoding="utf-8")))  # pyright: ignore[reportArgumentType, reportCallIssue]
                conn.execute(
                    f"INSERT INTO {VERSION_TABLE} (version) VALUES (%s)",
                    (version,),
                )
            print(f"apply {version}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
