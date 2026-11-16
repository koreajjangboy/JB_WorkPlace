"""작업이 바꾼 파일을 가려내고, diff를 보여주고, 사람이 승인한 파일만 커밋한다.

변경 추적 방식
- 첫 실행 직전에 저장 안 된 변경 목록과 각 파일 내용의 해시를 기록한다 (baseline).
- 나중에 지금의 변경 목록과 비교해서,
  · baseline에 없던 파일이 바뀌었으면 → 이 작업이 바꾼 파일
  · baseline에 있던 파일인데 내용(해시)이 달라졌으면 → 이 작업이 바꾼 파일 (원래 변경도 섞여 있음)
"""

import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

GIT_TIMEOUT = 60
DIFF_LIMIT = 120_000  # 파일 하나의 diff 최대 글자 수
NEW_FILE_LINE_LIMIT = 2000


class GitError(Exception):
    pass


def _git(repo: str, *args: str, stdin: str | None = None, check: bool = True) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=off", "-C", repo, *args],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git 실행 실패: {exc}") from exc
    if check and result.returncode != 0:
        raise GitError((result.stderr or result.stdout).strip() or f"git {' '.join(args)} 실패")
    return result.stdout


def _has_head(repo: str) -> bool:
    return bool(_git(repo, "rev-parse", "--verify", "-q", "HEAD", check=False).strip())


def _status(repo: str) -> dict[str, str]:
    """저장 안 된 변경 {경로: 상태 2글자}. 새 폴더 안의 파일도 하나씩 나열한다."""
    out = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries: dict[str, str] = {}
    parts = out.split("\0")
    i = 0
    while i < len(parts):
        item = parts[i]
        i += 1
        if len(item) < 4:
            continue
        code, path = item[:2], item[3:]
        if code[0] in "RC":  # 이름 바꾸기/복사: 다음 항목은 원래 이름이라 건너뛴다
            i += 1
        entries[path] = code
    return entries


def _hashes(repo: str, paths: list[str]) -> dict[str, str]:
    existing = [p for p in paths if (Path(repo) / p).is_file()]
    result = {p: "deleted" for p in paths if p not in existing}
    if existing:
        out = _git(repo, "hash-object", "--stdin-paths", stdin="\n".join(existing) + "\n")
        for path, digest in zip(existing, out.split()):
            result[path] = digest
    return result


def snapshot(repo: str) -> dict[str, dict[str, str]]:
    status = _status(repo)
    hashes = _hashes(repo, list(status))
    return {path: {"status": code, "hash": hashes.get(path, "")} for path, code in status.items()}


@dataclass
class FileChange:
    path: str
    status: str  # git 상태 2글자 (예: " M", "??", " D")
    kind: str  # added | modified | deleted | renamed
    pre_existing: bool  # 작업 전부터 저장 안 된 변경이 있던 파일
    additions: int | None = None
    deletions: int | None = None
    binary: bool = False
    size_bytes: int | None = None  # 지금 파일 크기 (삭제된 파일은 없음)


def _kind(code: str) -> str:
    if code == "??" or "A" in code:
        return "added"
    if "D" in code:
        return "deleted"
    if "R" in code:
        return "renamed"
    return "modified"


def task_changes(repo: str, baseline: dict[str, dict[str, str]] | None) -> list[FileChange]:
    """이 작업이 바꾼 파일 목록. baseline이 없으면 지금의 모든 변경을 '작업 전 변경 여부 모름'으로 돌려준다."""
    status = _status(repo)
    hashes = _hashes(repo, list(status))
    changes: list[FileChange] = []
    for path, code in status.items():
        if baseline is None:
            changes.append(FileChange(path, code, _kind(code), pre_existing=True))
            continue
        before = baseline.get(path)
        if before is None:
            changes.append(FileChange(path, code, _kind(code), pre_existing=False))
        elif before.get("hash") != hashes.get(path):
            changes.append(FileChange(path, code, _kind(code), pre_existing=True))

    binary_paths: set[str] = set()
    if changes and _has_head(repo):
        tracked = [c.path for c in changes if c.status != "??"]
        if tracked:
            out = _git(repo, "diff", "HEAD", "--numstat", "-z", "--", *tracked, check=False)
            stats: dict[str, tuple[int | None, int | None]] = {}
            for rec in out.split("\0"):
                cols = rec.split("\t")
                if len(cols) == 3:
                    add, dele, p = cols
                    stats[p] = (int(add) if add.isdigit() else None, int(dele) if dele.isdigit() else None)
                    if add == "-":
                        binary_paths.add(p)
            for c in changes:
                if c.path in stats:
                    c.additions, c.deletions = stats[c.path]
                c.binary = c.path in binary_paths
    for c in changes:
        file = Path(repo) / c.path
        if file.is_file():
            c.size_bytes = file.stat().st_size
        if c.status == "??" and c.additions is None:
            try:
                with file.open("rb") as fh:
                    head = fh.read(8000)
                if b"\0" in head:
                    c.binary = True
                elif (c.size_bytes or 0) <= 5_000_000:
                    data = file.read_bytes()
                    c.additions, c.deletions = data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1), 0
            except OSError:
                pass
    return sorted(changes, key=lambda c: c.path)


