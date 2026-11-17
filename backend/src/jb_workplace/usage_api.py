"""사용량 API: 기록 받기, provider별 요약, provider·단가표 관리."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from .db import get_session
from .models import PriceRule, Project, Provider, UsageRecord
from .services import CATALOG, CATALOG_BY_NAME, detect
from .usage import PriceBook, UsageIn, get_or_create_provider, record_usage

router = APIRouter(prefix="/api/usage")

TEXT_KINDS = {"text", "embedding"}
MEDIA_KINDS = {"image", "video", "audio", "mixed"}


class RecordIn(BaseModel):
    provider: str = Field(min_length=1, max_length=60)
    unit: str = Field(min_length=1, max_length=40)
    quantity: float = Field(default=0, ge=0)
    model: str | None = Field(default=None, max_length=120)
    kind: str = Field(default="text", max_length=20)
    project: str | None = Field(default=None, max_length=500)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    ts: datetime | None = None
    source_ref: str | None = Field(default=None, max_length=300)
    meta: dict[str, Any] | None = None


@router.post("/records", status_code=201)
def post_record(body: RecordIn, db: Session = Depends(get_session)) -> dict:
    """다른 프로젝트가 AI API를 쓸 때마다 사용량을 보내는 곳. 처음 보는 provider는 자동으로 등록된다."""
    record = record_usage(db, UsageIn(**body.model_dump(), source="app"))
    return {"id": record.id, "provider_id": record.provider_id}


def _kind_ok(kind: str, wanted: str) -> bool:
    if wanted == "text":
        return kind in TEXT_KINDS
    if wanted == "media":
        return kind in MEDIA_KINDS
    return True


@router.get("/summary")
def summary(
    days: int = Query(7, ge=1, le=90),
    kind: str = Query("all", pattern="^(all|text|media)$"),
    db: Session = Depends(get_session),
) -> dict:
    """기간 안의 provider별 일별 비용과 고유 단위 사용량. 지난 같은 기간 합계도 함께 준다."""
    today = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=days - 1)
    prev_start = start - timedelta(days=days)
    labels = [(start + timedelta(days=i)).date().isoformat() for i in range(days)]
    index = {d: i for i, d in enumerate(labels)}

    providers = {p.id: p for p in db.exec(select(Provider)).all()}
    projects = {p.id: p.name for p in db.exec(select(Project)).all()}
    book = PriceBook(db)
    records = db.exec(select(UsageRecord).where(UsageRecord.ts >= prev_start)).all()

    per: dict[int, dict[str, Any]] = {}
    prev_total = 0.0
    for r in records:
        provider = providers.get(r.provider_id)
        if provider is None or not _kind_ok(r.kind or provider.kind, kind):
            continue
        cost = book.cost(r)
        ts = r.ts.astimezone()
        if ts < start:
            prev_total += cost or 0
            continue
        p = per.setdefault(r.provider_id, {
            "series": [0.0] * days,
            "cost": 0.0,
            "missing_price": False,
            "units": defaultdict(float),
            "tokens": defaultdict(int),
            "models": defaultdict(lambda: {"cost": 0.0, "quantity": 0.0, "unit": None, "missing_price": False}),
            "projects": defaultdict(float),
            "records": 0,
        })
        p["records"] += 1
        day = ts.date().isoformat()
        if cost is None:
            p["missing_price"] = True
        else:
            p["cost"] += cost
            if day in index:
                p["series"][index[day]] += cost
        p["units"][r.unit] += r.quantity
        for k in ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens"):
            p["tokens"][k] += getattr(r, k)
        m = p["models"][r.model or "(모델 미상)"]
        m["quantity"] += r.quantity
        m["unit"] = r.unit
        if cost is None:
            m["missing_price"] = True
        else:
            m["cost"] += cost
        project_name = projects.get(r.project_id) if r.project_id else (r.project_name or "(프로젝트 없음)")
        p["projects"][project_name] += cost or 0

    week_ago = datetime.now(UTC) - timedelta(days=7)
    out = []
    for pid, p in per.items():
        provider = providers[pid]
        out.append({
            "id": pid,
            "name": provider.name,
            "display_name": provider.display_name or provider.name,
            "kind": provider.kind,
            "color": provider.color,
            "is_new": provider.created_at >= week_ago,
            "cost": round(p["cost"], 6),
            "missing_price": p["missing_price"],
            "series": [round(v, 6) for v in p["series"]],
            "units": dict(p["units"]),
            "tokens": dict(p["tokens"]),
            "models": sorted(
                ({"model": k, **v} for k, v in p["models"].items()), key=lambda x: -x["cost"]
            ),
            "projects": sorted(({"name": k, "cost": v} for k, v in p["projects"].items()), key=lambda x: -x["cost"]),
            "records": p["records"],
        })
    out.sort(key=lambda x: -x["cost"])
    total = sum(p["cost"] for p in out)
    new_providers = [
        {"id": p.id, "name": p.display_name or p.name, "missing_price": not any(k[0] == p.id for k in book.rules)}
        for p in providers.values()
        if p.created_at >= week_ago
    ]
    return {
        "days": days,
        "kind": kind,
        "labels": labels,
        "providers": out,
        "total_cost": round(total, 6),
        "prev_total_cost": round(prev_total, 6),
        "provider_count": len(out),
        "new_providers": new_providers,
    }


def _month_start(d: datetime, back: int) -> datetime:
    y, m = d.year, d.month - back
    while m <= 0:
        m += 12
        y -= 1
    return d.replace(year=y, month=m, day=1)


@router.get("/overview")
def overview(
    days: int = Query(7, ge=1, le=60),
    kind: str = Query("all", pattern="^(all|text|media)$"),
    db: Session = Depends(get_session),
) -> dict:
    """한 차트용 묶음: 최근 3달(월별 일평균) · 최근 4주(주별 일평균) · 최근 N일(일별).

    월·주 막대는 그 기간 비용 ÷ 지난 날 수 (이번 달·이번 주는 오늘까지의 날 수)라서
    일별 막대와 같은 '하루 비용' 기준으로 비교할 수 있다.
    """
    now = datetime.now().astimezone()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    buckets: list[dict[str, Any]] = []
    for back in (2, 1, 0):
        start = _month_start(today, back)
        end = min(_month_start(today, back - 1) if back else tomorrow, tomorrow)
        buckets.append({"group": "month", "label": f"M {start.month}", "start": start, "end": end})
    this_monday = today - timedelta(days=today.weekday())
    for back in (3, 2, 1, 0):
        start = this_monday - timedelta(weeks=back)
        end = min(start + timedelta(days=7), tomorrow)
        buckets.append({"group": "week", "label": f"W {start.isocalendar().week}", "start": start, "end": end})
    for back in range(days - 1, -1, -1):
        start = today - timedelta(days=back)
        buckets.append({"group": "day", "label": f"{start.month}/{start.day}", "start": start, "end": start + timedelta(days=1)})
    for b in buckets:
        b["days"] = max(1, round((b["end"] - b["start"]).total_seconds() / 86400))

    earliest = min(b["start"] for b in buckets)
    providers = {p.id: p for p in db.exec(select(Provider)).all()}
    book = PriceBook(db)
    records = db.exec(select(UsageRecord).where(UsageRecord.ts >= earliest)).all()

    per: dict[int, dict[str, Any]] = {}
    for r in records:
        provider = providers.get(r.provider_id)
        if provider is None or not _kind_ok(r.kind or provider.kind, kind):
            continue
        cost = book.cost(r)
        ts = r.ts.astimezone()
        p = per.setdefault(r.provider_id, {"totals": [0.0] * len(buckets), "missing_price": False})
        if cost is None:
            p["missing_price"] = True
            continue
        for i, b in enumerate(buckets):
            if b["start"] <= ts < b["end"]:
                p["totals"][i] += cost

    out = []
    for pid, p in per.items():
        provider = providers[pid]
        values = [round(t / b["days"], 6) for t, b in zip(p["totals"], buckets)]
        selected = sum(t for t, b in zip(p["totals"], buckets) if b["group"] == "day")
        out.append({
            "id": pid,
            "name": provider.name,
            "display_name": provider.display_name or provider.name,
            "kind": provider.kind,
            "color": provider.color,
            "missing_price": p["missing_price"],
            "values": values,
            "selected_cost": round(selected, 6),
        })
    out.sort(key=lambda x: -x["selected_cost"])
    return {
        "days": days,
        "kind": kind,
        "buckets": [
            {"group": b["group"], "label": b["label"], "start": b["start"].date().isoformat(), "days": b["days"]}
            for b in buckets
        ],
        "providers": out,
    }


# ---------------------------------------------------------------- provider와 단가표


class ProviderOut(BaseModel):
    id: int
    name: str
    display_name: str | None
    kind: str
    color: str | None
    created_at: datetime
    collection: str
    default_unit: str | None
    detect: str | None
    website: str | None
    notes: str | None


KIND_PATTERN = "^(text|image|video|audio|embedding|mixed)$"
COLLECTION_PATTERN = "^(claude_logs|app|manual|takeout)$"


class ProviderPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=60)
    kind: str | None = Field(default=None, pattern=KIND_PATTERN)
    color: str | None = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")
    collection: str | None = Field(default=None, pattern=COLLECTION_PATTERN)
    default_unit: str | None = Field(default=None, max_length=40)
    detect: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=1000)


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40, pattern="^[A-Za-z0-9_.-]+$")
    display_name: str | None = Field(default=None, max_length=60)
    kind: str | None = Field(default=None, pattern=KIND_PATTERN)
    collection: str | None = Field(default=None, pattern=COLLECTION_PATTERN)
    default_unit: str | None = Field(default=None, max_length=40)
    detect: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=1000)


@router.get("/catalog")
def catalog(db: Session = Depends(get_session)) -> list[dict]:
    """등록할 때 고를 수 있는 자주 쓰는 서비스 목록."""
    registered = {p.name for p in db.exec(select(Provider)).all()}
    return [{**c, "registered": c["name"] in registered} for c in CATALOG]


@router.post("/providers", response_model=ProviderOut, status_code=201)
def create_provider(body: ProviderCreate, db: Session = Depends(get_session)) -> ProviderOut:
    key = body.name.strip().lower()
    if db.exec(select(Provider).where(Provider.name == key)).first():
        raise HTTPException(409, "이미 등록된 서비스입니다")
    provider = get_or_create_provider(db, key, body.kind or "text", body.display_name)
    for field, value in body.model_dump(exclude={"name"}, exclude_none=True).items():
        setattr(provider, field, value)
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return ProviderOut(**provider.model_dump())


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: int, db: Session = Depends(get_session)) -> None:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(404, "서비스를 찾을 수 없습니다")
    used = db.exec(select(func.count()).select_from(UsageRecord).where(UsageRecord.provider_id == provider_id)).one()
    if used:
        raise HTTPException(409, f"사용량 기록이 {used}건 있어 지울 수 없습니다. 기록을 남겨 두려면 메모만 바꾸세요.")
    for rule in db.exec(select(PriceRule).where(PriceRule.provider_id == provider_id)).all():
        db.delete(rule)
    db.delete(provider)
    db.commit()


@router.get("/services")
def services_status(refresh: bool = False, db: Session = Depends(get_session)) -> dict:
    """설정 화면: 서비스별 연결 상태 (기록, 마지막 수신, 코드에서 쓰는 프로젝트와 연결된 프로젝트)."""
    providers = db.exec(select(Provider).order_by(Provider.name)).all()
    projects = db.exec(select(Project).where(Project.exists == True)).all()  # noqa: E712
    names = {p.id: p.name for p in projects}
    week_ago = datetime.now(UTC) - timedelta(days=7)

    stats: dict[int, dict[str, Any]] = {}
    for pid, total, last, recent in db.exec(
        select(
            UsageRecord.provider_id,
            func.count(),
            func.max(UsageRecord.ts),
            func.count().filter(UsageRecord.ts >= week_ago),
        ).group_by(UsageRecord.provider_id)
    ).all():
        stats[pid] = {"records": total, "last_at": last, "records_7d": recent}
    reporting: dict[int, set[str]] = defaultdict(set)
    for pid, proj_id in db.exec(
        select(UsageRecord.provider_id, UsageRecord.project_id).where(UsageRecord.project_id != None).distinct()  # noqa: E711
    ).all():
        if proj_id in names:
            reporting[pid].add(names[proj_id])

    scan = detect(
        [(p.id, p.name, p.path) for p in projects],
        [(p.name, p.detect) for p in providers if p.detect],
        refresh=refresh,
    )
    out = []
    for p in providers:
        used_in = [
            {"project": info["name"], "files": info["uses"][p.name], "instrumented": info["instrumented"]}
            for info in scan["projects"].values()
            if p.name in info["uses"]
        ]
        out.append({
            **ProviderOut(**p.model_dump()).model_dump(mode="json"),
            "helper": CATALOG_BY_NAME.get(p.name, {}).get("helper", "record_usage"),
            "has_price": bool(db.exec(select(PriceRule.id).where(PriceRule.provider_id == p.id).limit(1)).first()),
            **{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in stats.get(p.id, {"records": 0, "last_at": None, "records_7d": 0}).items()},
            "reporting_projects": sorted(reporting.get(p.id, set())),
            "used_in": sorted(used_in, key=lambda x: x["project"].lower()),
        })
    return {"scanned_at": scan["scanned_at"], "services": out}


class ManualIn(BaseModel):
    provider_id: int
    date: datetime
    cost_usd: float | None = Field(default=None, ge=0)
    quantity: float = Field(default=0, ge=0)
    unit: str | None = Field(default=None, max_length=40)
    project: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=300)


@router.post("/manual", status_code=201)
def add_manual(body: ManualIn, db: Session = Depends(get_session)) -> dict:
    """연결하기 어려운 서비스의 사용량·비용을 직접 입력한다 (예: 이번 달 청구서 금액)."""
    provider = db.get(Provider, body.provider_id)
    if provider is None:
        raise HTTPException(404, "서비스를 찾을 수 없습니다")
    if body.cost_usd is None and not body.quantity:
        raise HTTPException(400, "비용이나 사용량 중 하나는 입력하세요")
    record = record_usage(db, UsageIn(
        provider=provider.name, unit=body.unit or provider.default_unit or "request", quantity=body.quantity,
        kind=provider.kind, project=body.project, cost_usd=body.cost_usd, ts=body.date, source="manual",
        meta={"note": body.note} if body.note else None,
    ))
    return {"id": record.id}


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_session)) -> list[ProviderOut]:
    return [ProviderOut(**p.model_dump()) for p in db.exec(select(Provider).order_by(Provider.name)).all()]


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
def patch_provider(provider_id: int, body: ProviderPatch, db: Session = Depends(get_session)) -> ProviderOut:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(404, "provider를 찾을 수 없습니다")
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(provider, key, value)
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return ProviderOut(**provider.model_dump())


class PriceOut(BaseModel):
    id: int
    provider_id: int
    model: str | None
    unit: str
    price_per_unit: float
    valid_from: datetime
    note: str | None


class PriceIn(BaseModel):
    provider_id: int
    model: str | None = Field(default=None, max_length=120)
    unit: str = Field(min_length=1, max_length=40)
    price_per_unit: float = Field(ge=0)
    valid_from: datetime | None = None
    note: str | None = Field(default=None, max_length=200)


@router.get("/prices", response_model=list[PriceOut])
def list_prices(provider_id: int | None = None, db: Session = Depends(get_session)) -> list[PriceOut]:
    query = select(PriceRule)
    if provider_id is not None:
        query = query.where(PriceRule.provider_id == provider_id)
    rows = db.exec(query.order_by(PriceRule.provider_id, PriceRule.model, PriceRule.unit, PriceRule.valid_from)).all()
    return [PriceOut(**r.model_dump()) for r in rows]


@router.post("/prices", response_model=PriceOut, status_code=201)
def add_price(body: PriceIn, db: Session = Depends(get_session)) -> PriceOut:
    if db.get(Provider, body.provider_id) is None:
        raise HTTPException(404, "provider를 찾을 수 없습니다")
    rule = PriceRule(
        provider_id=body.provider_id,
        model=(body.model or "").strip() or None,
        unit=body.unit.strip(),
        price_per_unit=body.price_per_unit,
        valid_from=body.valid_from or datetime(2020, 1, 1, tzinfo=UTC),
        note=body.note,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return PriceOut(**rule.model_dump())


@router.delete("/prices/{rule_id}", status_code=204)
def delete_price(rule_id: int, db: Session = Depends(get_session)) -> None:
    rule = db.get(PriceRule, rule_id)
    if rule is None:
        raise HTTPException(404, "단가를 찾을 수 없습니다")
    db.delete(rule)
    db.commit()


# ---------------------------------------------------------------- Gemini 앱 (Google Takeout)


@router.get("/takeout")
def takeout_status() -> dict:
    """지켜보는 폴더와 마지막으로 가져온 결과."""
    from . import takeout

    return takeout.status()


@router.post("/takeout")
async def takeout_upload(request: Request, name: str = Query("upload", max_length=200)) -> dict:
    """Takeout zip(또는 활동 JSON)을 본문 그대로 받아 가져온다."""
    from starlette.concurrency import run_in_threadpool

    from . import takeout

    data = await request.body()
    if not data:
        raise HTTPException(400, "파일이 비어 있습니다")
    try:
        return await run_in_threadpool(takeout.import_bytes, data, name)
    except takeout.TakeoutError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/takeout/scan")
def takeout_scan() -> dict:
    """지켜보는 폴더를 지금 확인한다."""
    from . import takeout

    return {"imported": takeout.scan_dirs(), **takeout.status()}


# ---------------------------------------------------------------- Google Cloud 결제 내보내기 (BigQuery)


@router.get("/billing")
def billing_status() -> dict:
    from . import billing

    return billing.status()


@router.post("/billing/sync")
def billing_sync(full: bool = False) -> dict:
    """결제 내보내기 테이블에서 지금 가져온다. full=true면 처음부터."""
    from . import billing

    return {**billing.status(), "result": billing.sync_safely(full)}
