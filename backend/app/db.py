from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

from app.config import Settings
from app.migrations import run_migrations

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return

        # Only create database in local development
        # Render provides pre-created databases
        environment = getattr(self._settings, "environment", "local")
        if environment == "local":
            await self._ensure_database_exists_local()

        db_config = self._settings.db_config
        self._pool = await asyncpg.create_pool(
            host=db_config["host"],
            port=db_config["port"],
            user=db_config["user"],
            password=db_config["password"],
            database=db_config["database"],
            min_size=1,
            max_size=10,
        )
        migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
        await run_migrations(self._pool, migrations_dir)

    async def disconnect(self) -> None:
        if self._pool is None:
            return

        await self._pool.close()
        self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool has not been initialized.")
        return self._pool

    async def _ensure_database_exists_local(self) -> None:
        """Create database if it doesn't exist (local development only)."""
        db_config = self._settings.db_config
        try:
            # Connect to postgres database (always exists)
            connection = await asyncpg.connect(
                host=db_config["host"],
                port=db_config["port"],
                user=db_config["user"],
                password=db_config["password"],
                database="postgres",
            )

            try:
                # Check if database exists
                result = await connection.fetchval(
                    "SELECT 1 FROM pg_database WHERE datname = $1",
                    db_config["database"],
                )

                if not result:
                    # Create database if it doesn't exist
                    # Note: CREATE DATABASE cannot run inside a transaction
                    await connection.execute(
                        f'CREATE DATABASE "{db_config["database"]}"'
                    )
                    logger.info(
                        f"Created database: {db_config['database']}"
                    )
            finally:
                await connection.close()
        except Exception as e:
            logger.warning(
                f"Could not ensure database exists: {e}. "
                "Assuming database is already created (e.g., on Render)."
            )
