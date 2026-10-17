from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://this_or_that:this_or_that@localhost:5432/this_or_that"
    cors_origins: list[str] = ["http://localhost:5173"]
    # How long a disconnected lobby host keeps the role before it is handed off (SPEC §3).
    host_grace_seconds: float = 120
    # Pause after the bracket drops / a matchup is decided, before the next vote opens (SPEC §7).
    reveal_seconds: float = 5
    # Length of the sudden-death revote after a tie (SPEC §8).
    revote_seconds: float = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()
