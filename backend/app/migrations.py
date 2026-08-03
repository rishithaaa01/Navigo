from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import asyncpg


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    sql: str


class MigrationRunner:
    def __init__(self, pool: asyncpg.Pool, migrations_dir: Path) -> None:
        self._pool = pool
        self._migrations_dir = migrations_dir

    async def run(self) -> None:
        await self._ensure_migrations_table()
        applied_versions = await self._get_applied_versions()

        for migration in self._load_migrations():
            if migration.version in applied_versions:
                continue
            await self._apply_migration(migration)

    async def _ensure_migrations_table(self) -> None:
        query = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(32) NOT NULL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """

        async with self._pool.acquire() as connection:
            await connection.execute(query)

    async def _get_applied_versions(self) -> set[str]:
        query = "SELECT version FROM schema_migrations"

        async with self._pool.acquire() as connection:
            rows = await connection.fetch(query)
            return {str(row["version"]) for row in rows}

    def _load_migrations(self) -> list[Migration]:
        migrations: list[Migration] = []
        for path in sorted(self._migrations_dir.glob("*.sql")):
            version, _, name = path.stem.partition("_")
            migrations.append(
                Migration(
                    version=version,
                    name=name or path.stem,
                    sql=path.read_text(encoding="utf-8"),
                )
            )
        return migrations

    async def _apply_migration(self, migration: Migration) -> None:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                for statement in self._split_sql_statements(migration.sql):
                    await connection.execute(statement)
                await connection.execute(
                    """
                    INSERT INTO schema_migrations (version, name)
                    VALUES ($1, $2)
                    """,
                    migration.version,
                    migration.name,
                )

    def _split_sql_statements(self, sql: str) -> list[str]:
        statements = []
        for statement in sql.split(";"):
            cleaned = statement.strip()
            if cleaned:
                statements.append(cleaned)
        return statements


async def run_migrations(pool: asyncpg.Pool, migrations_dir: Path) -> None:
    runner = MigrationRunner(pool, migrations_dir)
    await runner.run()
