# ✅ Migration Complete! Deploy to Render Now

## 🎉 What's Done

ALL files have been migrated from MySQL to PostgreSQL:
- ✅ Dependencies (asyncpg installed)
- ✅ Configuration (DATABASE_URL support)
- ✅ Database connection
- ✅ Migration runner
- ✅ SQL schemas (001, 002)
- ✅ Auth service
- ✅ Community service

## 🚀 Deploy to Render (15 minutes)

### Step 1: Create PostgreSQL Database (3 min)

1. Go to https://dashboard.render.com
2. Click **"New +"** → **"PostgreSQL"**
3. Fill in:
   - Name: `navigo-db`
   - Database: `navigo_db`
   - User: `navigo_user`
   - Region: **Singapore (Southeast Asia)**
   - Plan: **Free**
4. Click **"Create Database"**
5. Wait ~2 minutes for database to be ready

### Step 2: Create Web Service (5 min)

1. Click **"New +"** → **"Web Service"**
2. **Connect your GitHub repository**
3. Fill in:
   - Name: `navigo-backend`
   - Region: **Singapore (Southeast Asia)**
   - Branch: `main` (or your default branch)
   - Root Directory: `backend`
   - Runtime: **Python 3**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Click **"Create Web Service"** (don't deploy yet!)

### Step 3: Link Database & Add Environment Variables (3 min)

1. In your web service, go to **"Environment"** tab
2. Click **"Add Environment Group"**
3. Select your `navigo-db` database
4. This automatically adds `DATABASE_URL`

Now add these environment variables manually:

```
ENVIRONMENT=production
JWT_SECRET_KEY=<generate-below>
GRAPHHOPPER_API_KEY=<your-graphhopper-key>
SEARCH_CACHE_TTL_SECONDS=300
ROUTE_CACHE_TTL_SECONDS=120
```

**Generate JWT Secret** (run this command):
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output and paste it as `JWT_SECRET_KEY`

### Step 4: Deploy! (4 min)

1. Click **"Manual Deploy"** → **"Deploy latest commit"**
2. Wait 3-4 minutes
3. Watch the logs for: **"Application startup complete"**
4. Your backend URL will be: `https://navigo-backend.onrender.com`

### Step 5: Test the API

Visit: `https://navigo-backend.onrender.com/docs`

You should see the FastAPI documentation page!

### Step 6: Update Frontend & Rebuild APK

1. Create `frontend/.env` file:
   ```env
   BACKEND_BASE_URL=https://navigo-backend.onrender.com
   ```

2. Rebuild your APK with this new `.env` file

3. Install the APK on your device

4. **Authentication will now work!** 🎉

## ❓ Troubleshooting

### Database connection error

- Make sure you linked the database in Environment settings
- Check that `DATABASE_URL` is set automatically

### Migration failed

- Check deployment logs
- Migrations run automatically on startup
- If you see errors about tables, the SQL might have syntax issues

### API returns 502

- Check logs for errors
- Make sure all environment variables are set
- Verify `PORT` is not overridden (Render sets it automatically)

### Frontend still says "Authentication failed"

- Make sure you created `frontend/.env` with correct `BACKEND_BASE_URL`
- Make sure you rebuilt the APK **after** adding the `.env` file
- The `.env` file must be in `frontend/` directory (same level as `pubspec.yaml`)

## 🎯 Expected Result

✅ Backend deployed at: `https://navigo-backend.onrender.com`
✅ API docs accessible: `https://navigo-backend.onrender.com/docs`
✅ Database connected (PostgreSQL on Render)
✅ Migrations applied automatically
✅ Frontend `.env` configured
✅ APK rebuilt with production backend URL
✅ **Authentication works on APK!**

## 📝 Quick Verification Checklist

- [ ] PostgreSQL database created on Render
- [ ] Web service created and linked to database
- [ ] `DATABASE_URL` environment variable set (auto)
- [ ] `JWT_SECRET_KEY` generated and set
- [ ] `GRAPHHOPPER_API_KEY` set
- [ ] `ENVIRONMENT=production` set
- [ ] Deployment successful (no errors in logs)
- [ ] API docs accessible at `/docs`
- [ ] Frontend `.env` created with backend URL
- [ ] APK rebuilt
- [ ] APK tested - authentication works!

---

**Need help?** Check the logs in Render dashboard or let me know what error you're seeing!
