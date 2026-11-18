"""Claude Code를 프로젝트 폴더에서 실행하고, 출력(stream-json)을 RunEvent로 기록한다.

안전장치
- --restricted: 사용자/프로젝트 설정 파일을 무시하고, 파일 도구를 프로젝트 폴더 안으로 제한한다.
- --strict-mcp-config: MCP 서버를 쓰지 않는다.
- --permission-prompts none: 허용 목록(runner_allowed_tools)에 없는 동작은 자동으로 거부된다.
- --max-budget-usd + 시간 제한 + 동시 실행 수 제한.
- 지시(prompt)는 명령줄이 아니라 표준 입력으로 넘긴다.
"""

import json
import re
import logging
import os
import subprocess
import threading
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from .config import get_settings
from .db import engine
from .gitops import GitError, is_repo, snapshot
from .models import Project, RateLimitSnapshot, Run, RunEvent, Task
from .scanner.sessions import TOOL_INPUT_LIMIT, TOOL_RESULT_LIMIT, TEXT_LIMIT, _text_of, _truncate

log = logging.getLogger(__name__)

_lock = threading.Lock()
_procs: dict[int, subprocess.Popen] = {}
_kill_reasons: dict[int, str] = {}  # run_id -> "stopped" | "timeout"

MAX_STDERR_EVENTS = 50

# 커밋은 사람이 승인한 뒤 WorkPlace가 하므로, Claude에게는 메시지 초안만 남기게 한다.
COMMIT_HINT = (
    "You are running inside JB WorkPlace. You cannot run git add, git commit or git push; "
    "the user reviews the diff and WorkPlace commits after approval. "
    "If you changed any files, end your final message with a suggested commit message in a fenced "
    "code block whose language is `commit` (```commit ... ```). Match the repository's existing "
    "commit message style (check `git log` if needed). Do not include a Co-Authored-By line."
)
_COMMIT_BLOCK = re.compile(r"```commit[^\n]*\n(.*?)```", re.DOTALL)


def extract_commit_message(text: str) -> str | None:
    blocks = _COMMIT_BLOCK.findall(text or "")
    return blocks[-1].strip() or None if blocks else None


# 다른 프로젝트(또는 이 프로젝트)에 작업을 추가하는 통로. Claude는 제안만 하고, 사람이 확인한 뒤 등록한다.
TASKS_HINT = (
    "JB WorkPlace can also hold tasks for other projects. You cannot create tasks yourself. "
    "Only when the user asks you to add or create tasks, end your final message with a fenced code "
    "block whose language is `workplace-tasks` containing a JSON array of objects with keys "
    '"project" (exact project name from the list below), "title" (short) and "prompt" (the full '
    "instruction). Each proposed task runs later in its own project folder and cannot see this "
    "conversation or this folder, so write each prompt so it stands on its own (name the files to read "
    "and the output to write). The user reviews and registers the proposals. Do not create the tasks "
    "any other way. Registered projects: "
)
_TASKS_BLOCK = re.compile(r"```workplace-tasks[^\n]*\n(.*?)```", re.DOTALL)
MAX_PROPOSALS = 30
MAX_HINT_PROJECTS = 200


def tasks_hint(project_names: list[str]) -> str:
    names = sorted(set(project_names), key=str.lower)[:MAX_HINT_PROJECTS]
    return TASKS_HINT + (", ".join(json.dumps(n, ensure_ascii=False) for n in names) or "(none)") + "."


def extract_task_proposals(text: str) -> list[dict[str, Any]] | None:
    """마지막 ```workplace-tasks 블록의 JSON 배열을 읽는다. 형식이 틀리면 None."""
    blocks = _TASKS_BLOCK.findall(text or "")
    if not blocks:
        return None
    try:
        data = json.loads(blocks[-1])
    except ValueError:
        log.info("workplace-tasks 블록의 JSON을 읽지 못함")
        return None
    if isinstance(data, dict):
        data = data.get("tasks")
    if not isinstance(data, list):
        return None
    out = []
    for item in data[:MAX_PROPOSALS]:
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "").strip()[:20000]
        if not prompt:
            continue
        out.append({
            "project": str(item.get("project") or "").strip()[:200],
            "title": str(item.get("title") or "").strip()[:200] or make_title(prompt),
            "prompt": prompt,
            "task_id": None,
        })
    return out or None


