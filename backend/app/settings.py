from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Complaint Root-Cause Engine"
    data_backend: str = "demo"
    demo_user_ids: list[str] = Field(
        default=[
            "susinsusindran@gmail.com",
            "vigneshwaran7002@gmail.com",
            "sushramesh5@gmail.com",
        ]
    )
    demo_db_path: Path = Path("backend/demo.db")
    redis_url: str = "redis://localhost:6379/0"
    exasol_dsn: str = ""
    exasol_user: str = ""
    exasol_password: str = ""
    exasol_schema: str = "COMPLAINT_ENGINE"
    cors_origins: list[str] = Field(
        default=[
            "http://localhost:5173",
            "http://localhost:4173",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:4173",
        ]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
