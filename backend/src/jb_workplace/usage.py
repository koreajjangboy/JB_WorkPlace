"""사용량 수집과 비용 계산.

- Claude Code 세션 기록(하위 에이전트 기록 포함)을 날짜·모델별로 묶어 UsageRecord로 저장한다.
- 다른 provider는 record_usage() (API: POST /api/usage/records)로 기록한다. 처음 보는 provider는 자동 등록.
- 비용은 기록에 실제 비용(cost_usd)이 있으면 그것을, 없으면 PriceRule(단가표)로 계산한다.
  단가를 고치면 과거 기록의 비용도 다시 계산된다.
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func
from sqlmodel import Session, select

from .models import ClaudeSession, PriceRule, Project, Provider, UsageRecord

log = logging.getLogger(__name__)

TOKEN_UNITS = ("input_token", "output_token", "cache_write_token", "cache_read_token")
PALETTE = ["#D85A30", "#7F77DD", "#1D9E75", "#D4537E", "#378ADD", "#BA7517", "#639922", "#888780"]


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- provider


def get_or_create_provider(db: Session, name: str, kind: str = "text", display_name: str | None = None) -> Provider:
    key = name.strip().lower()
    provider = db.exec(select(Provider).where(Provider.name == key)).first()
    if provider:
        return provider
    count = db.exec(select(func.count()).select_from(Provider)).one()
    provider = Provider(
        name=key,
        display_name=display_name or name.strip(),
        kind=kind,
        color=PALETTE[count % len(PALETTE)],
        created_at=_now(),
    )
    db.add(provider)
    db.flush()
    log.info("새 provider 등록: %s", key)
    return provider


# ---------------------------------------------------------------- Claude 세션 기록 → 사용량


def _session_files(main: Path) -> list[Path]:
    """세션 본 기록 + 그 세션의 하위 에이전트 기록 (<세션>/subagents/*.jsonl)."""
    files = [main]
    sub = main.parent / main.stem / "subagents"
    if sub.is_dir():
        files.extend(sorted(sub.glob("*.jsonl")))
    return files


def claude_buckets(main: Path) -> dict[tuple[str, str], dict[str, int]]:
    """{(날짜 YYYY-MM-DD, 모델): 토큰 합계}. 같은 응답이 여러 줄로 나뉘어 기록되므로 응답 id로 한 번만 센다."""
    buckets: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for path in _session_files(main):
        seen: set[str] = set()
        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                msg = rec.get("message") or {}
                usage = msg.get("usage")
                model = msg.get("model")
                if not isinstance(usage, dict) or not model or model.startswith("<"):
                    continue
                mid = msg.get("id")
                if mid:
                    if mid in seen:
                        continue
                    seen.add(mid)
                try:
                    ts = datetime.fromisoformat(rec.get("timestamp", ""))
                except ValueError:
                    continue
                day = ts.astimezone().date().isoformat()  # 이 PC 시간대 기준 날짜
                b = buckets[(day, model)]
                b["input_tokens"] += int(usage.get("input_tokens") or 0)
                b["output_tokens"] += int(usage.get("output_tokens") or 0)
                b["cache_write_tokens"] += int(usage.get("cache_creation_input_tokens") or 0)
                b["cache_read_tokens"] += int(usage.get("cache_read_input_tokens") or 0)
                b["messages"] += 1
    return buckets


def sync_session_usage(db: Session, session: ClaudeSession, provider: Provider) -> int:
    """한 세션의 사용량 기록을 지우고 다시 만든다. 만든 기록 수를 돌려준다."""
    db.exec(delete(UsageRecord).where(UsageRecord.source_ref.like(f"session:{session.id}:%")))
    buckets = claude_buckets(Path(session.file_path))
    for (day, model), t in buckets.items():
        local_midnight = datetime.combine(datetime.fromisoformat(day).date(), time(12)).astimezone()
        total = t["input_tokens"] + t["output_tokens"] + t["cache_write_tokens"] + t["cache_read_tokens"]
        db.add(UsageRecord(
            provider_id=provider.id,
            model=model,
            project_id=session.project_id,
            ts=local_midnight,
            kind="text",
            unit="token",
            quantity=total,
            input_tokens=t["input_tokens"],
            output_tokens=t["output_tokens"],
            cache_write_tokens=t["cache_write_tokens"],
            cache_read_tokens=t["cache_read_tokens"],
            source="session_log",
            source_ref=f"session:{session.id}:{day}:{model}",
            meta={"session_id": session.id, "messages": t["messages"], "title": session.title},
        ))
    return len(buckets)


def sync_claude_usage(db: Session, changed_ids: set[str]) -> int:
    """바뀐 세션과 아직 사용량을 모으지 않은 세션의 사용량을 갱신한다."""
    provider = get_or_create_provider(db, "claude", "text", "Claude")
    collected = {
        row for row in db.exec(
            select(func.split_part(UsageRecord.source_ref, ":", 2)).where(UsageRecord.source == "session_log").distinct()
        ).all()
    }
    sessions = db.exec(select(ClaudeSession)).all()
    count = 0
    for s in sessions:
        if s.id in changed_ids or s.id not in collected:
            count += sync_session_usage(db, s, provider)
        else:
            # 프로젝트 연결이 바뀌었을 수 있으니 맞춰 준다.
            db.exec(
                UsageRecord.__table__.update()
                .where(UsageRecord.source_ref.like(f"session:{s.id}:%"))
                .where(UsageRecord.project_id.is_distinct_from(s.project_id))
                .values(project_id=s.project_id)
            )
    db.commit()
    return count


# ---------------------------------------------------------------- 앱에서 직접 기록 (record_usage)


@dataclass
class UsageIn:
    provider: str
    unit: str
    quantity: float = 0
    model: str | None = None
    kind: str = "text"
    project: str | None = None  # 프로젝트 폴더 이름이나 경로
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float | None = None
    ts: datetime | None = None
    source: str = "app"
    source_ref: str | None = None
    meta: dict[str, Any] | None = None


def _find_project(db: Session, ref: str | None) -> Project | None:
    if not ref:
        return None
    key = ref.strip().rstrip("\\/").lower()
    for p in db.exec(select(Project).where(Project.exists == True)).all():  # noqa: E712
        if p.name.lower() == key or p.path.rstrip("\\/").lower() == key:
            return p
    return None


def record_usage(db: Session, item: UsageIn) -> UsageRecord:
    provider = get_or_create_provider(db, item.provider, item.kind)
    if item.source_ref:
        existing = db.exec(select(UsageRecord).where(UsageRecord.source_ref == item.source_ref)).first()
        if existing:
            return existing
    project = _find_project(db, item.project)
    tokens = item.input_tokens + item.output_tokens + item.cache_write_tokens + item.cache_read_tokens
    record = UsageRecord(
        provider_id=provider.id,
        model=item.model,
        project_id=project.id if project else None,
        project_name=None if project else item.project,
        ts=item.ts or _now(),
        kind=item.kind or provider.kind,
        unit=item.unit,
        quantity=item.quantity or tokens,
        input_tokens=item.input_tokens,
        output_tokens=item.output_tokens,
        cache_write_tokens=item.cache_write_tokens,
        cache_read_tokens=item.cache_read_tokens,
        cost_usd=item.cost_usd,
        source=item.source,
        source_ref=item.source_ref,
        meta=item.meta,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ---------------------------------------------------------------- 비용 계산


class PriceBook:
    """단가표 조회. 모델 전용 단가가 없으면 provider 공통 단가(model 비어 있음)를 쓴다."""

    def __init__(self, db: Session):
        self.rules: dict[tuple[int, str | None, str], list[PriceRule]] = defaultdict(list)
        for r in db.exec(select(PriceRule).order_by(PriceRule.valid_from)).all():
            self.rules[(r.provider_id, r.model, r.unit)].append(r)

    def price(self, provider_id: int, model: str | None, unit: str, at: datetime) -> float | None:
        for key in ((provider_id, model, unit), (provider_id, None, unit)):
            candidates = [r for r in self.rules.get(key, []) if r.valid_from <= at]
            if candidates:
                return candidates[-1].price_per_unit
        return None

    def cost(self, r: UsageRecord) -> float | None:
        if r.cost_usd is not None:
            return r.cost_usd
        if r.unit == "token":
            parts = (
                ("input_token", r.input_tokens),
                ("output_token", r.output_tokens),
                ("cache_write_token", r.cache_write_tokens),
                ("cache_read_token", r.cache_read_tokens),
            )
            if r.input_tokens or r.output_tokens or r.cache_write_tokens or r.cache_read_tokens:
                total = 0.0
                for unit, n in parts:
                    if not n:
                        continue
                    p = self.price(r.provider_id, r.model, unit, r.ts)
                    if p is None:
                        return None
                    total += p * n
                return total
        p = self.price(r.provider_id, r.model, r.unit, r.ts)
        return None if p is None else p * r.quantity
