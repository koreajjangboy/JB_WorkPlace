"""고른 파일의 변경 내용을 Claude가 읽고 커밋 메시지 초안을 쓴다.

파일을 고치지 않는 읽기 전용 실행이다.
- --restricted, --strict-mcp-config, 허용 목록 밖 동작은 자동 거부
- Edit/Write 도구는 아예 주지 않는다
- --no-session-persistence: 세션 기록을 남기지 않는다
"""

import json
import re
import os
import subprocess

from .config import get_settings
from .runner import extract_commit_message

TIMEOUT_SECONDS = 180
MAX_LISTED_FILES = 200
_CLAUDE_TRAILER = re.compile(r"^Co-Authored-By:.*\b(Claude|anthropic\.com)\b", re.IGNORECASE)


class CommitMessageError(Exception):
    pass


def _prompt(files: list[dict]) -> str:
    lines = []
    for f in files[:MAX_LISTED_FILES]:
        extra = []
        if f.get("binary"):
            extra.append("binary")
        if f.get("size_bytes") is not None:
            extra.append(f"{f['size_bytes']:,} bytes")
        lines.append(f"- [{f['kind']}] {f['path']}" + (f" ({', '.join(extra)})" if extra else ""))
    more = f"\n- … and {len(files) - MAX_LISTED_FILES} more files" if len(files) > MAX_LISTED_FILES else ""
    return (
        "Write a git commit message for committing exactly these files in this repository:\n"
        + "\n".join(lines)
        + more
        + "\n\nLook at what changed (git diff HEAD -- <file> for tracked files, read new text files; "
        "for binary files use only their names and sizes). Run `git log --oneline -10` and match the "
        "repository's existing commit message style and language. Do not modify any files. "
        "Do not add a Co-Authored-By line.\n"
        "Reply with only the commit message inside a fenced code block whose language is `commit`."
    )


def draft_commit_message(repo: str, files: list[dict]) -> tuple[str, float | None]:
    """(메시지, 환산 비용)을 돌려준다."""
    s = get_settings()
    exe = s.resolved_claude_exe
    if not exe:
        raise CommitMessageError("claude 실행 파일을 찾지 못했습니다")
    args = [
        exe, "-p",
        "--output-format", "json",
        "--restricted", "--strict-mcp-config",
        "--tools", "Read,Glob,Grep,Bash",
        "--permission-mode", "manual",
        "--permission-prompts", "none",
        "--allowedTools", "Read,Glob,Grep,Bash(git diff*),Bash(git log*),Bash(git status*),Bash(git show*)",
        "--disallowedTools", s.runner_disallowed_tools,
        "--max-budget-usd", f"{s.commit_message_budget_usd:g}",
        "--no-session-persistence",
    ]
    if s.commit_message_model:
        args += ["--model", s.commit_message_model]
    try:
        result = subprocess.run(
            args,
            cwd=repo,
            input=_prompt(files),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommitMessageError(f"{TIMEOUT_SECONDS}초 안에 끝나지 않았습니다") from exc
    except OSError as exc:
        raise CommitMessageError(f"claude 실행 실패: {exc}") from exc

    try:
        data = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
    except (json.JSONDecodeError, IndexError):
        data = {}
    text = str(data.get("result") or "")
    if result.returncode != 0 or data.get("is_error") or not text:
        detail = text or (result.stderr or "").strip()[-300:] or f"종료 코드 {result.returncode}"
        raise CommitMessageError(f"메시지를 만들지 못했습니다: {detail}")
    usage = data.get("usage") or {}
    _last.clear()
    _last.update(
        model=next(iter(data.get("modelUsage") or {}), None),
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_write_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
    )
    message = extract_commit_message(text) or text.strip().strip("`").strip()
    # 지시를 어기고 Claude 공동 작성자 줄을 붙였으면 뺀다 (커밋은 사람이 승인해서 하는 것).
    lines = [line for line in message.splitlines() if not _CLAUDE_TRAILER.match(line.strip())]
    return "\n".join(lines).strip(), data.get("total_cost_usd")


def last_usage() -> dict:
    """가장 최근 draft_commit_message 실행의 토큰 사용량 (사용량 기록용)."""
    return dict(_last)


_last: dict = {}
