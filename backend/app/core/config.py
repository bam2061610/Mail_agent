from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Orhun Mail Agent"
    environment: str = "dev"
    database_url: str = "postgresql+asyncpg://oma:oma@localhost:5432/oma"
    redis_url: str | None = None
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_base_url: str | None = None
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
