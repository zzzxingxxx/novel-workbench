from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/novel_workbench.db"
    app_name: str = "Novel Workbench"
    model_config = SettingsConfigDict(
        env_prefix="NOVEL_WORKBENCH_", env_file=".env", extra="ignore"
    )


settings = Settings()


def ensure_database_directory(database_url: str) -> None:
    if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        path = Path(database_url.removeprefix("sqlite:///"))
        path.parent.mkdir(parents=True, exist_ok=True)
