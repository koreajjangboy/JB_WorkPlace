"""Google 캘린더 일정: 비공개 iCal(ICS) 주소에서 받아 기간 안의 일정을 돌려준다.

OAuth 없이 캘린더 설정의 "iCal 형식의 비공개 주소"를 쓴다. 반복 일정(RRULE)은
자주 쓰는 형태(DAILY/WEEKLY/MONTHLY/YEARLY, INTERVAL, COUNT, UNTIL, BYDAY, BYMONTHDAY, BYMONTH)를
펼치고, EXDATE와 RECURRENCE-ID(반복 중 한 번만 바뀐 일정)를 반영한다.
"""

import calendar as pycal
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from .config import get_settings

router = APIRouter(prefix="/api/calendar")

PALETTE = ["#2563eb", "#16a34a", "#d97706", "#db2777", "#7c3aed", "#0891b2", "#dc2626"]
WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
MAX_PERIODS = 3000  # 반복 일정 하나를 펼칠 때 볼 최대 주기 수

_cache: dict[str, tuple[float, str]] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------- ICS 읽기

def _unescape(v: str) -> str:
    return v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _parse_lines(text: str) -> list[tuple[str, dict[str, str], str]]:
    # 줄 접기 풀기: 공백이나 탭으로 시작하는 줄은 앞 줄에 이어 붙인다.
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: list[str] = []
    for line in raw:
        if line[:1] in (" ", "\t") and lines:
            lines[-1] += line[1:]
        elif line:
            lines.append(line)
    out = []
    for line in lines:
        m = re.match(r'^([^:;]+)((?:;[^:;=]+=(?:"[^"]*"|[^:;]*))*):(.*)$', line)
        if not m:
            continue
        name, params_s, value = m.groups()
        params = {}
        for p in re.findall(r';([^:;=]+)=("[^"]*"|[^:;]*)', params_s):
            params[p[0].upper()] = p[1].strip('"')
        out.append((name.upper(), params, value))
    return out


