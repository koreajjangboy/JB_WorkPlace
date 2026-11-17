def main() -> None:
    """`uv run jb-workplace`로 백엔드 서버를 띄운다 (이 PC에서만 접속 가능).

    자동 재시작(reload)은 기본으로 끈다. 켜 두면 WorkPlace 작업이 WorkPlace 자신의 코드를 고칠 때
    서버가 다시 시작되면서 실행 중인 그 작업이 중단된다. 개발할 때만 JB_WORKPLACE_RELOAD=1 로 켠다.
    """
    import os

    import uvicorn

    reload = os.environ.get("JB_WORKPLACE_RELOAD") == "1"
    uvicorn.run("jb_workplace.main:app", host="127.0.0.1", port=8000, reload=reload)
