# Design Document: MySQL to PostgreSQL Migration

## Overview

### Purpose

This design specifies the technical approach for migrating the Navigo backend from MySQL to PostgreSQL. The migration enables deployment on Render's free PostgreSQL tier while maintaining complete functional compatibility with the existing system.

### Scope

The migration encompasses:
- Replacing the aiomysql driver with asyncpg for PostgreSQL connectivity
- Converting database configuration to support PostgreSQL connection parameters
- Translating MySQL-specific SQL syntax to PostgreSQL equivalents in schema migrations
- Updating query parameterization from MySQL's `%s` format to PostgreSQL's `$1, $2, ...` format
- Modifying auto-increment ID retrieval patterns to use PostgreSQL's `RETURNING` clause
- Ensuring zero API contract changes for frontend compatibility
- Providing deployment documentation for Render and local PostgreSQL setup

### Goals

1. **Zero Downtime Migration Path**: Enable smooth transition from MySQL to PostgreSQL
2. **Functional Equivalence**: Preserve all existing application behavior
3. **API Compatibility**: Maintain exact API response schemas
4. **Render Deployment**: Successfully deploy on Render's managed PostgreSQL service
5. **Local Development**: Support PostgreSQL for local development and testing

### Non-Goals

- Data migration from existing MySQL instances (this migration assumes new PostgreSQL databases)
- Performance optimization beyond maintaining current performance characteristics
- Schema redesign or database normalization improvements
- Addition of new features or functionality


## Architecture

### Current Architecture (MySQL)

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Application                     │
├─────────────────────────────────────────────────────────────┤
│  AuthService  │  CommunityService  │  MappingService        │
├─────────────────────────────────────────────────────────────┤
│                    Database Class                            │
│              (aiomysql.Pool management)                      │
├─────────────────────────────────────────────────────────────┤
│                   MigrationRunner                            │
│          (Executes SQL migration files)                      │
├─────────────────────────────────────────────────────────────┤
│                     aiomysql Driver                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
                      MySQL Database
```

### Target Architecture (PostgreSQL)

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Application                     │
├─────────────────────────────────────────────────────────────┤
│  AuthService  │  CommunityService  │  MappingService        │
│      (Updated query parameterization: $1, $2, ...)          │
├─────────────────────────────────────────────────────────────┤
│                    Database Class                            │
│              (asyncpg.Pool management)                       │
├─────────────────────────────────────────────────────────────┤
│                   MigrationRunner                            │
│     (PostgreSQL-compatible SQL, asyncpg transactions)        │
├─────────────────────────────────────────────────────────────┤
│                     asyncpg Driver                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
                   PostgreSQL Database
```

### Key Architectural Changes

1. **Driver Layer**: Replace aiomysql with asyncpg
2. **Connection Management**: Adapt pool creation and connection acquisition to asyncpg API
3. **Query Execution**: Update cursor-based patterns to asyncpg's connection-based API
4. **Transaction Handling**: Use asyncpg's transaction context managers
5. **Result Handling**: Replace DictCursor with asyncpg's Record objects


## Components and Interfaces

### 1. Database Connection Management (`app/db.py`)

#### Current Implementation (MySQL)
```python
class Database:
    async def connect(self) -> None:
        await self._ensure_database_exists()  # Creates DB if missing
        self._pool = await aiomysql.create_pool(
            host=..., port=..., user=..., password=..., db=...,
            minsize=1, maxsize=10, autocommit=True
        )
```

#### Target Implementation (PostgreSQL)
```python
class Database:
    async def connect(self) -> None:
        # Skip database creation on Render (pre-provisioned)
        # Only attempt creation in local development
        if self._settings.environment == "local":
            await self._ensure_database_exists_local()
        
        self._pool = await asyncpg.create_pool(
            host=..., port=..., user=..., password=..., database=...,
            min_size=1, max_size=10
        )
```

#### Key Changes
- Remove or conditionally execute `_ensure_database_exists()` (Render provides pre-created databases)
- Replace `aiomysql.create_pool()` with `asyncpg.create_pool()`
- Parameter mapping: `db` → `database`, `minsize` → `min_size`, `maxsize` → `max_size`
- asyncpg does not have autocommit mode; transactions are explicit
- Connection URL parsing: Support `DATABASE_URL` environment variable

#### Interface
```python
class Database:
    def __init__(self, settings: Settings) -> None: ...
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    
    @property
    def pool(self) -> asyncpg.Pool: ...
```


### 2. Configuration Management (`app/config.py`)

#### Current Implementation (MySQL)
```python
class Settings(BaseSettings):
    mysql_host: str
    mysql_port: int = 3306
    mysql_user: str
    mysql_password: str
    mysql_database: str
```

#### Target Implementation (PostgreSQL)
```python
class Settings(BaseSettings):
    database_url: Optional[str] = None  # For Render deployment
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str
    postgres_password: str
    postgres_database: str
    environment: str = "local"  # local, production
    
    @property
    def db_host(self) -> str:
        return self._parse_db_url_component("host") or self.postgres_host
    
    @property
    def db_port(self) -> int:
        return self._parse_db_url_component("port") or self.postgres_port
    
    # Similar properties for user, password, database
```

#### Key Changes
- Add `database_url` field for Render's `DATABASE_URL` environment variable
- Rename `mysql_*` fields to `postgres_*` (or generic `database_*`)
- Support both connection URL and individual parameters
- Parse `postgresql://user:password@host:port/database` format
- Default port: 5432 (PostgreSQL) instead of 3306 (MySQL)
- Add `environment` field to control database creation behavior

#### Connection URL Parsing
```python
from urllib.parse import urlparse

def parse_database_url(url: str) -> dict:
    parsed = urlparse(url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": parsed.username,
        "password": parsed.password,
        "database": parsed.path.lstrip("/")
    }
```


### 3. Migration Runner (`app/migrations.py`)

#### Current Implementation (MySQL)
```python
async def _apply_migration(self, migration: Migration) -> None:
    async with self._pool.acquire() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("START TRANSACTION")
            for statement in self._split_sql_statements(migration.sql):
                await cursor.execute(statement)
            await cursor.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                (migration.version, migration.name)
            )
            await connection.commit()
```

