import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .calendar_api import router as calendar_router
from .config import get_settings
from .runner import recover_orphans
from .sync import run_scan
from .project_changes_api import router as project_changes_router
from .tasks_api import router as tasks_router
from .usage_api import router as usage_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def _scan_in_background() -> None:
    try:
        run_scan()
    except Exception:  # 시작 스캔이 실패해도 서버는 뜨게 한다.
        log.exception("시작 스캔 실패")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        recover_orphans()
    except Exception:
        log.exception("중단된 실행 정리 실패")
    threading.Thread(target=_scan_in_background, daemon=True).start()
    from .takeout import watch_forever

    threading.Thread(target=watch_forever, daemon=True).start()  # Gemini 앱 Takeout 폴더 확인
    from .billing import watch_forever as watch_billing

    threading.Thread(target=watch_billing, daemon=True).start()  # Google Cloud 결제 내보내기
    yield


app = FastAPI(title="JB WorkPlace", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(tasks_router)
app.include_router(project_changes_router)
app.include_router(usage_router)
app.include_router(calendar_router)
