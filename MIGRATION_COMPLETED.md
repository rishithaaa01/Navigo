# PostgreSQL Migration Status

## ✅ Completed Changes

### 1. Dependencies Updated
- ✅ `requirements.txt` - Updated to use `asyncpg==0.29.0`
- ✅ Removed `aiomysql` and `PyMySQL` dependencies

### 2. Configuration Updated  
- ✅ `backend/app/config.py` - Added PostgreSQL configuration
  - Supports `DATABASE_URL` environment variable (for Render)
  - Supports individual `POSTGRES_*` environment variables (for local)
  - Added `db_config` computed property for URL parsing
  - Added `environment` field to control database creation

### 3. Database Module Updated
- ✅ `backend/app/db.py` - Migrated to asyncpg
  - Updated imports from `aiomysql` to `asyncpg`
  - Updated connection pool to use `asyncpg.create_pool()`
  - Uses `db_config` property for connection parameters
  - Added conditional database creation (local only)

### 4. Migration Runner Updated
- ✅ `backend/app/migrations.py` - Migrated to asyncpg
  - Updated imports to `asyncpg`
  - Updated queries to use `$1, $2` parameterization
  - Uses `connection.transaction()` for rollback safety
  - Removed MySQL-specific ENGINE and CHARSET clauses

### 5. SQL Migrations Converted
- ✅ `001_create_users_table.sql` - PostgreSQL syntax
  - `BIGINT UNSIGNED AUTO_INCREMENT` → `BIGSERIAL`
  - Removed `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`
  
- ✅ `002_add_community_safety_tables.sql` - PostgreSQL syntax
  - `BIGINT UNSIGNED AUTO_INCREMENT` → `BIGSERIAL`
  - `TINYINT UNSIGNED` → `SMALLINT` with CHECK constraints
  - `INT UNSIGNED` → `INTEGER` with CHECK constraints
  - Added trigger for `ON UPDATE CURRENT_TIMESTAMP` behavior
  - Removed all ENGINE and CHARSET clauses
  - Converted indexes to PostgreSQL syntax

## ⚠️ Remaining Service Layer Updates Needed

The following files still need query parameter updates (`%s` → `$1, $2, $3...`):

### High Priority:
1. **`backend/app/services/auth_service.py`** - Auth queries
2. **`backend/app/services/community_service.py`** - Community queries  
3. **`backend/app/services/mapping_service.py`** - Mapping queries (if has DB queries)

### Updates Needed:
- Replace `%s` with `$1, $2, $3` sequential parameters
- Replace `cursor.lastrowid` with `RETURNING id` clause
- Use `connection.fetchval()`, `connection.fetchrow()`, `connection.fetch()` instead of cursor methods
- Convert `ON DUPLICATE KEY UPDATE` to `ON CONFLICT DO UPDATE`
- Remove `DictCursor` usage (asyncpg returns Record objects by default)

## 🚀 Environment Setup

### For Local Development:

Create `backend/.env`:
```env
# PostgreSQL Configuration (Local)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=navigo_user
POSTGRES_PASSWORD=your_password_here
POSTGRES_DATABASE=navigo_db
ENVIRONMENT=local

# OR use DATABASE_URL (alternative)
# DATABASE_URL=postgresql://navigo_user:your_password_here@localhost:5432/navigo_db

# JWT Secret
JWT_SECRET_KEY=generate-a-secure-random-string-here-at-least-32-chars
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440

# GraphHopper API
GRAPHHOPPER_API_KEY=your_graphhopper_api_key_here

# Cache Settings
SEARCH_CACHE_TTL_SECONDS=300
ROUTE_CACHE_TTL_SECONDS=120
```

### For Render Production:

Set these environment variables in Render dashboard:
```env
# Render provides DATABASE_URL automatically when you create PostgreSQL database
DATABASE_URL=postgresql://user:password@host.render.com:5432/database_name
ENVIRONMENT=production

# JWT Secret (generate with: python -c "import secrets; print(secrets.token_urlsafe(32))")
JWT_SECRET_KEY=your-generated-secret-here

# GraphHopper API
GRAPHHOPPER_API_KEY=your_graphhopper_api_key_here

# Cache Settings (optional)
SEARCH_CACHE_TTL_SECONDS=300
ROUTE_CACHE_TTL_SECONDS=120
```

### Frontend `.env`:
```env
# After deploying backend to Render, update this URL
BACKEND_BASE_URL=https://your-backend-name.onrender.com
```

## 📋 Next Steps

1. **Update Service Layer Queries** (auth_service.py, community_service.py)
2. **Install PostgreSQL locally**:
   ```bash
   # Windows (with chocolatey)
   choco install postgresql
   
   # Or use Docker
   docker run --name navigo-postgres -e POSTGRES_PASSWORD=yourpassword -p 5432:5432 -d postgres:15
   ```

3. **Create local database and user**:
   ```sql
   CREATE USER navigo_user WITH PASSWORD 'your_password_here';
   CREATE DATABASE navigo_db OWNER navigo_user;
   ```

4. **Test locally**:
   ```bash
   cd backend
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```

5. **Deploy to Render**:
   - Create PostgreSQL database on Render
   - Create Web Service
   - Set environment variables
   - Deploy from Git

## 🔧 Quick Command Reference

### Generate JWT Secret:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Test PostgreSQL connection:
```bash
psql postgresql://user:password@localhost:5432/database_name
```

### Run migrations manually:
The migrations run automatically on app startup, but you can test them:
```python
import asyncio
from pathlib import Path
import asyncpg
from app.migrations import run_migrations

async def test():
    pool = await asyncpg.create_pool(
        host='localhost',
        port=5432,
        user='navigo_user',
        password='your_password',
        database='navigo_db'
    )
    await run_migrations(pool, Path('migrations'))
    await pool.close()

asyncio.run(test())
```