#### Target Implementation (PostgreSQL)
```python
async def _apply_migration(self, migration: Migration) -> None:
    async with self._pool.acquire() as connection:
        async with connection.transaction():
            for statement in self._split_sql_statements(migration.sql):
                await connection.execute(statement)
            await connection.execute(
                "INSERT INTO schema_migrations (version, name) VALUES ($1, $2)",
                migration.version, migration.name
            )
```

#### Key Changes
- Replace cursor-based API with connection-based API (asyncpg pattern)
- Use `connection.transaction()` context manager instead of explicit START/COMMIT
- Replace `%s` with `$1, $2` in parameterized queries
- Pass parameters as separate arguments instead of tuple
- Transaction automatically rolls back on exception

#### Schema Migrations Table (PostgreSQL)
```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(32) NOT NULL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Note: Remove `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4` clauses


### 4. Service Layer Query Updates

#### AuthService (`app/services/auth_service.py`)

**Query Pattern Changes:**

1. **User Signup - ID Retrieval**
```python
# Current (MySQL)
await cursor.execute(
    "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s)",
    (request.full_name, request.email, password_hash)
)
user_id = cursor.lastrowid

# Target (PostgreSQL)
user_id = await connection.fetchval(
    "INSERT INTO users (full_name, email, password_hash) VALUES ($1, $2, $3) RETURNING id",
    request.full_name, request.email, password_hash
)
```

2. **User Lookup - DictCursor Replacement**
```python
# Current (MySQL)
async with connection.cursor(DictCursor) as cursor:
    await cursor.execute("SELECT id, full_name, email FROM users WHERE id = %s", (user_id,))
    user_row = await cursor.fetchone()

