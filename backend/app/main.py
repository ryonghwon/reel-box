import hmac
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from . import db
from .config import DESKTOP, TOKEN
from .routes import browser, exports, jobs, recordings, saved, settings


@asynccontextmanager
async def lifespan(app):
    if len(TOKEN) < 24:
        raise RuntimeError("API_TOKEN must contain at least 24 characters")
    db.init()
    if DESKTOP:
        from .browser_reconcile import reconcile_existing

        reconcile_existing()
    runner = None
    if DESKTOP:
        from .desktop_queue import LocalQueue

        runner = LocalQueue()
        runner.start()
        app.state.local_queue = runner
    try:
        yield
    finally:
        if runner:
            runner.stop()


def authorize(x_api_key: str = Header(default="")):
    if not TOKEN or not hmac.compare_digest(TOKEN, x_api_key):
        raise HTTPException(401, "인증되지 않은 요청입니다.")


app = FastAPI(
    title="Reel Box",
    version="1.5.0",
    lifespan=lifespan,
    dependencies=[Depends(authorize)],
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


for router in (
    settings.router,
    jobs.router,
    saved.router,
    exports.router,
    recordings.router,
    browser.router,
):
    app.include_router(router)
