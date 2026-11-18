"""책나래(국립장애인도서관) 대출 현황: 내가 빌린 책과 반납 예정일.

로그인은 사용자가 직접 한다. [로그인] 버튼을 누르면 전용 프로필로 Edge(또는 Chrome) 창을 띄우고,
사용자가 그 창에서 로그인하면 개발자 도구 프로토콜(CDP)로 그 창의 nld.go.kr 쿠키만 받아 온다.
그 뒤 목록 페이지는 백엔드가 쿠키로 직접 요청한다. 비밀번호는 저장하지 않는다.

사이트 세션이 끝나면(보통 일정 시간 동안 쓰지 않으면) 다시 "로그인 필요"가 되고,
그 전까지 마지막으로 받은 목록은 파일에 남겨 두고 계속 보여준다.
"""

import http.cookiejar
import json
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from .config import get_settings

router = APIRouter(prefix="/api/booknarae")

LIST_URL = "https://cn.nld.go.kr/booknarae/booknaraeLend/selectMyBooknaraeLendReqList.do"
COOKIE_DOMAIN = "nld.go.kr"  # 이 도메인의 쿠키만 받아 온다.
LOGIN_WAIT_SECONDS = 600  # 로그인 창을 기다리는 최대 시간
# 목록에서 뺄 상태 (공백은 지우고 비교한다)
DONE_STATUSES = ("반납완료", "취소", "반려", "제공불가", "택배접수(반납)")

_fetch_lock = threading.Lock()
_status: dict[str, Any] = {"checked_at": 0.0, "logged_in": None, "error": None}
_login_lock = threading.Lock()
_login: dict[str, Any] = {"state": "idle", "message": None}  # idle | waiting | done | failed


# ---------------------------------------------------------------- 파일

def _data_dir() -> Path:
    d = get_settings().booknarae_data_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(name: str) -> dict | None:
    p = _data_dir() / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(name: str, data: dict) -> None:
    p = _data_dir() / name
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _drop_session() -> None:
    (_data_dir() / "session.json").unlink(missing_ok=True)


# ---------------------------------------------------------------- 쿠키

def _jar_from(cookies: list[dict]) -> http.cookiejar.CookieJar:
    jar = http.cookiejar.CookieJar()
    for c in cookies:
        domain = c["domain"]
        dot = domain.startswith(".")
        expires = c.get("expires")
        session = c.get("session", True) or not expires or expires < 0
        jar.set_cookie(
            http.cookiejar.Cookie(
                version=0, name=c["name"], value=c["value"], port=None, port_specified=False,
                domain=domain, domain_specified=dot, domain_initial_dot=dot,
                path=c.get("path") or "/", path_specified=True, secure=bool(c.get("secure")),
                expires=None if session else int(expires), discard=bool(session),
                comment=None, comment_url=None, rest={},
            )
        )
    return jar


def _jar_to(jar: http.cookiejar.CookieJar) -> list[dict]:
    return [
        {
            "name": c.name, "value": c.value, "domain": c.domain, "path": c.path,
            "secure": c.secure, "expires": c.expires, "session": c.expires is None,
        }
        for c in jar
        if c.domain.lstrip(".").endswith(COOKIE_DOMAIN)
    ]


# ---------------------------------------------------------------- 목록 받기와 읽기

