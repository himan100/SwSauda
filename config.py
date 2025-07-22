from decouple import config
from typing import Optional

class Settings:
    def __init__(self):
        self.mongodb_url: str = config("MONGODB_URL", default="mongodb://localhost:27017")
        self.database_name: str = config("DATABASE_NAME", default="swsauda")
        self.secret_key: str = config("SECRET_KEY", default="your-secret-key-here-change-in-production")
        self.algorithm: str = config("ALGORITHM", default="HS256")
        self.access_token_expire_minutes: int = config("ACCESS_TOKEN_EXPIRE_MINUTES", default=30, cast=int)
        self.super_admin_email: str = config("SUPER_ADMIN_EMAIL", default="admin@swsauda.com")
        self.super_admin_password: str = config("SUPER_ADMIN_PASSWORD", default="admin123")
        self.database_prefix: str = config("DATABASE_PREFIX", default="N")  # Prefix for restored databases
        
        # Server configuration (optional)
        self.host: str = config("HOST", default="0.0.0.0")
        self.port: int = config("PORT", default=8000, cast=int)
        self.reload: bool = config("RELOAD", default=True, cast=bool)

settings = Settings() 