# Target (PostgreSQL)
user_row = await connection.fetchrow(
    "SELECT id, full_name, email FROM users WHERE id = $1",
    user_id
)
# Access: user_row["id"], user_row["full_name"], etc.
```

#### CommunityService (`app/services/community_service.py`)

**Query Pattern Changes:**

1. **Upsert Operations (ON DUPLICATE KEY UPDATE → ON CONFLICT)**
```sql
-- Current (MySQL)
INSERT INTO favorite_places (user_id, place_name, address, latitude, longitude)
VALUES (%s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    place_name = VALUES(place_name),
    address = VALUES(address)

-- Target (PostgreSQL)
INSERT INTO favorite_places (user_id, place_name, address, latitude, longitude)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (user_id, latitude, longitude) DO UPDATE SET
    place_name = EXCLUDED.place_name,
    address = EXCLUDED.address
```

2. **Dynamic IN Clause Parameterization**
```python
# Current (MySQL)
placeholders = ", ".join(["%s"] * len(segment_keys))
query = f"SELECT ... FROM ... WHERE segment_key IN ({placeholders})"
await cursor.execute(query, tuple(segment_keys))

# Target (PostgreSQL)
placeholders = ", ".join([f"${i+1}" for i in range(len(segment_keys))])
query = f"SELECT ... FROM ... WHERE segment_key IN ({placeholders})"
await connection.fetch(query, *segment_keys)
```

3. **Auto-increment ID Retrieval**
```python
# Current (MySQL)
await cursor.execute("INSERT INTO safety_comments (...) VALUES (%s, ...)", (...))
comment_id = cursor.lastrowid

# Target (PostgreSQL)
comment_id = await connection.fetchval(
    "INSERT INTO safety_comments (...) VALUES ($1, ...) RETURNING id",
    ...
)
```


## Data Models

### Schema Migration Conversions

#### 1. Users Table

**MySQL Schema:**
```sql
CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**PostgreSQL Schema:**
```sql
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Conversion Rules Applied:**
- `BIGINT UNSIGNED NOT NULL AUTO_INCREMENT` → `BIGSERIAL`
- Remove `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`

#### 2. Place Safety Ratings Table

**MySQL Schema:**
```sql
CREATE TABLE IF NOT EXISTS place_safety_ratings (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    rating_value TINYINT UNSIGNED NOT NULL,
    -- other columns
    CONSTRAINT fk_place_safety_ratings_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**PostgreSQL Schema:**
```sql
CREATE TABLE IF NOT EXISTS place_safety_ratings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL CHECK (user_id >= 0),
    rating_value SMALLINT NOT NULL CHECK (rating_value >= 0 AND rating_value <= 255),
    -- other columns
    CONSTRAINT fk_place_safety_ratings_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

**Conversion Rules Applied:**
- `BIGINT UNSIGNED` → `BIGINT` + `CHECK (column >= 0)`
- `TINYINT UNSIGNED` → `SMALLINT` + `CHECK (column >= 0 AND column <= 255)`
- Remove `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`


#### 3. Road Segment Safety Scores Table

**MySQL Schema:**
```sql
CREATE TABLE IF NOT EXISTS road_segment_safety_scores (
    segment_key VARCHAR(120) NOT NULL PRIMARY KEY,
    normalized_score DECIMAL(5, 4) NOT NULL,
    rating_count INT UNSIGNED NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**PostgreSQL Schema:**
```sql
CREATE TABLE IF NOT EXISTS road_segment_safety_scores (
    segment_key VARCHAR(120) NOT NULL PRIMARY KEY,
    normalized_score DECIMAL(5, 4) NOT NULL,
    rating_count INTEGER NOT NULL DEFAULT 0 CHECK (rating_count >= 0),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Trigger to emulate ON UPDATE CURRENT_TIMESTAMP
CREATE OR REPLACE FUNCTION update_road_segment_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_road_segment_updated_at
BEFORE UPDATE ON road_segment_safety_scores
FOR EACH ROW
EXECUTE FUNCTION update_road_segment_timestamp();
```

**Conversion Rules Applied:**
- `INT UNSIGNED` → `INTEGER` + `CHECK (column >= 0)`
- `ON UPDATE CURRENT_TIMESTAMP` → Use trigger (PostgreSQL does not support this clause)
- Remove `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`

#### 4. Data Type Mapping Reference

| MySQL Type | PostgreSQL Type | Notes |
|------------|----------------|-------|
| `BIGINT UNSIGNED` | `BIGINT` + `CHECK (col >= 0)` | Or use `BIGSERIAL` for auto-increment |
| `INT UNSIGNED` | `INTEGER` + `CHECK (col >= 0)` | |
| `TINYINT UNSIGNED` | `SMALLINT` + `CHECK (col >= 0 AND col <= 255)` | |
| `DECIMAL(M,N)` | `DECIMAL(M,N)` or `NUMERIC(M,N)` | Identical |
| `VARCHAR(N)` | `VARCHAR(N)` or `TEXT` | Identical |
| `TEXT` | `TEXT` | Identical |
| `TIMESTAMP` | `TIMESTAMP` | Identical |
| `AUTO_INCREMENT` | `SERIAL` or `BIGSERIAL` | PostgreSQL sequence-based |


## Error Handling

### Connection Errors

**Scenario**: PostgreSQL connection fails on startup

**Handling Strategy**:
```python
async def connect(self) -> None:
    try:
        if self._settings.database_url:
            self._pool = await asyncpg.create_pool(self._settings.database_url)
        else:
            self._pool = await asyncpg.create_pool(
                host=self._settings.db_host,
                port=self._settings.db_port,
                user=self._settings.db_user,
                password=self._settings.db_password,
                database=self._settings.db_database,
                min_size=1,
                max_size=10
            )
    except asyncpg.InvalidPasswordError:
        raise RuntimeError("Database authentication failed. Check credentials.")
    except asyncpg.InvalidCatalogNameError:
        raise RuntimeError(f"Database '{self._settings.db_database}' does not exist.")
    except Exception as e:
        raise RuntimeError(f"Database connection failed: {e}")
```

### Migration Errors

**Scenario**: Migration SQL contains syntax errors

**Handling Strategy**:
- Use `connection.transaction()` to ensure automatic rollback
- Log the failed migration version and statement
- Do not record migration in `schema_migrations` table
- Re-raise exception to prevent application startup

```python
async def _apply_migration(self, migration: Migration) -> None:
    try:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                for statement in self._split_sql_statements(migration.sql):
                    await connection.execute(statement)
                await connection.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES ($1, $2)",
                    migration.version, migration.name
                )
    except Exception as e:
        logger.error(f"Migration {migration.version} failed: {e}")
        raise
```

### Query Execution Errors

**Scenario**: Parameterized query has mismatched parameter count

**Example Error**:
```
asyncpg.exceptions.InvalidSQLStatementNameError: 
prepared statement has 2 parameters but 3 were supplied
```

**Prevention**:
- Count parameters in SQL string and validate against arguments
- Use helper function to generate correct `$N` sequences for dynamic queries
- Add validation in development/testing

**Scenario**: Foreign key constraint violation

**Handling Strategy**:
```python
try:
    await connection.execute(...)
except asyncpg.ForeignKeyViolationError as e:
    raise CommunityServiceError("Referenced user does not exist.")
except asyncpg.UniqueViolationError as e:
    raise CommunityServiceError("Duplicate entry.")
```


## Testing Strategy

Since this is an infrastructure migration rather than a new feature with algorithmic logic, property-based testing is not applicable. The testing strategy focuses on **functional equivalence testing** and **integration testing** to ensure the PostgreSQL implementation behaves identically to the MySQL implementation.

### Test Categories

#### 1. Unit Tests (Example-Based)

**Purpose**: Verify individual database operations work correctly with PostgreSQL

**Test Cases**:

1. **User Authentication**
   - Test user signup with valid data → returns user ID and auth token
   - Test user signup with duplicate email → raises error
   - Test user login with correct credentials → returns auth token
   - Test user login with incorrect password → raises error
   - Test user lookup by ID → returns user object or None

2. **Favorite Places**
   - Test adding favorite place → returns place ID
   - Test adding duplicate favorite (same user, lat/lng) → updates existing
   - Test listing favorites → returns all user favorites ordered by created_at
   - Test removing favorite → deletes successfully
   - Test getting specific favorite → returns place or None

3. **Safety Ratings**
   - Test adding place rating → updates safety summary
   - Test calculating place safety summary → returns correct normalized score
   - Test adding road segment rating → updates segment scores
   - Test calculating road safety summary → averages segment scores correctly

4. **Comments**
   - Test adding comment → returns comment ID and "just now" timestamp
   - Test listing comments by target → returns comments in descending order
   - Test listing user comments → returns user's comments with location data
   - Test listing nearby comments → returns comments within radius

#### 2. Integration Tests

**Purpose**: Verify end-to-end database operations against real PostgreSQL instance

**Setup**:
```python
import pytest
import asyncpg

@pytest.fixture
async def db_pool():
    pool = await asyncpg.create_pool(
        host="localhost", port=5432,
        user="test_user", password="test_pass",
        database="navigo_test"
    )
    yield pool
    await pool.close()

@pytest.fixture
async def clean_database(db_pool):
    async with db_pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE users, favorite_places, ... CASCADE")
```

**Test Cases**:
- Complete signup → login → add favorite → add rating workflow
- Verify foreign key constraints (e.g., deleting user cascades to favorites)
- Verify unique constraints (e.g., duplicate email rejection)
- Verify transaction rollback on error


#### 3. Migration Tests

**Purpose**: Verify schema migrations execute successfully on PostgreSQL

**Test Cases**:
1. Apply migrations to empty PostgreSQL database → all tables created
2. Re-run migrations → already-applied migrations skipped
3. Verify schema_migrations table tracks applied versions
4. Inject failing migration → transaction rolls back, no partial state

**Example Test**:
```python
async def test_migrations_create_schema(db_pool):
    from app.migrations import run_migrations
    from pathlib import Path
    
    migrations_dir = Path(__file__).parent / "migrations"
    await run_migrations(db_pool, migrations_dir)
    
    async with db_pool.acquire() as conn:
        # Verify tables exist
        result = await conn.fetch("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        table_names = {row["table_name"] for row in result}
        
        assert "users" in table_names
        assert "favorite_places" in table_names
        assert "place_safety_ratings" in table_names
        # ... etc
```

#### 4. API Contract Tests

**Purpose**: Ensure API responses remain identical before and after migration

**Approach**: Compare JSON responses from MySQL-backed API vs PostgreSQL-backed API

**Test Cases**:
1. Signup response schema matches exactly
2. Login response schema matches exactly
3. Favorite places list response matches exactly
4. Safety summary response matches exactly (normalized score, badge, label)
5. Comments list response matches exactly (timestamps formatted identically)

**Example Test**:
```python
async def test_signup_response_schema(client):
    response = await client.post("/auth/signup", json={
        "full_name": "Test User",
        "email": "test@example.com",
        "password": "SecurePass123"
    })
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify schema
    assert "access_token" in data
    assert "token_type" in data
    assert data["token_type"] == "bearer"
    assert "user" in data
    assert "id" in data["user"]
    assert isinstance(data["user"]["id"], int)
    assert "full_name" in data["user"]
    assert "email" in data["user"]
```

#### 5. Data Precision Tests

**Purpose**: Verify numeric precision is preserved (coordinates, ratings)

**Test Cases**:
- Insert coordinate (latitude=40.7127837, longitude=-74.0059413) → retrieve exact values
- Calculate average rating from [0, 1, 2] → verify normalized_score = 0.5
- Verify DECIMAL(10,7) precision preserved in PostgreSQL


#### 6. Performance Baseline Tests

**Purpose**: Ensure PostgreSQL performance is comparable to MySQL

**Test Cases**:
- Benchmark query execution times for common operations
- Verify connection pool efficiently manages connections
- Test concurrent request handling (simulate multiple users)

**Acceptance Criteria**:
- No operation should be >2x slower than MySQL equivalent
- Connection pool should maintain 1-10 concurrent connections
- No connection leaks under load

### Test Environment Setup

#### Local PostgreSQL (Docker Compose)

```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: navigo_user
      POSTGRES_PASSWORD: navigo_pass
      POSTGRES_DB: navigo_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

#### Test Database Configuration

```python
# .env.test
DATABASE_URL=postgresql://navigo_user:navigo_pass@localhost:5432/navigo_test
ENVIRONMENT=test
```

### Test Execution Strategy

1. **Pre-Deployment Testing**
   - Run full test suite against local PostgreSQL
   - Verify all tests pass before deploying to Render

2. **Smoke Testing on Render**
   - Deploy to Render staging environment
   - Execute critical path tests (signup, login, add favorite, add rating)
   - Verify migrations applied successfully

3. **Production Deployment**
   - Deploy to production Render environment
   - Monitor error logs for 24 hours
   - Roll back if error rate exceeds baseline

### Success Criteria

- All unit tests pass (100% success rate)
- All integration tests pass (100% success rate)
- API contract tests confirm identical responses
- No data precision loss in coordinate or rating calculations
- Performance within acceptable range (< 2x slower)
- Successful deployment to Render with zero downtime


## Implementation Details

### Phase 1: Update Dependencies

**File**: `backend/requirements.txt`

**Changes**:
```diff
- aiomysql==0.2.0
- PyMySQL==1.1.0
+ asyncpg==0.29.0
```

### Phase 2: Update Configuration

**File**: `backend/app/config.py`

**Implementation**:
```python
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import urlparse
from typing import Optional

class Settings(BaseSettings):
    # Database configuration
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    postgres_database: str = Field(alias="POSTGRES_DATABASE")
    
    # Environment
    environment: str = Field(default="local", alias="ENVIRONMENT")
    
    # Other settings (GraphHopper, JWT, cache) remain unchanged
    
    @computed_field
    @property
    def db_config(self) -> dict:
        """Parse database configuration from URL or individual fields."""
        if self.database_url:
            parsed = urlparse(self.database_url)
            return {
                "host": parsed.hostname,
                "port": parsed.port or 5432,
                "user": parsed.username,
                "password": parsed.password,
                "database": parsed.path.lstrip("/")
            }
        return {
            "host": self.postgres_host,
            "port": self.postgres_port,
            "user": self.postgres_user,
            "password": self.postgres_password,
            "database": self.postgres_database
        }
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
```


### Phase 3: Update Database Connection

**File**: `backend/app/db.py`

**Implementation**:
```python
from __future__ import annotations

from pathlib import Path
import asyncpg
import logging

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
        if self._settings.environment == "local":
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
                database="postgres"
            )
            
            # Check if database exists
            exists = await connection.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                db_config["database"]
            )
            
            if not exists:
                await connection.execute(
                    f'CREATE DATABASE "{db_config["database"]}"'
                )
                logger.info(f"Created database: {db_config['database']}")
            
            await connection.close()
        except Exception as e:
            logger.warning(f"Could not ensure database exists: {e}")
```


### Phase 4: Update Migration Runner

**File**: `backend/app/migrations.py`

**Implementation**:
```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging

import asyncpg

logger = logging.getLogger(__name__)

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
        logger.info(f"Applying migration: {migration.version} - {migration.name}")
        
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                for statement in self._split_sql_statements(migration.sql):
                    await connection.execute(statement)
                await connection.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES ($1, $2)",
                    migration.version, migration.name
                )
        
        logger.info(f"Migration {migration.version} applied successfully")

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
```


### Phase 5: Convert Schema Migrations

**File**: `backend/migrations/001_create_users_table.sql`

**PostgreSQL Version**:
```sql
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**File**: `backend/migrations/002_add_community_safety_tables.sql`

