"""JB WorkPlace 사용량 기록 도우미 (파일 하나, 표준 라이브러리만 사용).

다른 프로젝트에 이 파일을 복사해 두고, AI API를 호출한 뒤 사용량을 보낸다.
WorkPlace 서버가 꺼져 있거나 오류가 나도 앱 동작에는 영향이 없다 (조용히 무시).

    from jb_usage import record_usage, record_openai, record_gemini

    # 아무 provider (단위는 자유: token, char, credit, second, image, request …)
    record_usage("runway", unit="credit", quantity=50, model="gen4_turbo", kind="video")
    record_usage("elevenlabs", unit="char", quantity=len(text), model="eleven_multilingual_v2", kind="audio")

    # 응답 객체에서 토큰 수를 꺼내 주는 도우미
    resp = openai_client.chat.completions.create(...)
    record_openai(resp)
    resp = gemini_client.models.generate_content(...)
    record_gemini(resp)

환경 변수
    JB_WORKPLACE_URL   기본값 http://127.0.0.1:8000
    JB_WORKPLACE_PROJECT  프로젝트 이름 (기본값: 현재 폴더 이름)
    JB_USAGE_DISABLED=1   기록하지 않음
"""

from __future__ import annotations

import json
import os
import threading
import urllib.request
from pathlib import Path
from typing import Any

_URL = os.environ.get("JB_WORKPLACE_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/usage/records"
_TIMEOUT = 2.0


def _project() -> str:
    return os.environ.get("JB_WORKPLACE_PROJECT") or Path.cwd().name


def _post(payload: dict[str, Any]) -> None:
    try:
        req = urllib.request.Request(
            _URL,
            data=json.dumps(payload, default=str).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=_TIMEOUT).close()
    except Exception:  # 기록 실패가 앱을 멈추게 하지 않는다
        pass


def record_usage(
    provider: str,
    unit: str,
    quantity: float = 0,
    *,
    model: str | None = None,
    kind: str = "text",
    project: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float | None = None,
    meta: dict[str, Any] | None = None,
    background: bool = True,
) -> None:
    """사용량 한 건을 WorkPlace에 보낸다. background=True면 응답을 기다리지 않는다."""
    if os.environ.get("JB_USAGE_DISABLED") == "1":
        return
    payload = {
        "provider": provider,
        "unit": unit,
        "quantity": quantity or (input_tokens + output_tokens),
        "model": model,
        "kind": kind,
        "project": project or _project(),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "meta": meta,
    }
    if background:
        threading.Thread(target=_post, args=(payload,), daemon=True).start()
    else:
        _post(payload)


def _get(obj: Any, *names: str) -> Any:
    for name in names:
        if obj is None:
            return None
        obj = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    return obj


def record_openai(response: Any, *, provider: str = "openai", project: str | None = None, kind: str = "text") -> None:
    """OpenAI 응답(Chat Completions / Responses / Embeddings)의 usage를 기록한다.

    OpenAI SDK로 다른 서비스를 부르는 경우(Upstage 등)는 provider 이름을 바꿔 준다.
    """
    usage = _get(response, "usage")
    if usage is None:
        return
    inp = _get(usage, "prompt_tokens") or _get(usage, "input_tokens") or 0
    out = _get(usage, "completion_tokens") or _get(usage, "output_tokens") or 0
    record_usage(provider, "token", model=_get(response, "model"), kind=kind, project=project,
                 input_tokens=int(inp), output_tokens=int(out))


def record_gemini(response: Any, *, model: str | None = None, project: str | None = None, kind: str = "text") -> None:
    """google-genai 응답의 usage_metadata를 기록한다."""
    meta = _get(response, "usage_metadata")
    if meta is None:
        return
    inp = _get(meta, "prompt_token_count") or 0
    out = (_get(meta, "candidates_token_count") or 0) + (_get(meta, "thoughts_token_count") or 0)
    record_usage("gemini", "token", model=model or _get(response, "model_version"), kind=kind, project=project,
                 input_tokens=int(inp), output_tokens=int(out))
