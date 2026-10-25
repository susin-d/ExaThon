import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Complaint Root-Cause Engine"
    data_backend: str = "demo"
    demo_scale: int = Field(default=1, ge=1, le=250)
    demo_user_ids: list[str] = Field(
        default=[
            "susinsusindran@gmail.com",
            "vigneshwaran7002@gmail.com",
            "sushramesh5@gmail.com",
        ]
    )
    demo_db_path: Path = Field(
        default_factory=lambda: Path("/tmp/complaint-engine-demo.db")
        if os.getenv("VERCEL")
        else Path("backend/demo.db")
    )
    supabase_db_url: str = ""
    queue_enabled: bool = False
    redis_url: str = ""
    cron_secret: str = ""
    worker_batch_size: int = Field(default=25, ge=1, le=100)
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
            "https://exathon-web.vercel.app",
            "https://altas-resolve.vercel.app",
            "https://altas-resolve-5ome8lzto-dhanayendran-5428s-projects.vercel.app",
            "https://altas-resolve-g1y802pfn-dhanayendran-5428s-projects.vercel.app",
            "https://altas-resolve-987lp3hts-dhanayendran-5428s-projects.vercel.app",
        ]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