**PostgreSQL Version**:
```sql
CREATE TABLE IF NOT EXISTS place_safety_ratings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL CHECK (user_id >= 0),
    place_name VARCHAR(255) NOT NULL,
    address VARCHAR(500) NOT NULL,
    latitude DECIMAL(10, 7) NOT NULL,
    longitude DECIMAL(10, 7) NOT NULL,
    rating_value SMALLINT NOT NULL CHECK (rating_value >= 0 AND rating_value <= 255),
    comment TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_place_safety_ratings_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_place_safety_location ON place_safety_ratings (latitude, longitude);
CREATE INDEX idx_place_safety_user ON place_safety_ratings (user_id);

CREATE TABLE IF NOT EXISTS road_segment_ratings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL CHECK (user_id >= 0),
    segment_key VARCHAR(120) NOT NULL,
    start_latitude DECIMAL(10, 7) NOT NULL,
    start_longitude DECIMAL(10, 7) NOT NULL,
    end_latitude DECIMAL(10, 7) NOT NULL,
    end_longitude DECIMAL(10, 7) NOT NULL,
    rating_value SMALLINT NOT NULL CHECK (rating_value >= 0 AND rating_value <= 255),
    comment TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_road_segment_ratings_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_road_segment_key ON road_segment_ratings (segment_key);
CREATE INDEX idx_road_segment_user ON road_segment_ratings (user_id);

CREATE TABLE IF NOT EXISTS road_segment_safety_scores (
    segment_key VARCHAR(120) NOT NULL PRIMARY KEY,
    start_latitude DECIMAL(10, 7) NOT NULL,
    start_longitude DECIMAL(10, 7) NOT NULL,
    end_latitude DECIMAL(10, 7) NOT NULL,
    end_longitude DECIMAL(10, 7) NOT NULL,
    normalized_score DECIMAL(5, 4) NOT NULL,
    rating_count INTEGER NOT NULL DEFAULT 0 CHECK (rating_count >= 0),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_road_segment_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_road_segment_updated_at
BEFORE UPDATE ON road_segment_safety_scores
FOR EACH ROW
EXECUTE FUNCTION update_road_segment_timestamp();

CREATE TABLE IF NOT EXISTS favorite_places (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL CHECK (user_id >= 0),
    place_name VARCHAR(255) NOT NULL,
    address VARCHAR(500) NOT NULL,
    latitude DECIMAL(10, 7) NOT NULL,
    longitude DECIMAL(10, 7) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_favorite_places_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,
    UNIQUE (user_id, latitude, longitude)
);

CREATE INDEX idx_favorite_places_user ON favorite_places (user_id);

CREATE TABLE IF NOT EXISTS safety_comments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL CHECK (user_id >= 0),
    target_type VARCHAR(20) NOT NULL,
    target_key VARCHAR(191) NOT NULL,
    place_name VARCHAR(255) NULL,
    address VARCHAR(500) NULL,
    latitude DECIMAL(10, 7) NULL,
    longitude DECIMAL(10, 7) NULL,
    comment TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_safety_comments_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_safety_comments_target ON safety_comments (target_type, target_key);
CREATE INDEX idx_safety_comments_user ON safety_comments (user_id);
```


