"""Gemini 앱(웹·모바일) 사용량: Google Takeout의 'Gemini 앱 활동' 내보내기 파일에서 추정한다.

Gemini 앱에는 사용량을 알려주는 API가 없다. 대신 Takeout으로 받은 활동 기록(JSON)에
질문과 답이 들어 있으므로, 글자 수로 토큰 수를 어림해서 날짜별로 저장한다.

- 파일: takeout-*.zip (또는 그 안의 활동 JSON). zip 안에서 경로에 'gemini'가 들어간 활동 JSON을 찾는다.
- 내보낼 때 '내 활동'의 형식을 JSON으로 골라야 한다 (기본값 HTML은 날짜가 언어마다 달라 읽지 않는다).
- 지켜보는 폴더(TAKEOUT_DIRS)에 새 zip이 생기면 자동으로 가져온다. Takeout의 '2개월마다 내보내기'를
  Google Drive로 받고 Drive 데스크톱 앱이 이 PC에 동기화하면 손대지 않아도 들어온다.
- 다시 가져오면 그 파일이 담은 기간의 날짜만 새 값으로 바꾼다 (그보다 오래된 기록은 남는다).
"""

import html
import io
import json
import logging
import re
import threading
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session, select

from .config import BACKEND_DIR, get_settings
from .db import engine
from .models import UsageRecord
from .usage import get_or_create_provider

log = logging.getLogger(__name__)

PROVIDER = "gemini-app"
STATE_FILE = BACKEND_DIR / "data" / "takeout_state.json"
_lock = threading.Lock()
_TAG = re.compile(r"<[^>]+>")


class TakeoutError(ValueError):
    pass


def estimate_tokens(text: str) -> int:
    """글자 수로 어림한 토큰 수. 영문·숫자는 약 4글자, 한글 등은 약 1.5글자에 1토큰."""
    if not text:
        return 0
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    other = len(text) - ascii_chars
    return round(ascii_chars / 4 + other / 1.5)


def _html_text(fragment: str) -> str:
    return html.unescape(_TAG.sub(" ", fragment)).strip()


def _activity_json(data: bytes, name: str) -> list[dict[str, Any]]:
    """zip이든 JSON이든 받아서 Gemini 활동 항목 목록을 돌려준다."""
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if "gemini" in n.lower()]
            jsons = [n for n in names if n.lower().endswith(".json")]
            if not jsons:
                if any(n.lower().endswith(".html") for n in names):
                    raise TakeoutError("Gemini 활동이 HTML 형식입니다. Takeout에서 '내 활동'의 형식을 JSON으로 바꿔 다시 내보내세요.")
                raise TakeoutError("zip 안에 Gemini 앱 활동이 없습니다. Takeout에서 '내 활동 → Gemini 앱'을 선택했는지 확인하세요.")
            items: list[dict[str, Any]] = []
            for n in jsons:
                parsed = json.loads(zf.read(n).decode("utf-8-sig"))
                if isinstance(parsed, list):
                    items.extend(parsed)
            return items
    try:
        parsed = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise TakeoutError(f"{name}: Takeout zip이나 활동 JSON 파일이 아닙니다") from e
    if not isinstance(parsed, list):
        raise TakeoutError(f"{name}: 활동 JSON 형식이 아닙니다")
    return parsed


