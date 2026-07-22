from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    upstash_redis_rest_url: str
    upstash_redis_rest_token: str
    secret_key: str
    smtp_email: str
    smtp_app_password: str

    class Config:
        env_file = ".env"

settings = Settings()
