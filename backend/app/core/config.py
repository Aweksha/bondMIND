from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BONDMIND_", extra="ignore")

    env: str = "local"
    database_url: str = "postgresql+psycopg://bondmind:bondmind@localhost:5432/bondmind"
    cors_origins: list[str] = ["http://localhost:4200"]
    seed_dir: Path = REPO_ROOT / "data" / "seed"
    # Every response from a demo deployment carries this flag so the UI can label it.
    demo_mode: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