def _parse_dt(value: str, params: dict[str, str], tz: ZoneInfo) -> tuple[datetime | date, bool]:
    """(값, 종일 여부). 시간이 있는 값은 tz가 붙은 datetime으로 돌려준다."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value[:8], "%Y%m%d").date(), True
    if value.endswith("Z"):
        return datetime.strptime(value[:-1], "%Y%m%dT%H%M%S").replace(tzinfo=ZoneInfo("UTC")), False
    naive = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    zone = tz
    if params.get("TZID"):
        try:
            zone = ZoneInfo(params["TZID"])
        except Exception:  # Google은 IANA 이름을 쓰지만, 모르는 이름이면 기본 시간대로 본다.
            zone = tz
    return naive.replace(tzinfo=zone), False


def _parse_calendar(text: str, tz: ZoneInfo) -> tuple[str | None, list[dict[str, Any]]]:
    name = None
    events: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    depth = 0  # VEVENT 안의 VALARM 같은 하위 블록은 건너뛴다.
    for prop, params, value in _parse_lines(text):
        if prop == "BEGIN":
            if value == "VEVENT" and cur is None:
                cur = {"exdates": []}
            elif cur is not None:
                depth += 1
            continue
        if prop == "END":
            if cur is not None and depth > 0:
                depth -= 1
            elif value == "VEVENT" and cur is not None:
                if "start" in cur:
                    events.append(cur)
                cur = None
            continue
        if cur is None:
            if prop == "X-WR-CALNAME":
                name = _unescape(value)
            continue
        if depth > 0:
            continue
        try:
            if prop == "DTSTART":
                cur["start"], cur["all_day"] = _parse_dt(value, params, tz)
            elif prop == "DTEND":
                cur["end"], _ = _parse_dt(value, params, tz)
            elif prop == "DURATION":
                cur["duration"] = _parse_duration(value)
            elif prop == "RRULE":
                cur["rrule"] = dict(p.split("=", 1) for p in value.split(";") if "=" in p)
            elif prop == "EXDATE":
                for v in value.split(","):
                    cur["exdates"].append(_parse_dt(v, params, tz)[0])
            elif prop == "RECURRENCE-ID":
                cur["recurrence_id"], _ = _parse_dt(value, params, tz)
        except ValueError:
            continue
        if prop == "SUMMARY":
            cur["title"] = _unescape(value)
        elif prop == "LOCATION":
            cur["location"] = _unescape(value)
        elif prop == "DESCRIPTION":
            cur["description"] = _unescape(value)
        elif prop == "UID":
            cur["uid"] = value
        elif prop == "STATUS":
            cur["status"] = value.upper()
    return name, events


def _parse_duration(value: str) -> timedelta:
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value.strip())
    if not m:
        raise ValueError(value)
    sign, w, d, h, mi, s = m.groups()
    td = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0), minutes=int(mi or 0), seconds=int(s or 0))
    return -td if sign == "-" else td


# ---------------------------------------------------------------- 반복 일정 펼치기

def _nth_weekdays(year: int, month: int, spec: str) -> list[int]:
    """BYDAY 한 항목(예: MO, 2TU, -1FR)에 맞는 그 달의 날짜(일) 목록."""
    m = re.fullmatch(r"([+-]?\d+)?([A-Z]{2})", spec)
    if not m or m.group(2) not in WEEKDAYS:
        return []
    wd = WEEKDAYS[m.group(2)]
    days = [d for d in range(1, pycal.monthrange(year, month)[1] + 1) if date(year, month, d).weekday() == wd]
    if m.group(1) is None:
        return days
    n = int(m.group(1))
    idx = n - 1 if n > 0 else n
    return [days[idx]] if -len(days) <= idx < len(days) else []


def _period_dates(rule: dict[str, str], start: date, k: int) -> list[date]:
    """k번째 주기에 들어가는 날짜들 (정렬됨)."""
    freq = rule.get("FREQ", "")
    interval = max(1, int(rule.get("INTERVAL", "1") or 1))
    byday = [s for s in rule.get("BYDAY", "").split(",") if s]
    bymonthday = [int(s) for s in rule.get("BYMONTHDAY", "").split(",") if s.lstrip("-").isdigit()]
    if freq == "DAILY":
        return [start + timedelta(days=k * interval)]
    if freq == "WEEKLY":
        week_start = start - timedelta(days=start.weekday()) + timedelta(weeks=k * interval)
        wds = sorted({WEEKDAYS[d[-2:]] for d in byday if d[-2:] in WEEKDAYS}) or [start.weekday()]
        return [week_start + timedelta(days=w) for w in wds]
    if freq in ("MONTHLY", "YEARLY"):
        if freq == "MONTHLY":
            total = start.year * 12 + start.month - 1 + k * interval
            months = [(total // 12, total % 12 + 1)]
        else:
            year = start.year + k * interval
            bymonth = [int(s) for s in rule.get("BYMONTH", "").split(",") if s.isdigit()]
            months = [(year, m) for m in (bymonth or [start.month])]
        out: list[date] = []
        for y, m in months:
            last = pycal.monthrange(y, m)[1]
            days: set[int] = set()
            for spec in byday:
                days.update(_nth_weekdays(y, m, spec))
            for d in bymonthday:
                d = d if d > 0 else last + d + 1
                if 1 <= d <= last:
                    days.add(d)
            if not byday and not bymonthday and start.day <= last:
                days.add(start.day)  # 31일 반복은 31일이 없는 달을 건너뛴다.
            out.extend(date(y, m, d) for d in sorted(days))
        return out
    # HOURLY 같은 지원하지 않는 반복은 첫 일정만 보여준다.
    return [start] if k == 0 else []


def _occurrences(ev: dict[str, Any], range_start: date, range_end: date, tz: ZoneInfo):
    """(시작, 끝) 목록. 종일 일정은 date, 아니면 datetime."""
    start = ev["start"]
    all_day = ev.get("all_day", False)
    if "end" in ev:
        length = ev["end"] - start
    elif "duration" in ev:
        length = ev["duration"]
    else:
        length = timedelta(days=1) if all_day else timedelta(0)

    rule = ev.get("rrule")
    if not rule:
        yield start, start + length
        return

    until = None
    if "UNTIL" in rule:
        try:
            until = _parse_dt(rule["UNTIL"], {}, tz)[0]
        except ValueError:
            pass
    count = int(rule["COUNT"]) if rule.get("COUNT", "").isdigit() else None
    # 제외 날짜: 종일 일정은 날짜로, 시간 일정은 정확한 시각(UTC 기준)으로 비교한다.
    ex_dates = {x for x in ev["exdates"] if not isinstance(x, datetime)}
    ex_times = {x.astimezone(ZoneInfo("UTC")) for x in ev["exdates"] if isinstance(x, datetime)}

    start_date = start if all_day else start.date()
    # COUNT가 없으면 앞의 주기를 셀 필요가 없으므로 기간 바로 앞까지 건너뛴다.
    k0 = 0
    if count is None and range_start > start_date:
        interval = max(1, int(rule.get("INTERVAL", "1") or 1))
        gap_days = (range_start - start_date).days
        months = (range_start.year - start_date.year) * 12 + range_start.month - start_date.month
        per = {"DAILY": gap_days, "WEEKLY": gap_days // 7, "MONTHLY": months, "YEARLY": months // 12}
        k0 = max(0, per.get(rule.get("FREQ", ""), 0) // interval - 1)
    n = 0
    for k in range(k0, k0 + MAX_PERIODS):
        dates = _period_dates(rule, start_date, k)
        if not dates:
            if rule.get("FREQ") not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
                return
            continue
        for d in dates:
            if d < start_date:
                continue
            occ = d if all_day else datetime.combine(d, start.timetz())
            if until is not None:
                if isinstance(until, datetime):
                    past = d > until.astimezone(tz).date() if all_day else occ > until
                else:
                    past = d > until
                if past:
                    return
            n += 1
            if count is not None and n > count:
                return
            if d in ex_dates or (not all_day and occ.astimezone(ZoneInfo("UTC")) in ex_times):
                continue
            yield occ, occ + length
        if min(dates) > range_end:
            return


def _iso(v: date | datetime, tz: ZoneInfo) -> str:
    return v.astimezone(tz).isoformat() if isinstance(v, datetime) else v.isoformat()


def _expand(events: list[dict[str, Any]], range_start: date, range_end: date, tz: ZoneInfo, cal_index: int, cal_name: str):
    # 반복 중 한 번만 바뀐 일정은 원래 자리의 일정을 대신한다.
    overrides: dict[str, set[str]] = {}
    for ev in events:
        if "recurrence_id" in ev and ev.get("uid"):
            overrides.setdefault(ev["uid"], set()).add(_iso(ev["recurrence_id"], tz))

    out = []
    for ev in events:
        if ev.get("status") == "CANCELLED":
            continue
        replaced = overrides.get(ev.get("uid", ""), set()) if "recurrence_id" not in ev else set()
        for s, e in _occurrences(ev, range_start, range_end, tz):
            if replaced and _iso(s, tz) in replaced:
                continue
            all_day = not isinstance(s, datetime)
            s_date = s if all_day else s.astimezone(tz).date()
            # 종일 일정의 끝은 다음 날 0시(포함 안 됨). 시간 일정은 끝 시각이 0시면 그 전날까지.
            if all_day:
                e_date = e - timedelta(days=1) if e > s else s
            else:
                e_local = e.astimezone(tz)
                e_date = (e_local - timedelta(microseconds=1)).date() if e_local > s.astimezone(tz) else s_date
            if e_date < range_start or s_date > range_end:
                continue
            out.append({
                "id": f"{cal_index}:{ev.get('uid', id(ev))}:{_iso(s, tz)}",
                "title": ev.get("title") or "(제목 없음)",
                "start": _iso(s, tz),
                "end": _iso(e, tz),
                "start_date": s_date.isoformat(),
                "end_date": e_date.isoformat(),
                "all_day": all_day,
                "location": ev.get("location"),
                "description": ev.get("description"),
                "calendar": cal_name,
                "color": PALETTE[cal_index % len(PALETTE)],
            })
    return out


# ---------------------------------------------------------------- 받기 + API

def _fetch(url: str, refresh: bool) -> str:
    ttl = get_settings().calendar_cache_seconds
    with _lock:
        hit = _cache.get(url)
        if hit and not refresh and time.monotonic() - hit[0] < ttl:
            return hit[1]
    if url.startswith("webcal://"):
        url_http = "https://" + url[len("webcal://"):]
    else:
        url_http = url
    req = urllib.request.Request(url_http, headers={"User-Agent": "JB-WorkPlace-Calendar/1.0"})
    with urllib.request.urlopen(req, timeout=15) as res:
        text = res.read().decode("utf-8", errors="replace")
    with _lock:
        _cache[url] = (time.monotonic(), text)
    return text


def _mask(url: str) -> str:
    # 비공개 주소는 그 자체가 비밀이므로 오류 메시지에 그대로 내보내지 않는다.
    m = re.search(r"/ical/([^/]+)/", url)
    return f"…/{m.group(1)[:24]}…" if m else url.split("?")[0][:40] + "…"


@router.get("/events")
def events(
    start: date = Query(..., description="YYYY-MM-DD (포함)"),
    end: date = Query(..., description="YYYY-MM-DD (포함)"),
    refresh: bool = False,
) -> dict[str, Any]:
    if end < start or (end - start).days > 120:
        raise HTTPException(400, "기간은 시작일 이후, 120일 이내여야 합니다.")
    settings = get_settings()
    try:
        tz = ZoneInfo(settings.calendar_timezone)
    except Exception:
        raise HTTPException(500, f"알 수 없는 시간대: {settings.calendar_timezone}")

    urls = settings.calendar_urls
    calendars, items, errors = [], [], []
    for i, url in enumerate(urls):
        try:
            name, evs = _parse_calendar(_fetch(url, refresh), tz)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"캘린더 {i + 1} ({_mask(url)}) 받기 실패: {getattr(exc, 'reason', exc)}")
            continue
        cal_name = name or f"캘린더 {i + 1}"
        calendars.append({"name": cal_name, "color": PALETTE[i % len(PALETTE)]})
        items.extend(_expand(evs, start, end, tz, i, cal_name))

    items.sort(key=lambda e: (e["start_date"], not e["all_day"], e["start"], e["title"]))
    return {
        "configured": bool(urls),
        "timezone": settings.calendar_timezone,
        "calendars": calendars,
        "events": items,
        "errors": errors,
    }
