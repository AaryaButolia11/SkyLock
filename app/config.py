from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    upstash_redis_rest_url: str
    upstash_redis_rest_token: str
    secret_key: str
    resend_api_key: str
    resend_from_email: str   # e.g. "SkyLock <onboarding@resend.dev>" or your verified domain sender
    groq_api_key: str

    class Config:
        env_file = ".env"
        
settings = Settings()
