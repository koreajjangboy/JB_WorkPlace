"""Runway API 사용량: 개발자 API의 조직 사용량 조회(POST /v1/organization/usage)에서 가져온다.

- 날짜 × 모델별로 쓴 크레딧을 저장한다. 금액 = 크레딧 × RUNWAY_USD_PER_CREDIT (API 크레딧은 1개 $0.01).
- 한 번에 최대 90일까지 조회된다. 처음에는 90일, 이후에는 최근 40일을 다시 읽어 그 기간을 새 값으로 바꾼다.
- 웹 앱(구독) 크레딧은 별도 풀이고, 조회 API(webapp/usage)는 Enterprise 플랜에서만 열려 있어 여기서는 다루지 않는다.
- 남은 크레딧은 GET /v1/organization 의 creditBalance 로 보여준다.
"""

import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session

from .config import BACKEND_DIR, get_settings
from .db import engine
from .models import UsageRecord
from .usage import get_or_create_provider

log = logging.getLogger(__name__)

API = "https://api.dev.runwayml.com/v1"
VERSION = "2024-11-06"
PROVIDER = "runway"
WINDOW_DAYS = 40
MAX_DAYS = 90
STATE_FILE = BACKEND_DIR / "data" / "runway_state.json"
_lock = threading.Lock()


class RunwayUsageError(RuntimeError):
    pass


def _session(key: str):
    import requests

    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {key}", "X-Runway-Version": VERSION, "Content-Type": "application/json"})
    return s


def _check(res, what: str) -> dict[str, Any]:
    if res.status_code == 401:
        raise RunwayUsageError("Runway API 키가 올바르지 않습니다 (401). 개발자 포털(dev.runwayml.com)에서 만든 키인지 확인하세요.")
    try:
        data = res.json()
    except ValueError:
        data = {}
    if res.status_code >= 400:
        raise RunwayUsageError(f"{what}: {data.get('error') or res.text[:200]} ({res.status_code})")
    return data


def sync(full: bool = False) -> dict[str, Any]:
    s = get_settings()
    key = s.runway_api_key.strip()
    if not key:
        raise RunwayUsageError("RUNWAY_API_KEY 가 비어 있습니다 (backend/.env)")
    days = MAX_DAYS if full else WINDOW_DAYS
    today = datetime.now(UTC).date()
    start = today - timedelta(days=days - 1)
    session = _session(key)

    org = _check(session.get(f"{API}/organization", timeout=30), "organization")
    data = _check(session.post(f"{API}/organization/usage", json={
        "startDate": start.isoformat(), "beforeDate": (today + timedelta(days=1)).isoformat(),
    }, timeout=60), "organization/usage")

    saved = 0
    credits_total = 0.0
    day_list: set[str] = set()
    since = datetime.combine(start, datetime.min.time(), UTC)
    with _lock, Session(engine) as db:
        provider = get_or_create_provider(db, PROVIDER)
        db.exec(delete(UsageRecord).where(
            UsageRecord.provider_id == provider.id, UsageRecord.source == "runway_api", UsageRecord.ts >= since,
        ))
        for day in data.get("results", []):
            date = str(day.get("date", ""))[:10]
            if not date:
                continue
            for u in day.get("usedCredits", []):
                amount = float(u.get("amount") or 0)
                if not amount:
                    continue
                model = u.get("model") or "unknown"
                db.add(UsageRecord(
                    provider_id=provider.id, model=model, ts=datetime.fromisoformat(f"{date}T12:00:00+00:00"),
                    kind=provider.kind, unit="credit", quantity=amount,
                    cost_usd=round(amount * s.runway_usd_per_credit, 6),
                    source="runway_api", source_ref=f"runway:{date}:{model}",
                    meta={"usd_per_credit": s.runway_usd_per_credit},
                ))
                saved += 1
                credits_total += amount
                day_list.add(date)
        db.commit()

    result = {
        "at": datetime.now().astimezone().isoformat(), "error": None, "days": days, "records": saved,
        "credits": credits_total, "cost_usd": round(credits_total * s.runway_usd_per_credit, 4),
        "credit_balance": org.get("creditBalance"), "tier": (org.get("tier") or {}).get("name") if isinstance(org.get("tier"), dict) else org.get("tier"),
        "first": min(day_list) if day_list else None, "last": max(day_list) if day_list else None,
    }
    _save_state({"last_sync": result})
    log.info("Runway 사용량 가져옴: %s", result)
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
    return {"configured": bool(s.runway_api_key.strip()), "sync_hours": s.runway_sync_hours,
            "usd_per_credit": s.runway_usd_per_credit, "last_sync": _load_state().get("last_sync")}


def sync_safely(full: bool | None = None) -> dict[str, Any]:
    if full is None:  # 한 번도 데이터를 받은 적이 없으면 90일을 읽는다
        full = not (_load_state().get("last_sync") or {}).get("first")
    try:
        return sync(full)
    except Exception as e:
        log.warning("Runway 사용량 가져오기 실패: %s", e)
        result = {"at": datetime.now().astimezone().isoformat(), "error": str(e)}
        _save_state({"last_sync": result})
        return result


def watch_forever() -> None:
    while True:
        if get_settings().runway_api_key.strip():
            sync_safely()
        time.sleep(max(1, get_settings().runway_sync_hours) * 3600)
