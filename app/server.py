"""FastAPI app factory for the ALEXIS MVP control panel.

The app:

* mounts /static  -> app/web (the control-panel shell + css + js)
* mounts /dashboards -> paths.viz_dir() (the *_live.html viewers)
* serves GET / -> app/web/index.html
* attaches the three API routers (classify, dashboards, settings)
* installs a CORS allow-loopback policy
* installs a global exception handler that returns {"error": "<str>"}
  JSON and never leaks stack traces (it logs server-side instead).

Bind ONLY to 127.0.0.1 (the launcher does this); the app itself is
transport-agnostic.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.paths import app_root, viz_dir

from app.api import classify as classify_router
from app.api import dashboards as dashboards_router
from app.api import settings as settings_router
from app.api import jobs as jobs_router


_log = logging.getLogger("alexis.server")
# Loopback origins only — covers 127.0.0.1, localhost, and IPv6 [::1] so
# the UI works whether the WebView2 host or a smoke-testing browser uses
# any of those hostnames. Allow http only; never expose this server outside
# the local machine.
_LOOPBACK_RE = re.compile(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$")

# Reject oversize JSON bodies before they hit a route. 1 MiB is far more
# than the classifier or settings endpoints will ever need; protects the
# desktop process from a runaway frontend fetch loop or fuzzer.
_MAX_BODY_BYTES = 1 * 1024 * 1024


def _web_dir() -> Path:
    """app/web is bundled — lives next to the app package under app_root()."""
    return app_root() / "app" / "web"


def create_app() -> FastAPI:
    app = FastAPI(
        title="ALEXIS",
        version="0.1.0-mvp",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # ----- CORS: loopback only -----
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_LOOPBACK_RE.pattern,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # ----- Body size guard -----
    @app.middleware("http")
    async def _limit_body(request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > _MAX_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"error": "request body too large"},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid Content-Length header"},
                )
        return await call_next(request)

    # ----- Global exception handler -----
    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        _log.exception("[err] unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": f"internal error: {type(exc).__name__}"},
        )

    @app.exception_handler(HTTPException)
    async def _http_exc(_request: Request, exc: HTTPException) -> JSONResponse:
        # Preserve status code; render detail under "error" so the
        # client sees a single, stable error shape.
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": str(exc.detail)},
        )

    # ----- Routers -----
    app.include_router(classify_router.router)
    app.include_router(dashboards_router.router)
    app.include_router(settings_router.router)
    app.include_router(jobs_router.router)

    # ----- Static mounts -----
    web = _web_dir()
    if web.is_dir():
        app.mount("/static", StaticFiles(directory=str(web)), name="static")
    else:
        _log.warning("[warn] web dir missing: %s", web)

    viz = viz_dir()
    if viz.is_dir():
        app.mount("/dashboards", StaticFiles(directory=str(viz)), name="dashboards")
    else:
        _log.warning("[warn] viz dir missing: %s", viz)

    # ----- Root: serve the control-panel shell -----
    @app.get("/")
    def root() -> FileResponse:
        index = web / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=500, detail="index.html missing")
        return FileResponse(str(index), media_type="text/html")

    return app
