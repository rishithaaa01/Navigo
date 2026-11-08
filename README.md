# Navigo

**Navigo** is a location-aware safety and mapping application. It brings together map-based place discovery, route planning, community safety information, and quick access to emergency contacts.

## Features

- **Map and location:** Display a map, use the device's current location, and search for places.
- **Route planning:** Request shortest and safest route options between two points.
- **Community safety:** Support place and road safety ratings, summaries, and comments.
- **User accounts:** Sign up, log in, and access a profile.
- **Saved places:** Backend support for users' favorite places.
- **Emergency screen:** The mobile app provides one-tap calling for the emergency contacts listed in the app.

Route search uses OpenStreetMap's Nominatim service. Route candidates are obtained through the configured routing provider, and safest-route selection uses community safety data.

## Architecture

| Component | Technology | Location |
| --- | --- | --- |
| Mobile application | Flutter, Dart, Riverpod | `frontend/` |
| Maps | flutter_map, OpenStreetMap tiles, latlong2 | `frontend/` |
| Device location | geolocator | `frontend/` |
| API | Python, FastAPI | `backend/` |
| Database | PostgreSQL, asyncpg | `backend/` |
| Routing | GraphHopper provider integration | `backend/` |
| Place search | OpenStreetMap Nominatim | `backend/` |

## Repository structure

```text
.
├── frontend/          # Flutter mobile application
│   ├── lib/
│   │   ├── features/  # Map, location, routing and community features
│   │   ├── providers/
│   │   └── screens/
│   └── pubspec.yaml
├── backend/            # FastAPI service
│   ├── app/
│   │   ├── services/
│   │   ├── schemas.py
│   │   └── main.py
│   ├── migrations/
│   └── requirements.txt
├── CLAUDE.md           # Additional repository-specific development notes
└── DEPLOY_TO_RENDER.md # Deployment walkthrough
```

## Run locally

### 1. Backend API

Requirements: Python 3.11+ and PostgreSQL.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with a GraphHopper API key, a PostgreSQL connection, and a strong JWT secret. Then start the API from the `backend/` directory:

```bash
uvicorn app.main:app --reload
```

The API exposes interactive documentation at `/docs` while the development server is running.

### 2. Flutter application

Requirements: Flutter SDK and a configured Android or iOS development target.

```bash
cd frontend
flutter pub get
```

Create `frontend/.env` with the API base URL expected by the app's configuration, then run:

```bash
flutter run
```

For static analysis:

```bash
flutter analyze
```

## Backend configuration

The backend reads settings from environment variables or `backend/.env`.

| Variable | Purpose |
| --- | --- |
| `GRAPHHOPPER_API_KEY` | Routing provider credential |
| `DATABASE_URL` | PostgreSQL connection URL; alternatively use the `POSTGRES_*` variables |
| `POSTGRES_HOST`, `POSTGRES_PORT` | PostgreSQL host and port |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DATABASE` | PostgreSQL credentials and database |
| `JWT_SECRET_KEY` | Secret used to sign access tokens |
| `JWT_ALGORITHM` | Token signing algorithm (defaults to HS256) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime |
| `SEARCH_CACHE_TTL_SECONDS`, `ROUTE_CACHE_TTL_SECONDS` | Search and route cache durations |

Never commit real credentials or local `.env` files.

## Main API capabilities

The FastAPI service includes authentication, place search, route calculation, and community safety workflows. The route API provides shortest- and safest-route operations. Refer to the generated API documentation at `/docs` for the current request and response schemas.

## Deployment

See [DEPLOY_TO_RENDER.md](DEPLOY_TO_RENDER.md) for the repository's Render deployment notes. Review the environment variables and deployment settings before deploying to a public environment.
