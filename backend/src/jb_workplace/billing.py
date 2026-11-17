"""Google Cloud 결제 내보내기(BigQuery)에서 Gemini API 같은 서비스의 실제 비용을 가져온다.

- 인증: Application Default Credentials (`gcloud auth application-default login`, 또는 키 파일).
- 날짜(서울 시간) × GCP 프로젝트 × SKU 마다 한 건으로 저장한다. 비용은 크레딧(무료 사용량·할인)을 뺀 순비용이며,
  테이블에 들어 있는 환율(currency_conversion_rate)로 달러로 바꾼다.
- 결제 데이터는 며칠 뒤에 고쳐지기도 하므로, 매번 최근 40일을 다시 읽어 그 기간을 새 값으로 바꾼다.
- 이미 Billing 보고서 CSV로 넣어 둔 기간(meta.covered_until)은 두 번 세지 않도록 건너뛴다.
"""

import json
import logging
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlmodel import Session, select

from .config import BACKEND_DIR, get_settings
from .db import engine
from .models import UsageRecord
from .usage import get_or_create_provider

log = logging.getLogger(__name__)

TZ = "Asia/Seoul"
WINDOW_DAYS = 40
STATE_FILE = BACKEND_DIR / "data" / "billing_state.json"
_lock = threading.Lock()
_TABLE = re.compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
_MODEL = re.compile(r"(Gemini[\w .\-]*?(?:Pro|Flash(?:[- ]Lite)?|Nano|Ultra)|Imagen[\w .\-]*|Veo[\w .\-]*)", re.I)


class BillingError(RuntimeError):
    pass


def _session():
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as e:  # pragma: no cover
        raise BillingError("google-auth 패키지가 없습니다. backend 폴더에서 `uv sync`를 실행하세요.") from e
    try:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/bigquery.readonly", "https://www.googleapis.com/auth/cloud-platform.read-only"])
    except Exception as e:
        raise BillingError("Google 인증 정보가 없습니다. `gcloud auth application-default login`을 실행하세요.") from e
    return AuthorizedSession(creds)


def _query(session, project: str, sql: str, params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    url = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}/queries"
    body = {"query": sql, "useLegacySql": False, "queryParameters": params, "timeoutMs": 60000}
    res = session.post(url, json=body, timeout=90)
    data = res.json()
    if res.status_code >= 400:
        raise BillingError(data.get("error", {}).get("message", res.text[:300]))
    if not data.get("jobComplete", True):
        raise BillingError("BigQuery 조회가 시간 안에 끝나지 않았습니다")
    fields = [f["name"] for f in data.get("schema", {}).get("fields", [])]
    rows = [dict(zip(fields, (c.get("v") for c in r["f"]))) for r in data.get("rows", [])]
    token = data.get("pageToken")
    job = data.get("jobReference", {})
    while token:  # 행이 많으면 나눠서 받는다
        page = session.get(f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}/queries/{job.get('jobId')}",
                           params={"pageToken": token, "location": job.get("location")}, timeout=90).json()
        rows += [dict(zip(fields, (c.get("v") for c in r["f"]))) for r in page.get("rows", [])]
        token = page.get("pageToken")
    return rows


SQL = """
SELECT
  CAST(DATE(usage_start_time, @tz) AS STRING) AS day,
  project.id AS project,
  service.description AS service,
  sku.id AS sku_id,
  sku.description AS sku,
  SUM(cost) AS cost,
  SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS credits,
  ANY_VALUE(currency) AS currency,
  AVG(currency_conversion_rate) AS rate,
  SUM(usage.amount) AS amount,
  ANY_VALUE(usage.unit) AS unit,
  CAST(MAX(usage_end_time) AS STRING) AS last_at
FROM `{table}`
WHERE service.description IN UNNEST(@services)
  AND usage_start_time >= TIMESTAMP(@since, @tz)
GROUP BY day, project, service, sku_id, sku
"""


def _model(sku: str) -> str:
    m = _MODEL.search(sku or "")
    return m.group(1).strip() if m else (sku or "")[:120]


def _covered_until(db: Session, provider_id: int) -> str | None:
    """Billing CSV 합계로 이미 넣어 둔 마지막 날짜."""
    days = [
        (r.meta or {}).get("covered_until")
        for r in db.exec(select(UsageRecord).where(UsageRecord.provider_id == provider_id, UsageRecord.source == "billing")).all()
    ]
    days = [d for d in days if d]
    return max(days) if days else None


