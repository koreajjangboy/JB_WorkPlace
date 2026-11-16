from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://jb_workplace@localhost:5432/jb_workplace"

    # 이 폴더들의 바로 아래에 있는 git 저장소를 프로젝트로 등록한다. 쉼표로 여러 개 지정.
    scan_roots: str = r"C:\dev"

    # Claude Code 세션 기록 폴더
    claude_projects_dir: Path = Path.home() / ".claude" / "projects"

    # 프론트엔드 개발 서버 주소 (CORS 허용)
    frontend_origin: str = "http://localhost:5173"

    @property
    def scan_root_paths(self) -> list[Path]:
        return [Path(p.strip()) for p in self.scan_roots.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
