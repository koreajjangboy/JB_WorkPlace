"""OpenAI API 사용량: 조직의 Usage API·Costs API에서 가져온다 (Admin API 키 필요).

- 비용: GET /v1/organization/costs (하루 단위, 프로젝트·항목별) → 실제 청구 금액(USD)
- 토큰: GET /v1/organization/usage/completions (하루 단위, 모델·프로젝트별) → 입력·캐시·출력 토큰과 요청 수
  토큰 기록은 비용을 0으로 두어 금액은 비용 기록에서만 센다.
- 매번 최근 40일을 다시 읽어 그 기간을 새 값으로 바꾼다. 처음에는 180일을 읽는다.
"""

import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session, select

from .config import BACKEND_DIR, get_settings
from .db import engine
from .models import UsageRecord
from .usage import get_or_create_provider

log = logging.getLogger(__name__)

API = "https://api.openai.com/v1/organization"
PROVIDER = "openai"
WINDOW_DAYS = 40
FIRST_DAYS = 180
STATE_FILE = BACKEND_DIR / "data" / "openai_state.json"
_lock = threading.Lock()


class OpenAIUsageError(RuntimeError):
    pass


def _get(session, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """페이지를 끝까지 따라가며 data 목록을 모은다."""
    out: list[dict[str, Any]] = []
    params = dict(params)
    for _ in range(100):
        res = session.get(f"{API}/{path}", params=params, timeout=60)
        if res.status_code == 401:
            raise OpenAIUsageError("Admin API 키가 올바르지 않습니다 (401). sk-admin- 으로 시작하는 키인지 확인하세요.")
        if res.status_code == 403:
            raise OpenAIUsageError("권한이 없습니다 (403). 조직 Owner가 만든 Admin API 키가 필요합니다.")
        if res.status_code >= 400:
            try:
                msg = res.json().get("error", {}).get("message")
            except ValueError:
                msg = None
            raise OpenAIUsageError(f"{path}: {msg or res.text[:200]} ({res.status_code})")
        data = res.json()
        out.extend(data.get("data", []))
        cursor = data.get("next_page")
        if not cursor:
            break
        params["page"] = cursor
    return out


def _session(key: str):
    import requests

    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return s


def _project_names(session) -> dict[str, str]:
    try:
        return {p["id"]: p.get("name") or p["id"] for p in _get(session, "projects", {"limit": 100, "include_archived": "true"})}
    except OpenAIUsageError as e:
        log.info("OpenAI 프로젝트 이름을 못 읽음: %s", e)
        return {}


def _day(start_time: int) -> tuple[str, datetime]:
    start = datetime.fromtimestamp(int(start_time), UTC)
    return start.date().isoformat(), start + timedelta(hours=12)


def sync(full: bool = False) -> dict[str, Any]:
    key = get_settings().openai_admin_key.strip()
    if not key:
        raise OpenAIUsageError("OPENAI_ADMIN_KEY 가 비어 있습니다 (backend/.env)")
    days = FIRST_DAYS if full else WINDOW_DAYS
    since = (datetime.now(UTC) - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    session = _session(key)
    names = _project_names(session)
    common = {"start_time": int(since.timestamp()), "bucket_width": "1d", "limit": 31}
    costs = _get(session, "costs", {**common, "group_by": ["project_id", "line_item"]})
    usage = _get(session, "usage/completions", {**common, "group_by": ["model", "project_id"]})

    saved_cost = saved_usage = 0
    total = 0.0
    tokens = 0
    day_list: set[str] = set()
    with _lock, Session(engine) as db:
        provider = get_or_create_provider(db, PROVIDER)
        db.exec(delete(UsageRecord).where(
            UsageRecord.provider_id == provider.id,
            UsageRecord.source.in_(["openai_costs", "openai_usage"]),
            UsageRecord.ts >= since,
        ))
        for bucket in costs:
            day, ts = _day(bucket["start_time"])
            for r in bucket.get("results", []):
                value = float((r.get("amount") or {}).get("value") or 0)
                if not value:
                    continue
                item = r.get("line_item") or "기타"
                project = r.get("project_id")
                db.add(UsageRecord(
                    provider_id=provider.id, model=item.split(",")[0].strip(), project_name=names.get(project, project),
                    ts=ts, kind=provider.kind, unit="usd", quantity=value, cost_usd=value,
                    source="openai_costs", source_ref=f"oa-cost:{day}:{project}:{item}",
                    meta={"line_item": item, "currency": (r.get("amount") or {}).get("currency"), "openai_project": project},
                ))
                saved_cost += 1
                total += value
                day_list.add(day)
        for bucket in usage:
            day, ts = _day(bucket["start_time"])
            for r in bucket.get("results", []):
                inp, cached, out = int(r.get("input_tokens") or 0), int(r.get("input_cached_tokens") or 0), int(r.get("output_tokens") or 0)
                if not (inp or out):
                    continue
                project = r.get("project_id")
                model = r.get("model") or "unknown"
                db.add(UsageRecord(
                    provider_id=provider.id, model=model, project_name=names.get(project, project),
                    ts=ts, kind=provider.kind, unit="token", quantity=inp + out,
                    input_tokens=max(0, inp - cached), cache_read_tokens=cached, output_tokens=out,
                    cost_usd=0.0,  # 금액은 비용 기록에서 센다
                    source="openai_usage", source_ref=f"oa-usage:{day}:{project}:{model}",
                    meta={"requests": r.get("num_model_requests"), "openai_project": project},
                ))
                saved_usage += 1
                tokens += inp + out
                day_list.add(day)
        db.commit()

    result = {
        "at": datetime.now().astimezone().isoformat(), "error": None, "days": days,
        "cost_records": saved_cost, "usage_records": saved_usage, "cost_usd": round(total, 4), "tokens": tokens,
        "first": min(day_list) if day_list else None, "last": max(day_list) if day_list else None,
    }
    _save_state({"last_sync": result})
    log.info("OpenAI 사용량 가져옴: %s", result)
    return result


# ---------------------------------------------------------------- 상태와 주기 실행


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def status() -> dict[str, Any]:
    s = get_settings()
    return {"configured": bool(s.openai_admin_key.strip()), "sync_hours": s.openai_sync_hours, "last_sync": _load_state().get("last_sync")}


def sync_safely(full: bool | None = None) -> dict[str, Any]:
    if full is None:  # 한 번도 성공한 적이 없으면 180일을 읽는다
        last = _load_state().get("last_sync") or {}
        full = not last.get("first")
    try:
        return sync(full)
    except Exception as e:
        log.warning("OpenAI 사용량 가져오기 실패: %s", e)
        result = {"at": datetime.now().astimezone().isoformat(), "error": str(e)}
        _save_state({"last_sync": result})
        return result


def watch_forever() -> None:
    while True:
        if get_settings().openai_admin_key.strip():
            sync_safely()
        time.sleep(max(1, get_settings().openai_sync_hours) * 3600)
