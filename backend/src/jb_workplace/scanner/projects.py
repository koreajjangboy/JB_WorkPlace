"""스캔 폴더 바로 아래의 git 저장소를 찾아 브랜치, 변경 파일 수, 마지막 커밋 시각을 읽는다."""

import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

GIT_TIMEOUT = 15


@dataclass
class RepoInfo:
    name: str
    path: str
    branch: str | None
    dirty_files: int
    last_commit_at: datetime | None


def _git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _read_repo(repo: Path) -> RepoInfo:
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    status = _git(repo, "status", "--porcelain", "--untracked-files=all")
    last = _git(repo, "log", "-1", "--format=%cI")
    last_commit_at = None
    if last and last.strip():
        try:
            last_commit_at = datetime.fromisoformat(last.strip())
        except ValueError:
            pass
    return RepoInfo(
        name=repo.name,
        path=str(repo),
        branch=branch.strip() if branch else None,
        dirty_files=len([l for l in status.splitlines() if l.strip()]) if status else 0,
        last_commit_at=last_commit_at,
    )


def find_repos(roots: list[Path]) -> list[Path]:
    repos: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir() and (child / ".git").exists():
                repos.append(child)
    return repos


def scan_repos(roots: list[Path]) -> list[RepoInfo]:
    repos = find_repos(roots)
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(_read_repo, repos))
