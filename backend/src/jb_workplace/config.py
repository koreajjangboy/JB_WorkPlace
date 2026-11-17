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
    # 커밋 메시지 초안을 쓸 때 쓰는 모델과 비용 상한 (읽기만 하는 짧은 실행)
    commit_message_model: str = "sonnet"
    commit_message_budget_usd: float = 0.5

    # ---- Google 캘린더 ----
    # 캘린더 설정 > 캘린더 통합 > "iCal 형식의 비공개 주소". 쉼표로 여러 개 지정.
    google_calendar_ics_urls: str = ""
    # 일정 시간을 이 시간대로 바꿔 보여준다.
    calendar_timezone: str = "Asia/Seoul"
    # 받아 온 캘린더를 다시 받기 전까지 쓰는 시간(초)
    calendar_cache_seconds: int = 300

    @property
    def calendar_urls(self) -> list[str]:
        return [u.strip() for u in self.google_calendar_ics_urls.split(",") if u.strip()]

    # ---- Google 캘린더 ----
    # 캘린더 설정 > 캘린더 통합 > "iCal 형식의 비공개 주소". 쉼표로 여러 개 지정.
    google_calendar_ics_urls: str = ""
    # 일정을 보여줄 시간대
    calendar_timezone: str = "Asia/Seoul"

    @property
    def calendar_ics_urls(self) -> list[str]:
        return [u.strip() for u in self.google_calendar_ics_urls.split(",") if u.strip()]

    # ---- Gemini 앱 사용량 (Google Takeout) ----
    # 이 폴더들에 생기는 takeout-*.zip 을 자동으로 가져온다. 쉼표로 여러 개 지정.
    # Takeout을 Google Drive로 받고 Drive 데스크톱 앱으로 동기화하면 'G:\내 드라이브\Takeout' 에 생긴다.
    takeout_dirs: str = str(Path.home() / "Downloads") + r",G:\내 드라이브\Takeout,G:\My Drive\Takeout"

    # ---- Google Cloud 결제 내보내기 (BigQuery) ----
    # 결제 내보내기 테이블 전체 이름 (프로젝트.데이터세트.gcp_billing_export_v1_…). 쉼표로 여러 개 지정.
    # 인증은 `gcloud auth application-default login` 으로 만든 ADC (또는 GOOGLE_APPLICATION_CREDENTIALS 키 파일).
    gcp_billing_tables: str = ""
    # 가져올 서비스: "결제 서비스 이름=WorkPlace 서비스 이름". 쉼표로 여러 개 지정.
    gcp_billing_services: str = "Gemini API=gemini"
    # 몇 시간마다 가져올지
    gcp_billing_sync_hours: int = 6

    # ---- OpenAI (조직 Usage·Costs API) ----
    # platform.openai.com/settings/organization/admin-keys 에서 만든 Admin API 키 (sk-admin-…). 읽기 전용으로 만든다.
    openai_admin_key: str = ""
    openai_sync_hours: int = 6

    # ---- Runway (개발자 API 조직 사용량) ----
    # dev.runwayml.com 개발자 포털에서 만든 API 키
    runway_api_key: str = ""
    runway_usd_per_credit: float = 0.01  # API 크레딧 1개 가격
    runway_sync_hours: int = 6

    @property
    def billing_tables(self) -> list[str]:
        return [t.strip().strip("`") for t in self.gcp_billing_tables.split(",") if t.strip()]

    @property
    def billing_services(self) -> dict[str, str]:
        pairs = (p.split("=", 1) for p in self.gcp_billing_services.split(",") if "=" in p)
        return {k.strip(): v.strip().lower() for k, v in pairs if k.strip() and v.strip()}

    @property
    def takeout_dir_paths(self) -> list[Path]:
        return [Path(p.strip()) for p in self.takeout_dirs.split(",") if p.strip()]

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
