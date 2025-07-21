from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "swsauda"
    secret_key: str = "your-secret-key-here-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    super_admin_email: str = "admin@swsauda.com"
    super_admin_password: str = "admin123"
    
    class Config:
        env_file = ".env"

settings = Settings() 