### Phase 6: Update AuthService Queries

**File**: `backend/app/services/auth_service.py`

**Key Changes**:

1. **Remove DictCursor import**: `from aiomysql import DictCursor` → remove
2. **Update all query parameterization**: `%s` → `$1, $2, ...`
3. **Replace cursor-based API with connection-based API**
4. **Use RETURNING clause for ID retrieval**

**Updated signup method**:
```python
async def signup(self, request: SignupRequest) -> AuthResponse:
    existing_user = await self._get_user_by_email(request.email)
    if existing_user is not None:
        raise AuthServiceError("An account with this email already exists.")

    password_hash = hash_password(request.password)
    insert_query = """
    INSERT INTO users (full_name, email, password_hash)
    VALUES ($1, $2, $3)
    RETURNING id
    """

    async with self._database.pool.acquire() as connection:
        user_id = await connection.fetchval(
            insert_query,
            request.full_name.strip(),
            request.email.lower(),
            password_hash
        )

    user = UserResponse(
        id=int(user_id),
        full_name=request.full_name.strip(),
        email=request.email.lower(),
    )
    return self._build_auth_response(user)
```

**Updated get_user_by_id method**:
```python
async def get_user_by_id(self, user_id: int) -> UserResponse | None:
    select_query = """
    SELECT id, full_name, email
    FROM users
    WHERE id = $1
    LIMIT 1
    """

    async with self._database.pool.acquire() as connection:
        user_row = await connection.fetchrow(select_query, user_id)

    if user_row is None:
        return None

    return UserResponse(
        id=int(user_row["id"]),
        full_name=user_row["full_name"],
        email=user_row["email"],
    )
```

**Updated _get_user_by_email method**:
```python
async def _get_user_by_email(self, email: str) -> dict | None:
    select_query = """
    SELECT id, full_name, email, password_hash
    FROM users
    WHERE email = $1
    LIMIT 1
    """

    async with self._database.pool.acquire() as connection:
        row = await connection.fetchrow(select_query, email.lower())
        return dict(row) if row else None
```


### Phase 7: Update CommunityService Queries

**File**: `backend/app/services/community_service.py`

**Key Changes**:

1. **Update all query parameterization**: `%s` → `$1, $2, ...`
2. **Convert ON DUPLICATE KEY UPDATE to ON CONFLICT**
3. **Use RETURNING clause for ID retrieval**
4. **Fix dynamic IN clause generation**

**Updated add_favorite_place method**:
```python
async def add_favorite_place(
    self,
    user: UserResponse,
    request: FavoritePlaceRequest,
) -> FavoritePlaceResponse:
    insert_query = """
    INSERT INTO favorite_places (user_id, place_name, address, latitude, longitude)
    VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (user_id, latitude, longitude) DO UPDATE SET
        place_name = EXCLUDED.place_name,
        address = EXCLUDED.address
    """

    async with self._database.pool.acquire() as connection:
        await connection.execute(
            insert_query,
            user.id,
            request.place_name,
            request.address,
            request.latitude,
            request.longitude,
        )

    favorite = await self.get_favorite_place(
        user.id,
        request.latitude,
        request.longitude,
    )
    if favorite is None:
        raise CommunityServiceError("Unable to save favorite place.")
    return favorite
```

