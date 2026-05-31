import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "CatForge / 品铸"
    api_prefix: str = ""
    database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    upload_dir: Path | None = None
    export_dir: Path | None = None
    sync_jobs: bool = True

    @property
    def repo_root(self) -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "examples").exists() and ((parent / "apps").exists() or (parent / "app").exists()):
                return parent
        return Path.cwd()

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.repo_root / 'data' / 'catforge.db'}"

    @property
    def resolved_upload_dir(self) -> Path:
        return self.upload_dir or self.repo_root / "data" / "uploads"

    @property
    def resolved_export_dir(self) -> Path:
        return self.export_dir or self.repo_root / "data" / "exports"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("CATFORGE_DATABASE_URL"),
        redis_url=os.getenv("CATFORGE_REDIS_URL", "redis://localhost:6379/0"),
        upload_dir=Path(os.environ["CATFORGE_UPLOAD_DIR"]) if os.getenv("CATFORGE_UPLOAD_DIR") else None,
        export_dir=Path(os.environ["CATFORGE_EXPORT_DIR"]) if os.getenv("CATFORGE_EXPORT_DIR") else None,
        sync_jobs=os.getenv("CATFORGE_SYNC_JOBS", "true").lower() not in {"0", "false", "no"},
    )