class RunnerError(Exception):
    """실행을 시작할 수 없을 때 (사용자에게 그대로 보여줄 메시지)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(UTC)


def make_title(prompt: str) -> str:
    first = next((line.strip() for line in prompt.splitlines() if line.strip()), "새 작업")
    return first if len(first) <= 60 else first[:57] + "…"


def running_count(db: Session) -> int:
    return db.exec(select(func.count()).select_from(Run).where(Run.status == "running")).one()


MAX_BUDGET_CAP_USD = 50.0  # 작업별 한도로 고를 수 있는 최댓값
MAX_MINUTES_CAP = 480

# 한도에 걸려 멈춘 뒤 [이어서 계속]을 누르면 보내는 지시
CONTINUE_PROMPT = "이전 실행이 실행 한도(비용 또는 시간)에 걸려 중간에 멈췄습니다. 멈춘 지점부터 이어서 작업을 끝까지 계속해 주세요."


def effective_limits(task: Task) -> tuple[float, int]:
    s = get_settings()
    budget = task.max_budget_usd if task.max_budget_usd else s.runner_max_budget_usd
    minutes = task.max_minutes if task.max_minutes else s.runner_max_minutes
    return min(budget, MAX_BUDGET_CAP_USD), min(minutes, MAX_MINUTES_CAP)


def _build_args(exe: str, task: Task, resume: str | None, budget: float, project_names: list[str]) -> list[str]:
    s = get_settings()
    args = [
        exe, "-p",
        "--output-format", "stream-json", "--verbose",
        "--restricted", "--strict-mcp-config",
        "--tools", s.runner_tools,
        "--permission-mode", "manual",
        "--permission-prompts", "none",
        "--allowedTools", s.runner_allowed_tools,
        "--disallowedTools", s.runner_disallowed_tools,
        "--max-budget-usd", f"{budget:g}",
        "--name", f"WorkPlace #{task.id}: {task.title}"[:120],
        "--append-system-prompt", COMMIT_HINT + "\n\n" + tasks_hint(project_names),
    ]
    if s.runner_model:
        args += ["--model", s.runner_model]
    if resume:
        args += ["--resume", resume]
    return args


# ---------------------------------------------------------------- 시작 / 중단


def start_run(task_id: int, prompt: str | None = None) -> Run:
    """작업을 실행한다. prompt가 없으면 작업의 원래 지시를 쓴다 (첫 실행)."""
    settings = get_settings()
    exe = settings.resolved_claude_exe
    if not exe:
        raise RunnerError("claude 실행 파일을 찾지 못했습니다. backend/.env 의 CLAUDE_EXE 를 설정하세요.", 503)

    with _lock:
        with Session(engine) as db:
            task = db.get(Task, task_id)
            if task is None:
                raise RunnerError("작업을 찾을 수 없습니다", 404)
            project = db.get(Project, task.project_id)
            if project is None or not project.exists or not Path(project.path).is_dir():
                raise RunnerError("프로젝트 폴더가 없습니다. [다시 스캔] 후 확인하세요.", 409)
            if task.status == "running":
                raise RunnerError("이 작업은 이미 실행 중입니다", 409)
            if running_count(db) >= settings.runner_max_concurrent:
                raise RunnerError(
                    f"동시에 {settings.runner_max_concurrent}개까지만 실행할 수 있습니다. 실행 중인 작업이 끝난 뒤 다시 시도하세요.",
                    409,
                )
            resume = task.session_id
            text = (prompt or "").strip() or (task.prompt if resume is None else "")
            if not text:
                raise RunnerError("지시 내용을 입력하세요")

            if task.baseline is None and is_repo(project.path):
                # 첫 실행 직전의 변경 상태를 기록해 두고, 나중에 이 작업이 바꾼 파일만 가려낸다.
                try:
                    task.baseline = snapshot(project.path)
                except GitError as exc:
                    log.info("변경 추적 기준을 만들지 못함 (task %s): %s", task.id, exc)

            budget, minutes = effective_limits(task)
            run = Run(
                task_id=task.id,
                prompt=text,
                status="running",
                started_at=_now(),
                resumed_from=resume,
                max_budget_usd=budget,
                max_minutes=minutes,
            )
            task.status = "running"
            task.updated_at = _now()
            db.add(run)
            db.add(task)
            db.commit()
            db.refresh(run)
            db.refresh(task)
            run_id, cwd = run.id, project.path
            project_names = list(db.exec(
                select(Project.name).where(Project.exists == True, Project.hidden == False)  # noqa: E712
            ).all())
            args = _build_args(exe, task, resume, budget, project_names)

        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            proc = subprocess.Popen(
                args,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
            )
        except OSError as exc:
            _finish(run_id, status="failed", error=f"claude 실행 실패: {exc}", stop_reason="error")
            raise RunnerError(f"claude 실행 실패: {exc}", 500) from exc

        _procs[run_id] = proc
        with Session(engine) as db:
            row = db.get(Run, run_id)
            row.pid = proc.pid
            db.add(row)
            db.commit()
            db.refresh(row)
            result = row

    threading.Thread(
        target=_watch, args=(run_id, proc, text, budget, minutes), daemon=True, name=f"run-{run_id}"
    ).start()
    return result


def stop_run(run_id: int) -> bool:
    proc = _procs.get(run_id)
    if proc is None or proc.poll() is not None:
        return False
    _kill(run_id, "stopped")
    return True


def _kill(run_id: int, reason: str) -> None:
    proc = _procs.get(run_id)
    if proc is None:
        return
    _kill_reasons.setdefault(run_id, reason)
    _kill_tree(proc.pid)


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


# ---------------------------------------------------------------- 출력 처리


class _EventWriter:
    def __init__(self, run_id: int):
        self.run_id = run_id
        self.seq = 0

    def add(self, kind: str, payload: dict[str, Any]) -> None:
        with Session(engine) as db:
            db.add(RunEvent(run_id=self.run_id, seq=self.seq, ts=_now(), kind=kind, payload=payload))
            db.commit()
        self.seq += 1


def _tool_summary(name: str, tool_input: dict[str, Any]) -> str:
    for key in ("command", "file_path", "pattern", "path", "url", "description"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value if len(value) <= 160 else value[:157] + "…"
    return ""


def _update_run(run_id: int, **fields: Any) -> None:
    with Session(engine) as db:
        row = db.get(Run, run_id)
        for key, value in fields.items():
            setattr(row, key, value)
        db.add(row)
        db.commit()


def _handle_line(run_id: int, line: str, writer: _EventWriter, state: dict[str, Any]) -> None:
    line = line.strip()
    if not line:
        return
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        writer.add("stderr", {"text": _truncate(line, TOOL_RESULT_LIMIT)})
        return
    if not isinstance(msg, dict):
        return
    mtype = msg.get("type")

    if mtype == "system" and msg.get("subtype") == "init":
        state["session_id"] = msg.get("session_id")
        _update_run(run_id, session_id=msg.get("session_id"), model=msg.get("model"))
        writer.add("init", {"session_id": msg.get("session_id"), "model": msg.get("model"), "tools": msg.get("tools", [])})
        return

    if mtype == "assistant":
        message = msg.get("message") or {}
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text", "").strip():
                writer.add("text", {"text": _truncate(block["text"], TEXT_LIMIT)})
            elif block.get("type") == "tool_use":
                tool_input = block.get("input") or {}
                writer.add("tool_use", {
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "summary": _tool_summary(block.get("name", ""), tool_input),
                    "input": _truncate(json.dumps(tool_input, ensure_ascii=False, indent=2), TOOL_INPUT_LIMIT),
                })
        return

    if mtype == "user":
        message = msg.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    raw = block.get("content")
                    text = raw if isinstance(raw, str) else _text_of(raw)
                    writer.add("tool_result", {
                        "tool_use_id": block.get("tool_use_id"),
                        "text": _truncate(text or "", TOOL_RESULT_LIMIT),
                        "is_error": bool(block.get("is_error")),
                    })
        return

    if mtype == "result":
        usage = msg.get("usage") or {}
        state["result"] = msg
        denials = [
            {"tool": d.get("tool_name"), "summary": _tool_summary(d.get("tool_name", ""), d.get("tool_input") or {})}
            for d in msg.get("permission_denials") or []
            if isinstance(d, dict)
        ]
        _update_run(
            run_id,
            session_id=msg.get("session_id") or state.get("session_id"),
            num_turns=msg.get("num_turns"),
            cost_usd=msg.get("total_cost_usd"),
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cache_creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
            cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
        )
        writer.add("result", {
            "subtype": msg.get("subtype"),
            "is_error": bool(msg.get("is_error")),
            "text": _truncate(str(msg.get("result") or ""), TEXT_LIMIT),
            "cost_usd": msg.get("total_cost_usd"),
            "num_turns": msg.get("num_turns"),
            "duration_ms": msg.get("duration_ms"),
            "denials": denials,
        })
        return

    if mtype == "rate_limit_event":
        _save_rate_limit(run_id, msg.get("rate_limit_info") or {})
    # task_summary 같은 나머지 메시지는 화면에 필요 없어 버린다.


def _epoch(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value), tz=UTC) if value else None
    except (TypeError, ValueError, OSError):
        return None


def _save_rate_limit(run_id: int, info: dict[str, Any]) -> None:
    windows = info.get("unifiedWindows") or {}
    five = windows.get("five_hour") or {}
    seven = windows.get("seven_day") or {}
    if not five and not seven:
        return
    with Session(engine) as db:
        db.add(RateLimitSnapshot(
            ts=_now(),
            run_id=run_id,
            status=info.get("status"),
            five_hour_utilization=five.get("utilization"),
            five_hour_resets_at=_epoch(five.get("resetsAt")),
            seven_day_utilization=seven.get("utilization"),
            seven_day_resets_at=_epoch(seven.get("resetsAt")),
            overage_status=info.get("overageStatus"),
        ))
        db.commit()


def _watch(run_id: int, proc: subprocess.Popen, prompt: str, budget: float, minutes: int) -> None:
    writer = _EventWriter(run_id)
    state: dict[str, Any] = {}
    stderr_tail: deque[str] = deque(maxlen=20)

    def read_stderr() -> None:
        sent = 0
        for raw in proc.stderr:
            text = raw.rstrip()
            if not text:
                continue
            stderr_tail.append(text)
            if sent < MAX_STDERR_EVENTS:
                writer.add("stderr", {"text": _truncate(text, TOOL_RESULT_LIMIT)})
                sent += 1

    timer = threading.Timer(minutes * 60, _kill, args=(run_id, "timeout"))
    timer.daemon = True
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    try:
        timer.start()
        stderr_thread.start()
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except OSError as exc:
            writer.add("error", {"text": f"지시를 전달하지 못했습니다: {exc}"})
        for line in proc.stdout:
            try:
                _handle_line(run_id, line, writer, state)
            except Exception:  # 한 줄 처리 실패가 실행 전체를 멈추지 않게 한다
                log.exception("출력 처리 실패 (run %s)", run_id)
        code = proc.wait()
        stderr_thread.join(timeout=5)
    finally:
        timer.cancel()
        _procs.pop(run_id, None)

    reason = _kill_reasons.pop(run_id, None)
    result = state.get("result")
    stop_reason: str | None = None
    if reason == "stopped":
        status, error, stop_reason = "stopped", "사용자가 중단했습니다", "stopped"
    elif reason == "timeout":
        status, error, stop_reason = "failed", f"시간 한도({minutes}분)를 넘어 멈췄습니다. [이어서 계속]으로 이어 갈 수 있습니다.", "timeout"
    elif result is None:
        tail = " / ".join(list(stderr_tail)[-3:])
        status, error, stop_reason = "failed", f"결과 없이 종료됐습니다 (종료 코드 {code}){': ' + tail if tail else ''}", "error"
    elif result.get("subtype") == "error_max_budget_usd" or result.get("terminal_reason") == "budget_exhausted":
        status, error, stop_reason = "failed", f"비용 한도(${budget:g})에 도달해 멈췄습니다. [이어서 계속]으로 이어 갈 수 있습니다.", "budget"
    elif result.get("is_error") or result.get("subtype") != "success":
        status, error, stop_reason = "failed", f"{result.get('subtype')}: {str(result.get('result') or '')[:300]}", "error"
    else:
        status, error = "succeeded", None
    if error:
        writer.add("error", {"text": error, "stop_reason": stop_reason})
    final_text = str((result or {}).get("result") or "")
    _finish(
        run_id,
        status=status,
        error=error,
        stop_reason=stop_reason,
        exit_code=code,
        session_id=state.get("session_id"),
        commit_message=extract_commit_message(final_text),
        proposals=extract_task_proposals(final_text),
    )

    # 이번 실행의 세션 기록도 색인하도록 스캔을 한 번 돌린다.
    from .sync import run_scan

    threading.Thread(target=_safe_scan, args=(run_scan,), daemon=True).start()


def _safe_scan(run_scan) -> None:
    try:
        run_scan()
    except Exception:
        log.exception("실행 후 스캔 실패")


def _finish(run_id: int, *, status: str, error: str | None, exit_code: int | None = None,
            session_id: str | None = None, commit_message: str | None = None,
            stop_reason: str | None = None, proposals: list[dict[str, Any]] | None = None) -> None:
    with Session(engine) as db:
        run = db.get(Run, run_id)
        run.status = status
        run.error = error
        run.stop_reason = stop_reason
        run.exit_code = exit_code
        run.ended_at = _now()
        if session_id and not run.session_id:
            run.session_id = session_id
        task = db.get(Task, run.task_id)
        task.status = "review" if status == "succeeded" else "failed"
        if commit_message:
            task.commit_message = commit_message
        if proposals:
            # 이미 등록한 제안은 남기고, 새 제안을 뒤에 붙인다.
            kept = [p for p in (task.proposals or []) if p.get("task_id")]
            task.proposals = kept + proposals
        if run.session_id:
            task.session_id = run.session_id
        task.updated_at = _now()
        db.add(run)
        db.add(task)
        db.commit()


# ---------------------------------------------------------------- 서버 시작 시 정리


def _is_claude_process(pid: int) -> bool:
    if os.name != "nt":
        return False
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True)
    return "claude" in (out.stdout or "").lower()


def recover_orphans() -> None:
    """서버가 꺼질 때 실행 중이던 작업을 실패로 표시하고, 남은 claude 프로세스를 끝낸다."""
    with Session(engine) as db:
        runs = db.exec(select(Run).where(Run.status == "running")).all()
        for run in runs:
            if run.id in _procs:
                continue
            if run.pid and _is_claude_process(run.pid):
                _kill_tree(run.pid)
            run.status = "failed"
            run.error = "서버가 다시 시작되어 실행이 중단됐습니다"
            run.stop_reason = "restart"
            run.ended_at = _now()
            db.add(run)
            task = db.get(Task, run.task_id)
            if task:
                # [이어서 계속]과 "터미널에서 이어서 하기"가 이 세션을 쓸 수 있게 작업에도 남긴다.
                if run.session_id:
                    task.session_id = run.session_id
                if task.status == "running":
                    task.status = "failed"
                task.updated_at = _now()
                db.add(task)
        # 예전에 이 처리가 없어서 세션이 비어 있는 작업은 마지막 실행의 세션으로 채운다.
        for task in db.exec(select(Task).where(Task.session_id == None)).all():  # noqa: E711
            last = db.exec(
                select(Run).where(Run.task_id == task.id, Run.session_id != None).order_by(Run.id.desc()).limit(1)  # noqa: E711
            ).first()
            if last:
                task.session_id = last.session_id
                db.add(task)
        db.commit()
        if runs:
            log.warning("중단된 실행 %d개를 정리했습니다", len(runs))


# ---------------------------------------------------------------- 사용 한도 지금 확인


def check_rate_limit() -> tuple[bool, float | None, dict[str, int]]:
    """가장 가벼운 모델로 한 단어짜리 실행을 해서 Claude가 알려주는 사용 한도를 받아 저장한다.

    (저장했는지, 환산 비용, 토큰 사용량)을 돌려준다. 도구 없음, 세션 기록 남기지 않음.
    """
    exe = get_settings().resolved_claude_exe
    if not exe:
        raise RunnerError("claude 실행 파일을 찾지 못했습니다", 503)
    args = [
        exe, "-p", "--output-format", "stream-json", "--verbose",
        "--restricted", "--strict-mcp-config", "--tools", "",
        "--permission-mode", "manual", "--permission-prompts", "none",
        "--no-session-persistence", "--model", "haiku", "--max-budget-usd", "0.05",
    ]
    try:
        proc = subprocess.run(
            args, input="Reply with the single word: ok", capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError(f"사용 한도를 확인하지 못했습니다: {exc}", 502) from exc
    saved, cost, tokens = False, None, {}
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "rate_limit_event":
            _save_rate_limit(None, msg.get("rate_limit_info") or {})
            saved = True
        elif msg.get("type") == "result":
            cost = msg.get("total_cost_usd")
            u = msg.get("usage") or {}
            tokens = {
                "model": next(iter(msg.get("modelUsage") or {}), None),
                "input_tokens": int(u.get("input_tokens") or 0),
                "output_tokens": int(u.get("output_tokens") or 0),
                "cache_write_tokens": int(u.get("cache_creation_input_tokens") or 0),
                "cache_read_tokens": int(u.get("cache_read_input_tokens") or 0),
            }
    if not saved:
        raise RunnerError("Claude가 사용 한도 정보를 보내지 않았습니다. 잠시 뒤 다시 시도하세요.", 502)
    return saved, cost, tokens
