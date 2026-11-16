"""Claude Code 세션 기록(~/.claude/projects/<폴더>/<sessionId>.jsonl)을 읽는다.

- summarize_session: 목록 화면용 요약 (제목, 시각, 메시지 수, 토큰)
- read_transcript: 대화 보기 화면용 메시지 목록
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

TEXT_LIMIT = 4000
TOOL_INPUT_LIMIT = 1500
TOOL_RESULT_LIMIT = 2000
FIRST_PROMPT_LIMIT = 300


@dataclass
class SessionSummary:
    id: str
    file_path: str
    file_mtime: float
    cwd: str | None = None
    git_branch: str | None = None
    title: str | None = None
    first_prompt: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    user_messages: int = 0
    assistant_messages: int = 0
    models: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float | None = None


def list_session_files(claude_projects_dir: Path) -> list[Path]:
    """각 프로젝트 폴더 바로 아래의 .jsonl만 고른다 (하위 에이전트 기록 폴더는 제외)."""
    if not claude_projects_dir.is_dir():
        return []
    files: list[Path] = []
    for project_dir in claude_projects_dir.iterdir():
        if project_dir.is_dir():
            files.extend(p for p in project_dir.glob("*.jsonl") if p.is_file())
    return files


def _iter_lines(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _text_of(content: Any) -> str:
    """메시지 content(문자열 또는 블록 목록)에서 text 블록만 이어 붙인다."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p)
    return ""


def _has_tool_result(content: Any) -> bool:
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    )


def _is_human_prompt(record: dict[str, Any]) -> bool:
    """사람이 직접 입력한 메시지인지 (도구 결과, 메타 메시지, 하위 에이전트 메시지는 제외)."""
    if record.get("type") != "user" or record.get("isMeta") or record.get("isSidechain"):
        return False
    message = record.get("message")
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if _has_tool_result(content):
        return False
    return bool(_text_of(content).strip())


def _looks_like_command(text: str) -> bool:
    return text.lstrip().startswith("<")


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n… ({len(text) - limit}자 생략)"


def summarize_session(path: Path) -> SessionSummary | None:
    summary = SessionSummary(id=path.stem, file_path=str(path), file_mtime=path.stat().st_mtime)
    ai_title: str | None = None
    custom_title: str | None = None
    seen_message_ids: set[str] = set()
    models: dict[str, None] = {}
    found_any = False

    for record in _iter_lines(path):
        rtype = record.get("type")

        if rtype == "custom-title" and record.get("customTitle"):
            custom_title = record["customTitle"]
            continue
        if rtype == "ai-title" and record.get("aiTitle"):
            ai_title = record["aiTitle"]
            continue
        if rtype == "cost-state" and isinstance(record.get("totalCostUSD"), (int, float)):
            summary.cost_usd = float(record["totalCostUSD"])
            continue
        if rtype not in ("user", "assistant"):
            continue

        found_any = True
        if record.get("sessionId"):
            summary.id = record["sessionId"]
        if summary.cwd is None and record.get("cwd"):
            summary.cwd = record["cwd"]
        if record.get("gitBranch"):
            summary.git_branch = record["gitBranch"]

        ts = _parse_ts(record.get("timestamp"))
        if ts:
            if summary.started_at is None or ts < summary.started_at:
                summary.started_at = ts
            if summary.ended_at is None or ts > summary.ended_at:
                summary.ended_at = ts

        if rtype == "user":
            if _is_human_prompt(record):
                text = _text_of(record["message"]["content"]).strip()
                if not _looks_like_command(text):
                    summary.user_messages += 1
                    if summary.first_prompt is None:
                        summary.first_prompt = _truncate(text, FIRST_PROMPT_LIMIT)
            continue

        # assistant: 같은 응답(message.id)이 블록마다 여러 줄로 나뉘어 기록되므로 한 번만 센다.
        if record.get("isSidechain"):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        message_id = message.get("id")
        if message_id and message_id in seen_message_ids:
            continue
        if message_id:
            seen_message_ids.add(message_id)
        summary.assistant_messages += 1
        model = message.get("model")
        if model and not model.startswith("<"):
            models[model] = None
        usage = message.get("usage")
        if isinstance(usage, dict):
            summary.input_tokens += int(usage.get("input_tokens") or 0)
            summary.output_tokens += int(usage.get("output_tokens") or 0)
            summary.cache_creation_tokens += int(usage.get("cache_creation_input_tokens") or 0)
            summary.cache_read_tokens += int(usage.get("cache_read_input_tokens") or 0)

    if not found_any:
        return None
    summary.models = list(models)
    summary.title = custom_title or ai_title or (
        summary.first_prompt.splitlines()[0][:80] if summary.first_prompt else None
    )
    return summary


def read_transcript(path: Path) -> list[dict[str, Any]]:
    """대화 보기용 메시지 목록. 하위 에이전트 메시지와 생각(thinking) 블록은 뺀다."""
    entries: list[dict[str, Any]] = []
    for record in _iter_lines(path):
        rtype = record.get("type")
        if rtype not in ("user", "assistant") or record.get("isSidechain"):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        ts = record.get("timestamp")
        content = message.get("content")

        if rtype == "user":
            if record.get("isMeta"):
                continue
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    raw = block.get("content")
                    text = raw if isinstance(raw, str) else _text_of(raw)
                    entries.append({
                        "kind": "tool_result",
                        "ts": ts,
                        "text": _truncate(text or "", TOOL_RESULT_LIMIT),
                        "is_error": bool(block.get("is_error")),
                    })
            if _is_human_prompt(record):
                text = _text_of(content).strip()
                entries.append({
                    "kind": "command" if _looks_like_command(text) else "user",
                    "ts": ts,
                    "text": _truncate(text, TEXT_LIMIT),
                })
            continue

        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and block.get("text", "").strip():
                entries.append({
                    "kind": "assistant",
                    "ts": ts,
                    "text": _truncate(block["text"], TEXT_LIMIT),
                    "model": message.get("model"),
                })
            elif btype == "tool_use":
                tool_input = json.dumps(block.get("input", {}), ensure_ascii=False, indent=2)
                entries.append({
                    "kind": "tool_use",
                    "ts": ts,
                    "tool_name": block.get("name"),
                    "text": _truncate(tool_input, TOOL_INPUT_LIMIT),
                })
    return entries
