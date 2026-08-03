from __future__ import annotations

from datetime import timedelta

from app.config import Settings
from app.db import Database
from app.schemas import AuthResponse, LoginRequest, SignupRequest, UserResponse
from app.security import create_access_token, hash_password, verify_password


class AuthServiceError(Exception):
    pass


class AuthService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self._database = database
        self._settings = settings

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
                password_hash,
            )

        user = UserResponse(
            id=int(user_id),
            full_name=request.full_name.strip(),
            email=request.email.lower(),
        )
        return self._build_auth_response(user)

    async def login(self, request: LoginRequest) -> AuthResponse:
        user_row = await self._get_user_by_email(request.email)
        if user_row is None:
            raise AuthServiceError("Invalid email or password.")

        if not verify_password(request.password, user_row["password_hash"]):
            raise AuthServiceError("Invalid email or password.")

        user = UserResponse(
            id=int(user_row["id"]),
            full_name=user_row["full_name"],
            email=user_row["email"],
        )
        return self._build_auth_response(user)

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

    async def _get_user_by_email(self, email: str) -> dict | None:
        select_query = """
        SELECT id, full_name, email, password_hash
        FROM users
        WHERE email = $1
        LIMIT 1
        """

        async with self._database.pool.acquire() as connection:
            return await connection.fetchrow(select_query, email.lower())

    def _build_auth_response(self, user: UserResponse) -> AuthResponse:
        access_token = create_access_token(
            subject=str(user.id),
            settings=self._settings,
            expires_delta=timedelta(
                minutes=self._settings.jwt_access_token_expire_minutes,
            ),
        )

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            user=user,
        )
