"""AI 서비스 설정: 카탈로그, 프로젝트 코드에서 사용 위치 감지, 연결 상태.

감지는 각 git 저장소에서 `git grep`으로 SDK 이름·API 키 이름을 찾는다 (커밋 안 된 파일 포함,
.gitignore 대상은 제외). `jb_usage`가 보이면 그 프로젝트는 사용량을 보내도록 연결된 것으로 본다.
"""

import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# 자주 쓰는 서비스. 등록할 때 이 값을 기본으로 채운다. (목록에 없는 서비스도 직접 추가할 수 있다)
CATALOG: list[dict[str, Any]] = [
    {"name": "claude", "display_name": "Claude", "kind": "text", "default_unit": "token", "collection": "claude_logs",
     "detect": r"anthropic|@anthropic-ai/sdk|ANTHROPIC_API_KEY", "helper": "auto",
     "website": "https://www.anthropic.com/pricing"},
    {"name": "gemini", "display_name": "Gemini", "kind": "text", "default_unit": "token", "collection": "app",
     "detect": r"google\.genai|google\.generativeai|@google/genai|@google/generative-ai|GEMINI_API_KEY", "helper": "record_gemini",
     "website": "https://ai.google.dev/pricing"},
    {"name": "openai", "display_name": "OpenAI", "kind": "text", "default_unit": "token", "collection": "app",
     "detect": r"from openai|import openai|OPENAI_API_KEY|\"openai\"", "helper": "record_openai",
     "website": "https://openai.com/api/pricing"},
    {"name": "upstage", "display_name": "Upstage", "kind": "text", "default_unit": "token", "collection": "app",
     "detect": r"UPSTAGE_API_KEY|api\.upstage\.ai", "helper": "record_openai_upstage",
     "website": "https://www.upstage.ai/pricing"},
    {"name": "runway", "display_name": "Runway", "kind": "video", "default_unit": "credit", "collection": "app",
     "detect": r"runwayml|RUNWAY_API_KEY|RUNWAYML_API_SECRET", "helper": "record_usage",
     "website": "https://runwayml.com/pricing"},
    {"name": "elevenlabs", "display_name": "ElevenLabs", "kind": "audio", "default_unit": "char", "collection": "app",
     "detect": r"elevenlabs|ELEVENLABS_API_KEY|xi-api-key", "helper": "record_usage",
     "website": "https://elevenlabs.io/pricing"},
    {"name": "luma", "display_name": "Luma", "kind": "video", "default_unit": "credit", "collection": "app",
     "detect": r"lumaai|LUMA_API_KEY|api\.lumalabs\.ai", "helper": "record_usage",
     "website": "https://lumalabs.ai/api/pricing"},
]
CATALOG_BY_NAME = {c["name"]: c for c in CATALOG}

INSTRUMENT_MARK = "jb_usage"
_EXCLUDE = [":(exclude)node_modules", ":(exclude)**/node_modules/**", ":(exclude)*.lock", ":(exclude)package-lock.json",
            ":(exclude)**/*.min.js", ":(exclude).venv", ":(exclude)**/.venv/**", ":(exclude)**/dist/**"]

_cache: dict[str, Any] = {"at": None, "result": None}
_lock = threading.Lock()


def _grep(repo: str, pattern: str) -> set[str]:
    """저장소에서 패턴에 맞는 파일 경로 목록."""
    try:
        out = subprocess.run(
            ["git", "-C", repo, "grep", "-I", "-l", "-i", "--untracked", "-E", pattern, "--", ".", *_EXCLUDE],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {line.strip() for line in out.stdout.splitlines() if line.strip()} if out.returncode == 0 else set()


def _scan_project(path: str, providers: list[tuple[str, str]]) -> dict[str, Any]:
    if not (Path(path) / ".git").exists():
        return {"uses": {}, "instrumented": False}
    uses: dict[str, list[str]] = {}
    for name, pattern in providers:
        try:
            re.compile(pattern)
        except re.error:
            continue
        # 실제 호출 코드가 먼저 보이도록 .env·문서 파일은 뒤로 보낸다.
        def rank(f: str) -> tuple[int, str]:
            low = f.lower()
            config = ".env" in low or low.endswith((".md", ".txt", ".json", ".toml", ".lock", ".yml", ".yaml"))
            return (1 if config else 0, f)

        files = sorted((f for f in _grep(path, pattern) if "jb_usage" not in f), key=rank)
        if files:
            uses[name] = files[:5]
    instrumented = bool(_grep(path, INSTRUMENT_MARK))
    return {"uses": uses, "instrumented": instrumented}


def detect(projects: list[tuple[int, str, str]], providers: list[tuple[str, str]], refresh: bool = False) -> dict[str, Any]:
    """{"scanned_at", "projects": {project_id: {"name", "uses": {provider: [files]}, "instrumented"}}}"""
    # WorkPlace 저장소 자신은 카탈로그에 감지 패턴이 들어 있어 모든 서비스에 걸리므로 뺀다.
    own = str(Path(__file__).resolve().parents[3]).lower()
    projects = [p for p in projects if str(Path(p[2]).resolve()).lower() != own]
    with _lock:
        if not refresh and _cache["result"] is not None and _cache.get("key") == providers:
            return _cache["result"]
        with ThreadPoolExecutor(max_workers=6) as pool:
            scans = list(pool.map(lambda p: _scan_project(p[2], providers), projects))
        result = {
            "scanned_at": datetime.now(UTC).isoformat(),
            "projects": {pid: {"name": name, **scan} for (pid, name, _), scan in zip(projects, scans)},
        }
        _cache.update(at=datetime.now(UTC), result=result, key=providers)
        return result
