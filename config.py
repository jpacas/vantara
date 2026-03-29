from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    TELEGRAM_TOKEN: str
    TELEGRAM_USER_ID: int
    GROQ_API_KEY: str
    OPENAI_API_KEY: str
    DATABASE_URL: str

    class Config:
        env_file = ".env"


settings = Settings()