def summarize(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{로컬 날짜: {prompts, input_tokens, output_tokens, last}}. 답이 붙은 항목만 대화 한 번으로 센다."""
    days: dict[str, dict[str, Any]] = defaultdict(lambda: {"prompts": 0, "input_tokens": 0, "output_tokens": 0, "files": 0, "last": None})
    for item in items:
        if not isinstance(item, dict) or not item.get("time"):
            continue
        responses = item.get("safeHtmlItem") or []
        if not responses:
            continue  # 설정 변경·피드백 같은 기록
        try:
            ts = datetime.fromisoformat(str(item["time"]).replace("Z", "+00:00")).astimezone()
        except ValueError:
            continue
        # 제목은 "Prompted <질문>" 형태 (언어에 따라 앞말이 다르다). 앞말 몇 글자는 어림에 큰 영향이 없다.
        prompt = str(item.get("title") or "")
        answer = " ".join(_html_text(str(r.get("html", ""))) for r in responses if isinstance(r, dict))
        d = days[ts.date().isoformat()]
        d["prompts"] += 1
        d["input_tokens"] += estimate_tokens(prompt)
        d["output_tokens"] += estimate_tokens(answer)
        d["files"] += len(item.get("attachedFiles") or []) + (1 if item.get("imageFile") else 0)
        if d["last"] is None or ts > d["last"]:
            d["last"] = ts
    return dict(days)


def import_bytes(data: bytes, name: str = "upload") -> dict[str, Any]:
    days = summarize(_activity_json(data, name))
    if not days:
        raise TakeoutError("Gemini 대화 기록이 없습니다. 'Gemini 앱 활동'이 꺼져 있으면 기록이 남지 않습니다.")
    first, last = min(days), max(days)
    with _lock, Session(engine) as db:
        provider = get_or_create_provider(db, PROVIDER)
        # 이 파일이 담은 기간은 새 값으로 바꾼다. (같은 날을 다시 가져와도 두 번 세지 않는다)
        db.exec(delete(UsageRecord).where(
            UsageRecord.provider_id == provider.id,
            UsageRecord.source == "takeout",
            UsageRecord.source_ref >= f"takeout:{PROVIDER}:{first}",
            UsageRecord.source_ref <= f"takeout:{PROVIDER}:{last}",
        ))
        for day, d in sorted(days.items()):
            tokens = d["input_tokens"] + d["output_tokens"]
            db.add(UsageRecord(
                provider_id=provider.id,
                ts=d["last"],
                kind="text",
                unit="token",
                quantity=tokens,
                input_tokens=d["input_tokens"],
                output_tokens=d["output_tokens"],
                source="takeout",
                source_ref=f"takeout:{PROVIDER}:{day}",
                meta={"prompts": d["prompts"], "files": d["files"], "estimated": True, "file": name},
            ))
        db.commit()
    result = {
        "file": name,
        "days": len(days),
        "prompts": sum(d["prompts"] for d in days.values()),
        "tokens": sum(d["input_tokens"] + d["output_tokens"] for d in days.values()),
        "first": first,
        "last": last,
        "imported_at": datetime.now().astimezone().isoformat(),
    }
    state = _load_state()
    state["last_import"] = result
    _save_state(state)
    log.info("Gemini Takeout 가져옴: %s", result)
    return result


# ---------------------------------------------------------------- 폴더 지켜보기


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def watch_dirs() -> list[Path]:
    return get_settings().takeout_dir_paths


def _candidates() -> list[Path]:
    files: list[Path] = []
    for d in watch_dirs():
        if d.is_dir():
            files.extend(p for p in d.glob("takeout-*.zip") if p.is_file())
    return sorted(files, key=lambda p: p.stat().st_mtime)


def scan_dirs() -> list[dict[str, Any]]:
    """지켜보는 폴더에서 아직 안 가져온 Takeout zip을 가져온다. Gemini 활동이 없는 zip은 건너뛴다."""
    state = _load_state()
    seen: dict[str, float] = state.get("seen", {})
    results: list[dict[str, Any]] = []
    for path in _candidates():
        key = str(path).lower()
        mtime = path.stat().st_mtime
        if seen.get(key) == mtime:
            continue
        try:
            results.append(import_bytes(path.read_bytes(), path.name))
        except TakeoutError as e:
            log.info("Takeout 건너뜀 %s: %s", path.name, e)
        except (OSError, zipfile.BadZipFile) as e:
            log.warning("Takeout 읽기 실패 %s: %s", path.name, e)
            continue  # 동기화 중인 파일일 수 있으니 다음에 다시 본다
        state = _load_state()
        state.setdefault("seen", {})[key] = mtime
        _save_state(state)
    return results


def status() -> dict[str, Any]:
    state = _load_state()
    return {
        "dirs": [{"path": str(d), "exists": d.is_dir()} for d in watch_dirs()],
        "last_import": state.get("last_import"),
    }


def watch_forever(interval_seconds: int = 600) -> None:
    """백그라운드 스레드: 10분마다 폴더를 확인한다."""
    import time

    while True:
        try:
            scan_dirs()
        except Exception:
            log.exception("Takeout 폴더 확인 실패")
        time.sleep(interval_seconds)
