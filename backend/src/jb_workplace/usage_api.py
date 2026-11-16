"""사용량 API: 기록 받기, provider별 요약, provider·단가표 관리."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .db import get_session
from .models import PriceRule, Project, Provider, UsageRecord
from .usage import PriceBook, UsageIn, record_usage

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


# ---------------------------------------------------------------- provider와 단가표


class ProviderOut(BaseModel):
    id: int
    name: str
    display_name: str | None
    kind: str
    color: str | None
    created_at: datetime


class ProviderPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=60)
    kind: str | None = Field(default=None, pattern="^(text|image|video|audio|embedding|mixed)$")
    color: str | None = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")


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