class _Tables(HTMLParser):
    """페이지의 모든 표를 [행][칸] 글자로 모은다. 표 안의 표도 따로 모은다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._stack: list[list[list[str]]] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._stack[-1].append([])
        elif tag in ("td", "th") and self._stack:
            if not self._stack[-1]:
                self._stack[-1].append([])
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._stack:
            self._stack[-1][-1].append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _parse_date(s: str) -> str | None:
    m = re.search(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})", s)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return None


def _col(header: list[str], *keys: str) -> int | None:
    for k in keys:
        for i, h in enumerate(header):
            if k in h.replace(" ", ""):
                return i
    return None


def parse_loans(html: str) -> list[dict] | None:
    """대출 목록 표를 읽는다. 반납 예정일 열이 있는 표를 못 찾으면 None."""
    p = _Tables()
    p.feed(html)
    for rows in p.tables:
        for hi, header in enumerate(rows):
            due_i = _col(header, "반납예정", "반납기한", "반납일")
            if due_i is None:
                continue
            title_i = _col(header, "도서명", "자료명", "서명", "제목", "책이름")
            lent_i = _col(header, "대출일", "발송일", "신청일")
            status_i = _col(header, "상태", "진행")
            loans = []
            for r in rows[hi + 1:]:
                if len(r) < max(2, len(header) // 2):
                    continue  # "내역이 없습니다" 같은 합친 칸
                cell = lambda i: r[i] if i is not None and i < len(r) else ""  # noqa: E731
                title = cell(title_i) or max(r, key=len)
                status = cell(status_i)
                if any(s in status.replace(" ", "") for s in DONE_STATUSES):
                    continue
                loans.append({
                    "title": title,
                    "status": status or None,
                    "lent_on": _parse_date(cell(lent_i)),
                    "due_on": _parse_date(cell(due_i)),
                })
            loans.sort(key=lambda x: (x["due_on"] is None, x["due_on"] or "", x["title"]))
            return loans
    return None


def _looks_logged_out(final_url: str, html: str) -> bool:
    if "login" in final_url.lower():
        return True
    if "로그아웃" in html:
        return False
    low = html.lower()
    return 'type="password"' in low or "type='password'" in low or bool(re.search(r"alert\([^)]*로그인", html))


def _decode(body: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I) or re.search(rb'charset=["\']?([\w-]+)', body[:3000])
    enc = (m[1].decode() if isinstance(m[1], bytes) else m[1]) if m else "utf-8"
    try:
        return body.decode(enc)
    except (LookupError, UnicodeDecodeError):
        return body.decode("cp949", errors="replace")


def _fetch(cookies: list[dict], user_agent: str | None) -> tuple[bool, list[dict] | None, list[dict]]:
    """(로그인 상태인지, 대출 목록, 갱신된 쿠키). 목록 표를 못 읽으면 ValueError."""
    jar = _jar_from(cookies)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(LIST_URL, headers={
        "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "ko-KR,ko;q=0.9",
    })
    with opener.open(req, timeout=20) as resp:
        html = _decode(resp.read(), resp.headers.get("Content-Type", ""))
        final_url = resp.geturl()
    if _looks_logged_out(final_url, html):
        return False, None, _jar_to(jar)
    loans = parse_loans(html)
    if loans is None:
        # 사이트 구조가 예상과 다르다. 고칠 수 있게 받은 페이지를 남겨 둔다.
        (_data_dir() / "last_page.html").write_text(html, encoding="utf-8")
        raise ValueError(f"대출 목록 표를 찾지 못했습니다. 받은 페이지를 {_data_dir() / 'last_page.html'} 에 저장했습니다.")
    return True, loans, _jar_to(jar)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check(session: dict) -> None:
    """저장된 쿠키로 목록을 받아 캐시와 상태를 갱신한다. _fetch_lock 안에서 부른다."""
    try:
        ok, loans, cookies = _fetch(session["cookies"], session.get("user_agent"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        _status.update(checked_at=time.time(), error=str(getattr(e, "reason", e)))
        return
    _status.update(checked_at=time.time(), error=None, logged_in=ok)
    if ok:
        _write_json("session.json", {**session, "cookies": cookies})
        _write_json("loans.json", {"fetched_at": _now_iso(), "loans": loans})
    else:
        _drop_session()  # 만료된 쿠키로 사이트를 계속 두드리지 않는다.


# ---------------------------------------------------------------- 로그인 창

def _find_browser() -> str | None:
    s = get_settings().booknarae_browser
    if s:
        return s if Path(s).is_file() else None
    for p in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ):
        if Path(p).is_file():
            return p
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("google-chrome")


def _http_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=3) as r:
        return json.loads(r.read())


def _cdp(ws_url: str, method: str, params: dict | None = None) -> dict:
    from websockets.sync.client import connect  # uvicorn[standard]와 함께 설치된다.

    with connect(ws_url, max_size=None, open_timeout=5) as ws:
        ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv(timeout=10))
            if msg.get("id") == 1:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message", str(msg["error"])))
                return msg.get("result", {})


def _set_login(state: str, message: str | None = None) -> None:
    _login.update(state=state, message=message)


def _login_worker(exe: str) -> None:
    profile = _data_dir() / "browser-profile"
    port_file = profile / "DevToolsActivePort"
    port_file.unlink(missing_ok=True)
    subprocess.Popen(
        [exe, f"--user-data-dir={profile}", "--remote-debugging-port=0",
         "--no-first-run", "--no-default-browser-check", "--new-window", LIST_URL],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        if port_file.is_file() and port_file.read_text().strip():
            break
        time.sleep(0.5)
    else:
        _set_login("failed", "로그인 창을 열지 못했습니다. 이전에 열어 둔 책나래 로그인 창이 있으면 닫고 다시 시도하세요.")
        return
    base = f"http://127.0.0.1:{int(port_file.read_text().split()[0])}"

    try:
        version = _http_json(f"{base}/json/version")
    except (OSError, ValueError) as e:
        _set_login("failed", f"브라우저에 연결하지 못했습니다: {e}")
        return
    ws_url, user_agent = version["webSocketDebuggerUrl"], version.get("User-Agent")

    deadline = time.time() + LOGIN_WAIT_SECONDS
    last_urls: tuple[str, ...] = ()
    last_try = 0.0
    while time.time() < deadline:
        time.sleep(1.5)
        try:
            tabs = _http_json(f"{base}/json/list")
        except (OSError, ValueError):
            _set_login("failed", "로그인 창이 닫혔습니다.")
            return
        urls = tuple(sorted(t.get("url", "") for t in tabs if t.get("type") == "page"))
        # 창의 주소가 바뀌었을 때(로그인 후 이동)나 20초마다 한 번씩만 사이트에 확인한다.
        if urls == last_urls and time.time() - last_try < 20:
            continue
        last_urls, last_try = urls, time.time()
        if all("login" in u.lower() for u in urls if COOKIE_DOMAIN in u):
            continue  # 아직 로그인 화면이다.
        try:
            raw = _cdp(ws_url, "Storage.getCookies").get("cookies", [])
        except Exception:  # noqa: BLE001 - 창이 닫히는 중일 수 있다. 다음 차례에 다시 본다.
            continue
        cookies = [c for c in raw if c.get("domain", "").lstrip(".").endswith(COOKIE_DOMAIN)]
        session = {"cookies": cookies, "user_agent": user_agent}
        with _fetch_lock:
            _check(session)
            ok = _status["logged_in"] and not _status["error"]
        if ok:
            _set_login("done")
            try:
                _cdp(ws_url, "Browser.close")
            except Exception:  # noqa: BLE001
                pass
            return
    _set_login("failed", "로그인을 기다리는 시간이 지났습니다.")


# ---------------------------------------------------------------- API

@router.get("")
def loans(refresh: bool = False) -> dict:
    s = get_settings()
    with _fetch_lock:
        session = _read_json("session.json")
        if not session:
            _status["logged_in"] = False
        elif refresh or time.time() - _status["checked_at"] > s.booknarae_cache_minutes * 60:
            _check(session)
        cache = _read_json("loans.json") or {}
        return {
            "logged_in": bool(_status["logged_in"]),
            "error": _status["error"],
            "fetched_at": cache.get("fetched_at"),
            "loans": cache.get("loans", []),
            "login": dict(_login),
            "site_url": LIST_URL,
        }


@router.post("/login")
def start_login() -> dict:
    with _login_lock:
        if _login["state"] == "waiting":
            return dict(_login)
        exe = _find_browser()
        if not exe:
            raise HTTPException(400, "Edge나 Chrome을 찾지 못했습니다. backend\\.env 에 BOOKNARAE_BROWSER=브라우저 exe 경로 를 지정하세요.")
        _set_login("waiting")
        threading.Thread(target=_safe_worker, args=(exe,), daemon=True).start()
        return dict(_login)


def _safe_worker(exe: str) -> None:
    try:
        _login_worker(exe)
    except Exception as e:  # noqa: BLE001
        _set_login("failed", f"로그인 처리 중 오류: {e}")


@router.get("/login")
def login_status() -> dict:
    return dict(_login)
