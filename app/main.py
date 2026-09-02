"""FastAPI application entry point."""

from fastapi import FastAPI

from app.core.config import settings
from app.api.metadata import router as metadata_router


DISCLAIMER = (
    "Independent portfolio demonstration project. "
    "Not an official African Union or STATAFRIC platform."
)

app = FastAPI(title=settings.app_name)
app.include_router(metadata_router)


@app.get("/")
def read_root() -> dict[str, str]:
    """Return basic service metadata."""
    return {
        "name": settings.app_name,
        "status": "running",
        "documentation": "/docs",
        "disclaimer": DISCLAIMER,
    }


@app.get("/health")
def read_health() -> dict[str, str]:
    """Return the service health status."""
    return {
        "status": "healthy",
        "service": settings.app_name,
    }