**Updated list_favorite_places method**:
```python
async def list_favorite_places(self, user_id: int) -> list[FavoritePlaceResponse]:
    query = """
    SELECT id, place_name, address, latitude, longitude
    FROM favorite_places
    WHERE user_id = $1
    ORDER BY created_at DESC
    """

    async with self._database.pool.acquire() as connection:
        rows = await connection.fetch(query, user_id)

    return [
        FavoritePlaceResponse(
            id=int(row["id"]),
            place_name=row["place_name"],
            address=row["address"],
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
        )
        for row in rows
    ]
```

**Updated add_comment method with RETURNING**:
```python
async def add_comment(
    self,
    user: UserResponse,
    request: SafetyCommentRequest,
) -> SafetyCommentResponse:
    query = """
    INSERT INTO safety_comments (
        user_id, target_type, target_key, place_name, address,
        latitude, longitude, comment
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    RETURNING id
    """

    async with self._database.pool.acquire() as connection:
        comment_id = await connection.fetchval(
            query,
            user.id,
            request.target_type,
            request.target_key,
            request.place_name,
            request.address,
            request.latitude,
            request.longitude,
            request.comment.strip(),
        )

    return SafetyCommentResponse(
        id=int(comment_id),
        user_name=user.full_name,
        target_type=request.target_type,
        target_key=request.target_key,
        comment=request.comment.strip(),
        created_at="just now",
    )
```


**Updated get_road_safety_summary method (dynamic IN clause)**:
```python
async def get_road_safety_summary(
    self,
    route_points: list[Coordinates],
) -> SafetySummaryResponse:
    segments = self._segments_from_points(route_points)
    if not segments:
        return self._build_summary(0, 0)

    segment_keys = [segment["segment_key"] for segment in segments]
    
    # Generate PostgreSQL placeholders: $1, $2, $3, ...
    placeholders = ", ".join([f"${i+1}" for i in range(len(segment_keys))])
    query = f"""
    SELECT segment_key, normalized_score, rating_count
    FROM road_segment_safety_scores
    WHERE segment_key IN ({placeholders})
    """

    async with self._database.pool.acquire() as connection:
        rows = await connection.fetch(query, *segment_keys)

    if not rows:
        return self._build_summary(0, 0)

    weighted_score = 0.0
    total_ratings = 0
    matched_segments = 0
    for row in rows:
        weighted_score += float(row["normalized_score"])
        total_ratings += int(row["rating_count"])
        matched_segments += 1

    return self._build_summary(weighted_score / matched_segments, total_ratings)
```

**Updated _refresh_segment_scores method**:
```python
async def _refresh_segment_scores(
    self,
    connection,  # asyncpg connection
    segments: list[dict[str, Coordinates | str]],
) -> None:
    processed_keys: set[str] = set()
    for segment in segments:
        segment_key = str(segment["segment_key"])
        if segment_key in processed_keys:
            continue
        processed_keys.add(segment_key)

        aggregate = await connection.fetchrow(
            """
            SELECT AVG(rating_value / 2.0) AS normalized_score, COUNT(*) AS rating_count
            FROM road_segment_ratings
            WHERE segment_key = $1
            """,
            segment_key,
        )
        normalized_score = float(aggregate["normalized_score"] or 0)
        rating_count = int(aggregate["rating_count"] or 0)
        start = segment["start"]
        end = segment["end"]

        await connection.execute(
            """
            INSERT INTO road_segment_safety_scores (
                segment_key, start_latitude, start_longitude,
                end_latitude, end_longitude, normalized_score, rating_count
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (segment_key) DO UPDATE SET
                normalized_score = EXCLUDED.normalized_score,
                rating_count = EXCLUDED.rating_count,
                updated_at = CURRENT_TIMESTAMP
            """,
            segment_key,
            start.latitude,
            start.longitude,
            end.latitude,
            end.longitude,
            normalized_score,
            rating_count,
        )
```

**Updated add_road_rating method (transaction handling)**:
```python
async def add_road_rating(
    self,
    user: UserResponse,
    request: RoadSafetyRatingRequest,
) -> SafetySummaryResponse:
    segments = self._segments_from_points(request.route_points)
    if not segments:
        raise CommunityServiceError("Route must contain at least one segment.")

    insert_query = """
    INSERT INTO road_segment_ratings (
        user_id, segment_key, start_latitude, start_longitude,
        end_latitude, end_longitude, rating_value, comment
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    """

    async with self._database.pool.acquire() as connection:
        async with connection.transaction():
            for segment in segments:
                await connection.execute(
                    insert_query,
                    user.id,
                    segment["segment_key"],
                    segment["start"].latitude,
                    segment["start"].longitude,
                    segment["end"].latitude,
                    segment["end"].longitude,
                    self._rating_to_score(request.rating),
                    request.comment,
                )

            await self._refresh_segment_scores(connection, segments)

    return await self.get_road_safety_summary(request.route_points)
```


## Deployment Guide

### Local Development Setup

#### 1. Install PostgreSQL

**Option A: Using Docker (Recommended)**
```bash
# Create docker-compose.yml in project root
docker-compose up -d postgres
```

**docker-compose.yml**:
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: navigo_user
      POSTGRES_PASSWORD: navigo_pass
      POSTGRES_DB: navigo_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

