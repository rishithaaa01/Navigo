# Quick PostgreSQL Migration Completion Guide

## ✅ What's Done (90% Complete!)

1. ✅ Dependencies (`requirements.txt`)
2. ✅ Configuration (`config.py`)
3. ✅ Database connection (`db.py`)
4. ✅ Migration runner (`migrations.py`)
5. ✅ SQL migrations (001_, 002_)
6. ✅ **Auth service (`auth_service.py`) - FULLY MIGRATED**

## ⚠️ Last Step: Update Community Service

Only `community_service.py` needs updating. Here's the pattern:

### Search & Replace Pattern:

**1. Remove import:**
```python
# DELETE THIS LINE:
from aiomysql import DictCursor
```

**2. Update parameterization** - Find and replace:
```
%s → $1
(%s, %s) → $1, $2
(%s, %s, %s) → $1, $2, $3
# etc... (sequential numbers)
```

**3. Update cursor usage:**

**OLD Pattern:**
```python
async with connection.cursor() as cursor:
    await cursor.execute(query, (param1, param2))
    user_id = cursor.lastrowid
```

**NEW Pattern:**
```python
user_id = await connection.fetchval(
    query + " RETURNING id",
    param1, param2  # No tuple, direct params
)
```

**4. Update DictCursor queries:**

**OLD:**
```python
async with connection.cursor(DictCursor) as cursor:
    await cursor.execute(query, (param,))
    row = await cursor.fetchone()
```

**NEW:**
```python
row = await connection.fetchrow(query, param)  # No tuple
```

**5. Update fetch multiple:**

**OLD:**
```python
async with connection.cursor(DictCursor) as cursor:
    await cursor.execute(query, params)
    rows = await cursor.fetchall()
```

**NEW:**
```python
rows = await connection.fetch(query, *params)  # Unpack params
```

**6. Convert ON DUPLICATE KEY UPDATE:**

**OLD (MySQL):**
```sql
INSERT INTO favorite_places (user_id, place_name, address, latitude, longitude)
VALUES ($1, $2, $3, $4, $5)
ON DUPLICATE KEY UPDATE
    place_name = VALUES(place_name),
    address = VALUES(address)
```

**NEW (PostgreSQL):**
```sql
INSERT INTO favorite_places (user_id, place_name, address, latitude, longitude)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (user_id, latitude, longitude)
DO UPDATE SET
    place_name = EXCLUDED.place_name,
    address = EXCLUDED.address
```

**7. Dynamic IN clause (road_segment_safety_scores query):**

**OLD:**
```python
placeholders = ", ".join(["%s"] * len(segment_keys))
query = f"SELECT ... WHERE segment_key IN ({placeholders})"
await cursor.execute(query, tuple(segment_keys))
```

**NEW:**
```python
placeholders = ", ".join([f"${i+1}" for i in range(len(segment_keys))])
query = f"SELECT ... WHERE segment_key IN ({placeholders})"
rows = await connection.fetch(query, *segment_keys)  # Unpack!
```

## 🚀 Quick Setup for Render

### 1. Create PostgreSQL Database on Render:
1. Go to Render Dashboard
2. Click "New +" → "PostgreSQL"
3. Name: `navigo-db`
4. Database: `navigo_db`
5. User: `navigo_user`
6. Region: Singapore
7. Plan: Free
8. Click "Create Database"

### 2. Create Web Service:
1. Click "New +" → "Web Service"
2. Connect your GitHub repo
3. Name: `navigo-backend`
4. Region: Singapore
5. Branch: `main`
6. Root Directory: `backend`
7. Runtime: Python 3
8. Build Command: `pip install -r requirements.txt`
9. Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### 3. Add Environment Variables in Render:
```
DATABASE_URL=<auto-filled-by-render-when-you-link-database>
ENVIRONMENT=production
JWT_SECRET_KEY=<generate-with-command-below>
GRAPHHOPPER_API_KEY=<your-key>
```

**Generate JWT Secret:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. Link Database:
- In Web Service settings, go to "Environment"
- Click "Add Environment Group"
- Select your PostgreSQL database
- This auto-adds `DATABASE_URL`

### 5. Deploy:
- Click "Manual Deploy" → "Deploy latest commit"
- Wait 3-5 minutes
- Check logs for "Application startup complete"

### 6. Get Your Backend URL:
- It will be: `https://navigo-backend.onrender.com`
- Test: `https://navigo-backend.onrender.com/docs`

### 7. Update Frontend `.env`:
Create `frontend/.env`:
```env
BACKEND_BASE_URL=https://navigo-backend.onrender.com
```

### 8. Rebuild APK with new backend URL!

## 🔧 Local Testing (Optional but Recommended)

### Install PostgreSQL:
```bash
# Windows (with Chocolatey)
choco install postgresql

# Or use Docker
docker run --name navigo-postgres \
  -e POSTGRES_PASSWORD=navigo123 \
  -e POSTGRES_USER=navigo_user \
  -e POSTGRES_DB=navigo_db \
  -p 5432:5432 -d postgres:15
```

### Create `backend/.env`:
```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=navigo_user
POSTGRES_PASSWORD=navigo123
POSTGRES_DATABASE=navigo_db
ENVIRONMENT=local

JWT_SECRET_KEY=local-dev-secret-key-change-in-production
GRAPHHOPPER_API_KEY=your_key_here
```

### Test Locally:
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit: http://localhost:8000/docs

## ⚡ Fastest Path to Production

1. **Finish community_service.py** (10 min) - Use patterns above
2. **Push to GitHub** (1 min)
3. **Create Render Database** (2 min)
4. **Create Render Web Service** (3 min)
5. **Set environment variables** (2 min)
6. **Deploy** (5 min)
7. **Update frontend .env with backend URL** (1 min)
8. **Rebuild APK** (5 min)

**Total: ~30 minutes to production!**

## 🆘 Troubleshooting

### Error: "could not connect to server"
- Check DATABASE_URL is set correctly in Render
- Make sure database and web service are in same region

### Error: "relation does not exist"
- Check logs - migrations should run on startup
- Verify migration files are committed to Git

### Error: "Authentication failed"
- Make sure you updated frontend `.env` with correct `BACKEND_BASE_URL`
- Rebuild the APK after changing `.env`

### Error: "asyncpg.exceptions.InvalidParameterValueError"
- You missed a `%s` → `$N` conversion
- Search all `.py` files for `%s` in backend/app/services/

## 📝 Verification Checklist

- [ ] `community_service.py` updated (all %s → $N, cursor → connection methods)
- [ ] Code pushed to GitHub
- [ ] PostgreSQL created on Render
- [ ] Web Service created and linked to database
- [ ] Environment variables set (DATABASE_URL, JWT_SECRET_KEY, etc.)
- [ ] Deployment successful (check logs)
- [ ] API docs accessible at https://your-app.onrender.com/docs
- [ ] Frontend `.env` updated with backend URL
- [ ] APK rebuilt with new `.env`
- [ ] APK tested on device - authentication works!

Good luck! 🚀
