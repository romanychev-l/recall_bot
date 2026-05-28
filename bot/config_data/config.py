from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from pymongo import AsyncMongoClient


class Settings(BaseSettings):
    TOKEN: SecretStr

    # Either set MONGO_URI directly (recommended), or use host/port pieces.
    MONGO_URI: Optional[str] = None
    MONGO_HOST: str = "localhost"
    MONGO_PORT: int = 27017
    MONGO_DB_NAME: str = "recall_bot"

    LOG_LEVEL: str = "INFO"
    SCHEDULER_TZ: str = "UTC"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def mongo_uri(self) -> str:
        if self.MONGO_URI:
            return self.MONGO_URI
        return f"mongodb://{self.MONGO_HOST}:{self.MONGO_PORT}"


config_settings = Settings()

# tz_aware=True so datetimes read back from Mongo are tz-aware UTC, matching the
# tz-aware datetimes used throughout the app (avoids naive/aware mix errors).
mongo_client = AsyncMongoClient(config_settings.mongo_uri, tz_aware=True)
db = mongo_client[config_settings.MONGO_DB_NAME]