**Option B: Native Installation**
- macOS: `brew install postgresql@15`
- Ubuntu: `sudo apt-get install postgresql-15`
- Windows: Download from [postgresql.org](https://www.postgresql.org/download/windows/)

#### 2. Update Environment Variables

**Create/update `.env` file**:
```bash
# Database Configuration (PostgreSQL)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=navigo_user
POSTGRES_PASSWORD=navigo_pass
POSTGRES_DATABASE=navigo_db
ENVIRONMENT=local

# Or use DATABASE_URL
# DATABASE_URL=postgresql://navigo_user:navigo_pass@localhost:5432/navigo_db

# GraphHopper API
GRAPHHOPPER_API_KEY=your_api_key_here

# JWT Configuration
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Cache Configuration
SEARCH_CACHE_TTL_SECONDS=300
ROUTE_CACHE_TTL_SECONDS=120
```

#### 3. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

#### 4. Run Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Verify Database Initialization**:
- Application will automatically create database (if in local mode)
- Migrations will run on startup
- Check logs for migration application


### Render Deployment Setup

#### 1. Create PostgreSQL Database on Render

1. Log in to [Render Dashboard](https://dashboard.render.com/)
2. Click "New +" → "PostgreSQL"
3. Configure database:
   - **Name**: `navigo-db`
   - **Database**: `navigo_db`
   - **User**: `navigo_user`
   - **Region**: Select closest to your users
   - **Plan**: Free (or paid for production)
4. Click "Create Database"
5. Wait for provisioning (2-3 minutes)
6. Copy the **Internal Database URL** from the dashboard

**Internal Database URL format**:
```
postgresql://navigo_user:password@postgres-xyz.render.com/navigo_db
```

#### 2. Create Web Service on Render

1. Click "New +" → "Web Service"
2. Connect your GitHub repository
3. Configure service:
   - **Name**: `navigo-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free (or paid for production)

#### 3. Configure Environment Variables

In the Render dashboard for your web service, add the following environment variables:

| Key | Value | Notes |
|-----|-------|-------|
| `DATABASE_URL` | (Paste Internal Database URL) | From PostgreSQL database |
| `ENVIRONMENT` | `production` | Disables local database creation |
| `GRAPHHOPPER_API_KEY` | (Your API key) | |
| `JWT_SECRET_KEY` | (Generate strong secret) | Use `openssl rand -hex 32` |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | 24 hours |
| `SEARCH_CACHE_TTL_SECONDS` | `300` | 5 minutes |
| `ROUTE_CACHE_TTL_SECONDS` | `120` | 2 minutes |

**Generate JWT Secret**:
```bash
openssl rand -hex 32
```

#### 4. Deploy Application

1. Click "Create Web Service"
2. Render will automatically:
   - Clone repository
   - Install dependencies
   - Start application
   - Run migrations on first connection

**Monitor Deployment**:
- Check "Logs" tab for deployment progress
- Look for migration success messages
- Verify application starts without errors

#### 5. Verify Deployment

**Test API Health**:
```bash
curl https://navigo-backend.onrender.com/health
```

**Test User Signup**:
```bash
curl -X POST https://navigo-backend.onrender.com/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Test User",
    "email": "test@example.com",
    "password": "SecurePassword123"
  }'
```

**Expected Response**:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "full_name": "Test User",
    "email": "test@example.com"
  }
}
```


### Migration Verification Checklist

After deployment, verify the following:

- [ ] **Database Connection**: Application starts without connection errors
- [ ] **Schema Migrations**: All migrations applied successfully (check logs)
- [ ] **User Signup**: Can create new user and receive auth token
- [ ] **User Login**: Can authenticate with correct credentials
- [ ] **Favorite Places**: Can add, list, and remove favorites
- [ ] **Place Ratings**: Can rate places and view safety summaries
- [ ] **Road Ratings**: Can rate routes and view aggregated scores
- [ ] **Comments**: Can add and retrieve comments
- [ ] **API Responses**: All endpoints return expected JSON structure
- [ ] **Error Handling**: Invalid requests return appropriate error messages

### Troubleshooting

#### Connection Failed: "Database does not exist"

**Issue**: Application trying to connect to non-existent database

**Solution**:
- On Render: Database is pre-created, check `DATABASE_URL` is correct
- Locally: Ensure `ENVIRONMENT=local` to enable database creation

#### Migration Failed: "Syntax error near..."

**Issue**: PostgreSQL-incompatible SQL syntax

**Solution**:
- Review migration file for MySQL-specific syntax
- Check for: `ENGINE=InnoDB`, `CHARSET`, `AUTO_INCREMENT`, `%s` parameters
- Convert to PostgreSQL equivalents

#### Error: "Too many parameters"

**Issue**: Parameter count mismatch between SQL placeholders and arguments

**Solution**:
- Count `$N` placeholders in query
- Ensure matching number of arguments passed
- For dynamic IN clauses, verify placeholder generation

#### Connection Pool Exhausted

**Issue**: All 10 connections in use, new requests waiting

**Solution**:
- Verify connections are being released (use `async with pool.acquire()`)
- Check for long-running queries blocking connections
- Consider increasing `max_size` in pool configuration

### Rollback Plan

If deployment fails or critical issues arise:

1. **Revert Render Deployment**:
   - Go to Render dashboard → Deploys tab
   - Click "Rollback" on previous working deployment

2. **Switch Back to MySQL** (if needed):
   - Revert code changes in repository
   - Update environment variables to MySQL settings
   - Redeploy application

3. **Investigate Logs**:
   - Download Render logs: Dashboard → Logs → Download
   - Check for error patterns
   - Identify root cause before re-attempting migration


## Implementation Checklist

### Code Changes

- [ ] **Dependencies** (`requirements.txt`)
  - [ ] Remove `aiomysql==0.2.0`
  - [ ] Remove `PyMySQL==1.1.0`
  - [ ] Add `asyncpg==0.29.0`

- [ ] **Configuration** (`app/config.py`)
  - [ ] Add `database_url` field
  - [ ] Add `postgres_*` fields (host, port, user, password, database)
  - [ ] Add `environment` field
  - [ ] Add `db_config` computed property
  - [ ] Implement URL parsing logic

- [ ] **Database Connection** (`app/db.py`)
  - [ ] Replace `aiomysql` imports with `asyncpg`
  - [ ] Update `connect()` method to use `asyncpg.create_pool()`
  - [ ] Add conditional database creation (`_ensure_database_exists_local`)
  - [ ] Update pool parameter names (`minsize` → `min_size`, etc.)
  - [ ] Update `disconnect()` method for asyncpg

- [ ] **Migration Runner** (`app/migrations.py`)
  - [ ] Replace `aiomysql` imports with `asyncpg`
  - [ ] Update parameterization: `%s` → `$1, $2`
  - [ ] Use `connection.transaction()` context manager
  - [ ] Update `_ensure_migrations_table()` to remove MySQL clauses
  - [ ] Update `_get_applied_versions()` to use `connection.fetch()`
  - [ ] Update `_apply_migration()` to use asyncpg transaction API

- [ ] **Schema Migrations** (`migrations/*.sql`)
  - [ ] Convert `001_create_users_table.sql` to PostgreSQL
    - [ ] `BIGINT UNSIGNED AUTO_INCREMENT` → `BIGSERIAL`
    - [ ] Remove `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`
  - [ ] Convert `002_add_community_safety_tables.sql` to PostgreSQL
    - [ ] All `BIGINT UNSIGNED AUTO_INCREMENT` → `BIGSERIAL`
    - [ ] All `TINYINT UNSIGNED` → `SMALLINT` + CHECK constraint
    - [ ] All `INT UNSIGNED` → `INTEGER` + CHECK constraint
    - [ ] `ON UPDATE CURRENT_TIMESTAMP` → Trigger function
    - [ ] All `ON DUPLICATE KEY UPDATE` → `ON CONFLICT ... DO UPDATE`
    - [ ] Remove all `ENGINE` and `CHARSET` clauses
    - [ ] Move indexes to separate `CREATE INDEX` statements

- [ ] **AuthService** (`app/services/auth_service.py`)
  - [ ] Remove `from aiomysql import DictCursor`
  - [ ] Update `signup()`: Replace `%s` with `$1, $2, $3`, add `RETURNING id`
  - [ ] Update `signup()`: Use `connection.fetchval()` for ID retrieval
  - [ ] Update `login()`: Replace `%s` with `$1`
  - [ ] Update `get_user_by_id()`: Replace `%s` with `$1`, use `fetchrow()`
  - [ ] Update `_get_user_by_email()`: Replace `%s` with `$1`, use `fetchrow()`

- [ ] **CommunityService** (`app/services/community_service.py`)
  - [ ] Remove `from aiomysql import DictCursor`
  - [ ] Update all parameterization: `%s` → `$1, $2, ...`
  - [ ] Update `add_favorite_place()`: Convert `ON DUPLICATE KEY UPDATE`
  - [ ] Update `list_favorite_places()`: Use `connection.fetch()`
  - [ ] Update `get_favorite_place()`: Use `connection.fetchrow()`
  - [ ] Update `add_place_rating()`: Update parameterization
  - [ ] Update `get_place_safety_summary()`: Update parameterization, use `fetch()`
  - [ ] Update `add_road_rating()`: Add transaction context, update params
  - [ ] Update `get_road_safety_summary()`: Fix dynamic placeholder generation
  - [ ] Update `add_comment()`: Add `RETURNING id`, use `fetchval()`
  - [ ] Update `list_comments()`: Update parameterization, use `fetch()`
  - [ ] Update `list_user_comments()`: Update parameterization, use `fetch()`
  - [ ] Update `list_nearby_comments()`: Update parameterization, use `fetch()`
  - [ ] Update `_refresh_segment_scores()`: Update params, use `fetchrow()`, convert upsert


### Testing

- [ ] **Unit Tests**
  - [ ] Test user signup with valid data
  - [ ] Test user signup with duplicate email
  - [ ] Test user login with correct credentials
  - [ ] Test user login with incorrect password
  - [ ] Test adding favorite place
  - [ ] Test adding duplicate favorite (upsert)
  - [ ] Test listing favorites
  - [ ] Test removing favorite
  - [ ] Test adding place rating
  - [ ] Test calculating place safety summary
  - [ ] Test adding road rating
  - [ ] Test calculating road safety summary
  - [ ] Test adding comment
  - [ ] Test listing comments

- [ ] **Integration Tests**
  - [ ] Test full signup → login → add favorite workflow
  - [ ] Test foreign key cascade (delete user → favorites deleted)
  - [ ] Test unique constraint enforcement
  - [ ] Test transaction rollback on error

- [ ] **Migration Tests**
  - [ ] Test migrations on empty database
  - [ ] Test migrations idempotency (re-run)
  - [ ] Test migration tracking in schema_migrations

- [ ] **API Contract Tests**
  - [ ] Compare signup response schema (MySQL vs PostgreSQL)
  - [ ] Compare login response schema
  - [ ] Compare favorites list response schema
  - [ ] Compare safety summary response schema
  - [ ] Compare comments list response schema

- [ ] **Data Precision Tests**
  - [ ] Test coordinate precision (DECIMAL(10,7))
  - [ ] Test rating calculations (normalized_score)
  - [ ] Test timestamp formatting

### Deployment

- [ ] **Local Development**
  - [ ] Install PostgreSQL (Docker or native)
  - [ ] Create `.env` file with PostgreSQL settings
  - [ ] Run application locally
  - [ ] Verify migrations applied
  - [ ] Test all API endpoints

- [ ] **Render Deployment**
  - [ ] Create PostgreSQL database on Render
  - [ ] Create web service on Render
  - [ ] Configure environment variables
  - [ ] Deploy application
  - [ ] Verify migrations applied
  - [ ] Test API health endpoint
  - [ ] Test user signup/login
  - [ ] Monitor logs for errors

### Documentation

- [ ] Update README with PostgreSQL setup instructions
- [ ] Document environment variables
- [ ] Document Render deployment process
- [ ] Document migration verification steps
- [ ] Document troubleshooting common issues

## Summary

This design provides a complete technical specification for migrating the Navigo backend from MySQL to PostgreSQL. The migration maintains 100% functional equivalence while enabling deployment on Render's managed PostgreSQL service.

**Key Migration Points**:
1. Replace aiomysql driver with asyncpg
2. Update configuration to support DATABASE_URL
3. Convert schema migrations to PostgreSQL syntax
4. Update query parameterization from %s to $1, $2, ...
5. Replace cursor.lastrowid with RETURNING clause
6. Convert ON DUPLICATE KEY UPDATE to ON CONFLICT
7. Implement triggers for ON UPDATE CURRENT_TIMESTAMP behavior
8. Maintain exact API contract compatibility

The migration is designed to be reversible, thoroughly testable, and deployable with minimal risk.
