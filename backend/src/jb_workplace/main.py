import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .config import get_settings
from .sync import run_scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def _scan_in_background() -> None:
    try:
        run_scan()
    except Exception:  # 시작 스캔이 실패해도 서버는 뜨게 한다.
        log.exception("시작 스캔 실패")


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_scan_in_background, daemon=True).start()
    yield


app = FastAPI(title="JB WorkPlace", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
