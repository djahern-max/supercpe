from pydantic_settings import BaseSettings, SettingsConfigDict

PRODUCTION_ORIGIN = "https://supercpe.com"

# The shortest secret this app will boot with in production. Sessions are
# server-side random tokens (009), so the only secret-class value config
# carries is the Spaces secret; the database password travels inside
# DATABASE_URL and is the managed cluster's own.
MIN_SECRET_BYTES = 32

SPACES_VARS = (
    "SPACES_BUCKET",
    "SPACES_REGION",
    "SPACES_ENDPOINT",
    "SPACES_KEY",
    "SPACES_SECRET",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    cors_origins: str = "http://localhost:5173"
    storage_root: str = "uploads"
    # True on a developer machine: the session cookie is sent without the
    # Secure flag so plain-http localhost works. Production sets DEV=false.
    dev: bool = True
    # dev | prod. prod turns on the boot refusals in `boot_violations`.
    env: str = "dev"
    # local | spaces.
    storage_backend: str = "local"
    spaces_bucket: str = ""
    spaces_region: str = ""
    spaces_endpoint: str = ""
    spaces_key: str = ""
    spaces_secret: str = ""
    # The git sha baked into the image at build time; `/health` reports it.
    app_version: str = "dev"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


class ConfigurationError(RuntimeError):
    pass


def boot_violations(settings: Settings) -> list[str]:
    """Everything wrong with the configuration, all at once, so a bad
    deploy is fixed in one edit instead of one restart per mistake."""
    violations: list[str] = []

    if settings.env not in ("dev", "prod"):
        violations.append(f"ENV must be 'dev' or 'prod', not '{settings.env}'.")
    if settings.storage_backend not in ("local", "spaces"):
        violations.append(
            "STORAGE_BACKEND must be 'local' or 'spaces', not "
            f"'{settings.storage_backend}'."
        )

    if settings.storage_backend == "spaces":
        for var in SPACES_VARS:
            if not getattr(settings, var.lower()):
                violations.append(f"{var} is required when STORAGE_BACKEND=spaces.")

    if settings.env == "prod":
        if settings.dev:
            violations.append(
                "DEV must be false in prod: the session cookie must carry "
                "the Secure flag."
            )
        if settings.cors_origins != PRODUCTION_ORIGIN:
            violations.append(
                f"CORS_ORIGINS must be exactly {PRODUCTION_ORIGIN} in prod, "
                f"not '{settings.cors_origins}'."
            )
        if "sslmode=require" not in settings.database_url:
            violations.append(
                "DATABASE_URL must carry sslmode=require in prod."
            )
        if settings.storage_backend != "spaces":
            violations.append(
                "STORAGE_BACKEND must be spaces in prod: local disk does "
                "not satisfy 9.02 retention."
            )
        if len(settings.spaces_secret.encode()) < MIN_SECRET_BYTES:
            violations.append(
                f"SPACES_SECRET must be at least {MIN_SECRET_BYTES} bytes."
            )

    return violations


def ensure_boot_config(settings: Settings) -> None:
    violations = boot_violations(settings)
    if violations:
        raise ConfigurationError(
            "Refusing to boot with this configuration:\n- "
            + "\n- ".join(violations)
        )


settings = Settings()
