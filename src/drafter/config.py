from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DRAFTER_", extra="ignore")

    riot_api_key: str = Field(default="", validation_alias="RIOT_API_KEY")
    data_dir: Path = Path("data")
    # Starting guess, replaced by the X-App-Rate-Limit header after the first response.
    app_rate_limit: str = "20:1,100:120"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "drafter.duckdb"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def static_dir(self) -> Path:
        return self.data_dir / "static"