def sync(full: bool = False) -> dict[str, Any]:
    """설정된 테이블에서 최근 비용을 가져온다. full=True면 처음부터 다시 읽는다."""
    settings = get_settings()
    tables, services = settings.billing_tables, settings.billing_services
    if not tables:
        raise BillingError("GCP_BILLING_TABLES 가 비어 있습니다 (backend/.env)")
    for t in tables:
        if not _TABLE.match(t):
            raise BillingError(f"테이블 이름 형식이 아닙니다: {t} (프로젝트.데이터세트.테이블)")
    since = date(2000, 1, 1) if full else datetime.now(ZoneInfo(TZ)).date() - timedelta(days=WINDOW_DAYS)
    session = _session()

    result: dict[str, Any] = {"at": datetime.now().astimezone().isoformat(), "tables": [], "error": None}
    with _lock:
        for table in tables:
            rows = _query(session, table.split(".")[0], SQL.format(table=table), [
                {"name": "tz", "parameterType": {"type": "STRING"}, "parameterValue": {"value": TZ}},
                {"name": "since", "parameterType": {"type": "STRING"}, "parameterValue": {"value": since.isoformat()}},
                {"name": "services", "parameterType": {"type": "ARRAY", "arrayType": {"type": "STRING"}},
                 "parameterValue": {"arrayValues": [{"value": s} for s in services]}},
            ])
            saved = skipped = 0
            total = 0.0
            with Session(engine) as db:
                providers = {svc: get_or_create_provider(db, name) for svc, name in services.items()}
                start = datetime.combine(since, datetime.min.time(), ZoneInfo(TZ))
                for p in providers.values():
                    db.exec(delete(UsageRecord).where(
                        UsageRecord.provider_id == p.id,
                        UsageRecord.source == "billing_export",
                        UsageRecord.source_ref.like(f"bq:{table}:%"),
                        UsageRecord.ts >= start,
                    ))
                covered = {svc: _covered_until(db, p.id) for svc, p in providers.items()}
                for r in rows:
                    provider = providers.get(r["service"])
                    if provider is None:
                        continue
                    if covered[r["service"]] and r["day"] <= covered[r["service"]]:
                        skipped += 1
                        continue
                    cost, credits = float(r["cost"] or 0), float(r["credits"] or 0)
                    rate = float(r["rate"] or 1) or 1.0
                    net_usd = (cost + credits) / rate
                    if not cost and not credits and not float(r["amount"] or 0):
                        continue
                    db.add(UsageRecord(
                        provider_id=provider.id,
                        model=_model(r["sku"]),
                        project_name=r["project"],
                        ts=datetime.fromisoformat(f"{r['day']}T12:00:00").replace(tzinfo=ZoneInfo(TZ)),
                        kind=provider.kind,
                        unit=r["unit"] or "count",
                        quantity=float(r["amount"] or 0),
                        cost_usd=round(net_usd, 6),
                        source="billing_export",
                        source_ref=f"bq:{table}:{r['day']}:{r['project']}:{r['sku_id']}",
                        meta={"sku": r["sku"], "currency": r["currency"], "cost": cost, "credits": credits,
                              "rate": rate, "gcp_project": r["project"]},
                    ))
                    saved += 1
                    total += net_usd
                db.commit()
            days = sorted({r["day"] for r in rows})
            result["tables"].append({
                "table": table, "rows": len(rows), "saved": saved, "skipped_csv_days": skipped,
                "cost_usd": round(total, 4), "first": days[0] if days else None, "last": days[-1] if days else None,
            })
    _save_state({"last_sync": result})
    log.info("결제 내보내기 가져옴: %s", result)
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
    return {
        "tables": s.billing_tables,
        "services": s.billing_services,
        "sync_hours": s.gcp_billing_sync_hours,
        "last_sync": _load_state().get("last_sync"),
    }


def sync_safely(full: bool = False) -> dict[str, Any]:
    try:
        return sync(full)
    except Exception as e:  # 상태 화면에 오류를 보여준다
        log.warning("결제 내보내기 가져오기 실패: %s", e)
        result = {"at": datetime.now().astimezone().isoformat(), "tables": [], "error": str(e)}
        _save_state({"last_sync": result})
        return result


def watch_forever() -> None:
    while True:
        if get_settings().billing_tables:
            last = _load_state().get("last_sync") or {}
            # 아직 한 번도 데이터를 받은 적이 없으면 처음부터 읽는다 (내보내기를 켠 직후에는 테이블이 비어 있다).
            sync_safely(full=not any(t.get("rows") for t in last.get("tables", [])))
        time.sleep(max(1, get_settings().gcp_billing_sync_hours) * 3600)
