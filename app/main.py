"""FastAPI application entry point for the API and production React build."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.metadata import router as metadata_router
from app.api.afr_trade import router as afr_trade_router
from app.api.ui_support import router as ui_support_router


DISCLAIMER = (
    "Independent portfolio demonstration — not an official African Union or "
    "STATAFRIC platform."
)
ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = ROOT / "frontend" / "dist"
LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Log lifecycle events without performing network or database work."""
    LOGGER.info("Application startup environment=%s", settings.environment)
    yield
    LOGGER.info("Application shutdown")


app = FastAPI(title=settings.app_name, debug=False, lifespan=lifespan)

if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
    )


@app.middleware("http")
async def production_headers_and_failure_logging(request: Request, call_next):
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        LOGGER.exception(
            "Unhandled request failure method=%s path=%s",
            request.method,
            request.url.path,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    if response.status_code >= 500:
        LOGGER.error(
            "Request failed method=%s path=%s status=%s elapsed_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            (perf_counter() - started) * 1000,
        )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://fastapi.tiangolo.com; font-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response

app.include_router(metadata_router)
app.include_router(afr_trade_router)
app.include_router(ui_support_router)


@app.get("/health")
def read_health() -> dict[str, str]:
    """Return the service health status."""
    return {
        "status": "healthy",
        "service": settings.app_name,
    }


if (FRONTEND_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="frontend-assets",
    )


@app.get("/", include_in_schema=False)
def read_root():
    """Serve the production UI, with JSON metadata as a development fallback."""
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {
        "name": settings.app_name,
        "status": "running",
        "documentation": "/docs",
        "disclaimer": DISCLAIMER,
    }


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_route(full_path: str):
    """Return React's shell for client routes without masking API 404s."""
    protected = {"api", "docs", "redoc", "openapi.json", "health", "assets"}
    first_segment = full_path.split("/", 1)[0]
    if first_segment in protected or any(
        segment.startswith(".") for segment in full_path.split("/")
    ):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse(status_code=404, content={"detail": "Frontend build not found"})