def all_changes(repo: str) -> list[FileChange]:
    """프로젝트의 저장 안 된 변경 전부 (작업과 상관없이)."""
    changes = task_changes(repo, None)
    for c in changes:
        c.pre_existing = False
    return changes


def file_diff(repo: str, path: str, status: str) -> str:
    if status == "??" or not _has_head(repo):
        file = Path(repo) / path
        try:
            data = file.read_bytes()
        except OSError:
            return "(파일을 읽을 수 없습니다)"
        if b"\0" in data[:8000]:
            return "(바이너리 파일)"
        lines = data.decode("utf-8", errors="replace").splitlines()
        shown = lines[:NEW_FILE_LINE_LIMIT]
        body = "\n".join("+" + line for line in shown)
        more = f"\n… ({len(lines) - len(shown)}줄 더 있음)" if len(lines) > len(shown) else ""
        return f"새 파일: {path}\n@@ -0,0 +1,{len(lines)} @@\n{body}{more}"
    diff = _git(repo, "diff", "HEAD", "--", path, check=False)
    if not diff.strip():
        return "(내용 변경 없음 — 권한이나 줄바꿈만 바뀌었을 수 있습니다)"
    return diff if len(diff) <= DIFF_LIMIT else diff[:DIFF_LIMIT] + "\n… (diff가 너무 길어 일부만 표시)"


def commit(repo: str, files: list[str], message: str) -> str:
    """지정한 파일만 커밋하고 커밋 해시를 돌려준다. 이미 스테이징돼 있던 다른 파일은 섞지 않는다."""
    if not files:
        raise GitError("커밋할 파일을 하나 이상 고르세요")
    if not message.strip():
        raise GitError("커밋 메시지를 입력하세요")
    _git(repo, "add", "-A", "--", *files)
    _git(repo, "commit", "-F", "-", "--only", "--", *files, stdin=message.strip() + "\n")
    return _git(repo, "rev-parse", "HEAD").strip()


PUSH_TIMEOUT = 120


def push(repo: str) -> str:
    """지금 브랜치를 원격에 올린다. 강제 push는 하지 않는다.

    연결된 원격 브랜치가 없으면 origin 에 같은 이름으로 올리고 연결한다 (-u).
    인증 창을 띄우거나 비밀번호를 묻지 않는다 (GIT_TERMINAL_PROMPT=0).
    """
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if not branch or branch == "HEAD":
        raise GitError("브랜치가 아닌 상태(detached HEAD)라 push할 수 없습니다")
    upstream = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False).strip()
    if upstream:
        args = ["push"]
    else:
        remotes = _git(repo, "remote").split()
        if "origin" not in remotes:
            raise GitError("원격 저장소(origin)가 없습니다. GitHub 저장소를 먼저 연결하세요.")
        args = ["push", "-u", "origin", branch]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        result = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PUSH_TIMEOUT,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"{PUSH_TIMEOUT}초 안에 끝나지 않았습니다. 네트워크나 인증 상태를 확인하세요.") from exc
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        lower = output.lower()
        if "rejected" in lower and ("fetch first" in lower or "non-fast-forward" in lower):
            raise GitError("원격에 내 PC에 없는 커밋이 있어 push가 거부됐습니다. 터미널에서 git pull 후 다시 시도하세요.\n" + output)
        if "authentication" in lower or "could not read username" in lower or "permission denied" in lower or "403" in lower:
            raise GitError("인증이 필요합니다. 터미널에서 한 번 직접 git push 해서 로그인해 두세요.\n" + output)
        raise GitError(output or f"git push 실패 (종료 코드 {result.returncode})")
    return output


def as_dict(change: FileChange) -> dict:
    return asdict(change)
