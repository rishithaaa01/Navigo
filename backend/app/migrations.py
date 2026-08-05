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
        """Split SQL statements while respecting dollar-quoted strings."""
        statements = []
        current = []
        in_dollar_quote = False
        dollar_tag = None
        
        lines = sql.split('\n')
        for line in lines:
            stripped = line.strip()
            
            # Check for dollar quote tags
            if not in_dollar_quote:
                # Look for dollar quote start (e.g., $$, $func$, $body$)
                import re
                match = re.search(r'\$(\w*)\$', stripped)
                if match and 'LANGUAGE' not in stripped.upper():
                    in_dollar_quote = True
                    dollar_tag = match.group(0)
                    current.append(line)
                    continue
            else:
                # Look for matching dollar quote end
                if dollar_tag in stripped:
                    in_dollar_quote = False
                    dollar_tag = None
                    current.append(line)
                    continue
            
            current.append(line)
            
            # If we hit a semicolon outside of dollar quotes, that's a statement boundary
            if ';' in stripped and not in_dollar_quote:
                statement = '\n'.join(current).strip()
                if statement:
                    # Remove trailing semicolon
                    if statement.endswith(';'):
                        statement = statement[:-1].strip()
                    if statement:
                        statements.append(statement)
                current = []
        
        # Don't forget the last statement if there's no trailing semicolon
        if current:
            statement = '\n'.join(current).strip()
            if statement:
                if statement.endswith(';'):
                    statement = statement[:-1].strip()
                if statement:
                    statements.append(statement)
        
        return statements


async def run_migrations(pool: asyncpg.Pool, migrations_dir: Path) -> None:
    runner = MigrationRunner(pool, migrations_dir)
    await runner.run()
