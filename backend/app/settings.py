import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CORS_ORIGINS: list[str] = [
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
    cors_origins: str | list[str] = Field(default=DEFAULT_CORS_ORIGINS)

    @field_validator("cors_origins", mode="after")
    @classmethod
    def normalize_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return DEFAULT_CORS_ORIGINS
            if v.startswith("[") and v.endswith("]"):
                try:
                    loaded = json.loads(v)
                    if isinstance(loaded, list):
                        return [str(item).strip() for item in loaded if str(item).strip()]
                except Exception:
                    pass
            origins = [item.strip() for item in v.split(",") if item.strip()]
            return origins or DEFAULT_CORS_ORIGINS
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
