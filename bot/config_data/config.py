from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.db.session import build_engine, build_session_factory


class Settings(BaseSettings):
    TOKEN: SecretStr

    # Path to the SQLite file. On Railway point this at the mounted volume,
    # e.g. /data/recall_bot.db, so the database survives redeploys.
    DB_PATH: str = "recall_bot.db"
    # Escape hatch: set a full SQLAlchemy URL to use another backend (e.g.
    # postgresql+asyncpg://...) without touching code.
    DATABASE_URL: Optional[str] = None

    # Seeded into an empty database on first start.
    DICTIONARY_CSV: str = "data/dictionary.csv"

    LOG_LEVEL: str = "INFO"
    SCHEDULER_TZ: str = "UTC"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"sqlite+aiosqlite:///{self.DB_PATH}"


config_settings = Settings()

engine = build_engine(config_settings.database_url)
session_factory = build_session_factory(engine)
