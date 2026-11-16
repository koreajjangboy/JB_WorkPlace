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

    # ---- Runner (Claude Code 실행) ----
    # 비워 두면 npm 전역 설치 위치와 PATH에서 찾는다.
    claude_exe: str = ""
    # 실행에 노출할 도구 (--restricted 모드에서 이 목록만 쓸 수 있다)
    runner_tools: str = "Read,Edit,Write,Glob,Grep,Bash"
    # 묻지 않고 허용할 도구와 명령. 여기 없는 명령은 자동으로 거부된다.
    # (git status 같은 읽기 전용 명령은 Claude Code가 스스로 허용한다)
    runner_allowed_tools: str = (
        "Read,Edit,Write,Glob,Grep,"
        "Bash(npm test*),Bash(npm run test*),Bash(npm run build*),Bash(npm run lint*),"
        "Bash(npx tsc*),Bash(pytest*),Bash(uv run pytest*),Bash(python -m pytest*),"
        "Bash(git diff*),Bash(git status*),Bash(git log*)"
    )
    # 위 허용 목록과 상관없이 항상 거부할 명령
    runner_disallowed_tools: str = (
        "Bash(git push*),Bash(git commit*),Bash(git reset*),Bash(git checkout*),"
        "Bash(rm *),Bash(del *),WebFetch,WebSearch"
    )
    runner_max_concurrent: int = 1
    runner_max_minutes: int = 30
    runner_max_budget_usd: float = 2.0  # 실행 1회당 비용 상한 (--max-budget-usd)
    runner_model: str = ""  # 비워 두면 Claude Code 기본 모델

    @property
    def scan_root_paths(self) -> list[Path]:
        return [Path(p.strip()) for p in self.scan_roots.split(",") if p.strip()]

    @property
    def resolved_claude_exe(self) -> str | None:
        import os
        import shutil

        if self.claude_exe:
            return self.claude_exe if Path(self.claude_exe).is_file() else None
        appdata = os.environ.get("APPDATA")
        if appdata:
            npm_exe = Path(appdata) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
            if npm_exe.is_file():
                return str(npm_exe)
        # Windows에서는 .cmd/.ps1 래퍼를 피하고 실행 파일(.exe)만 찾는다.
        return shutil.which("claude.exe" if os.name == "nt" else "claude")


@lru_cache
def get_settings() -> Settings:
    return Settings()
