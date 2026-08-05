from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import urlparse
from typing import Optional


class Settings(BaseSettings):
    graphhopper_api_key: str = Field(alias="GRAPHHOPPER_API_KEY")
    graphhopper_base_url: str = "https://graphhopper.com/api/1"
    
    # PostgreSQL configuration
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: Optional[str] = Field(default=None, alias="POSTGRES_USER")
    postgres_password: Optional[str] = Field(default=None, alias="POSTGRES_PASSWORD")
    postgres_database: Optional[str] = Field(default=None, alias="POSTGRES_DATABASE")
    environment: str = Field(default="production", alias="ENVIRONMENT")
    
    jwt_secret_key: str = Field(alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(
        default=60 * 24,
        alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    search_cache_ttl_seconds: int = Field(
        default=300,
        alias="SEARCH_CACHE_TTL_SECONDS",
    )
    route_cache_ttl_seconds: int = Field(
        default=120,
        alias="ROUTE_CACHE_TTL_SECONDS",
    )

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


settings = Settings()
