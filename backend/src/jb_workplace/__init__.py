def main() -> None:
    """`uv run jb-workplace`로 백엔드 서버를 띄운다 (이 PC에서만 접속 가능)."""
    import uvicorn

    uvicorn.run("jb_workplace.main:app", host="127.0.0.1", port=8000, reload=True)
