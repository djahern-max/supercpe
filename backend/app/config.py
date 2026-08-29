from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    cors_origins: str = "http://localhost:5173"
    storage_root: str = "uploads"
    # True on a developer machine: the session cookie is sent without the
    # Secure flag so plain-http localhost works. Production sets DEV=false.
    dev: bool = True

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
