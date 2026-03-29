from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    TELEGRAM_TOKEN: str
    TELEGRAM_USER_ID: int
    GROQ_API_KEY: str
    OPENAI_API_KEY: str
    DATABASE_URL: str


settings = Settings()
