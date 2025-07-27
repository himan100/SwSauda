from decouple import config
import os
from typing import Optional

class Settings:
    def __init__(self):
        # Determine environment
        self.app_env: str = os.getenv("APP_ENV", config("APP_ENV", default="development"))
        # If in development, always read from .env, ignore env vars
        if self.app_env == "development":
            from dotenv import dotenv_values
            env = dotenv_values(".env")
            self.mongodb_url: str = env.get("MONGODB_URL", "mongodb://localhost:27017")
            self.database_name: str = env.get("DATABASE_NAME", "swsauda")
            self.secret_key: str = env.get("SECRET_KEY", "your-secret-key-here-change-in-production")
            self.algorithm: str = env.get("ALGORITHM", "HS256")
            self.access_token_expire_minutes: int = int(env.get("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
            self.super_admin_email: str = env.get("SUPER_ADMIN_EMAIL", "admin@swsauda.com")
            self.super_admin_password: str = env.get("SUPER_ADMIN_PASSWORD", "admin123")
            self.database_prefix: str = env.get("DATABASE_PREFIX", "N")
            self.host: str = env.get("HOST", "0.0.0.0")
            self.port: int = int(env.get("PORT", 8000))
            self.reload: bool = env.get("RELOAD", "true").lower() == "true"
            # Redis configuration
            self.redis_url: str = env.get("REDIS_URL", "redis://localhost:6379")
            self.redis_db: int = int(env.get("REDIS_DB", 0))
        else:
            # Production: use environment variables if set, fallback to .env
            self.mongodb_url: str = config("MONGODB_URL", default="mongodb://localhost:27017")
            self.database_name: str = config("DATABASE_NAME", default="swsauda")
            self.secret_key: str = config("SECRET_KEY", default="your-secret-key-here-change-in-production")
            self.algorithm: str = config("ALGORITHM", default="HS256")
            self.access_token_expire_minutes: int = config("ACCESS_TOKEN_EXPIRE_MINUTES", default=30, cast=int)
            self.super_admin_email: str = config("SUPER_ADMIN_EMAIL", default="admin@swsauda.com")
            self.super_admin_password: str = config("SUPER_ADMIN_PASSWORD", default="admin123")
            self.database_prefix: str = config("DATABASE_PREFIX", default="N")
            self.host: str = config("HOST", default="0.0.0.0")
            self.port: int = config("PORT", default=8000, cast=int)
            self.reload: bool = config("RELOAD", default=True, cast=bool)
            # Redis configuration
            self.redis_url: str = config("REDIS_URL", default="redis://localhost:6379")
            self.redis_db: int = config("REDIS_DB", default=0, cast=int)

settings = Settings() 