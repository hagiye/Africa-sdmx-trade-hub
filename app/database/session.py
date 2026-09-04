"""SQLAlchemy engine and session factory."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from collections.abc import Generator

from app.core.config import settings


engine_options: dict[str, object] = {"pool_pre_ping": True}
if settings.sqlalchemy_database_url.startswith("postgresql"):
    engine_options.update(
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle=300,
    )
    if settings.database_ssl_mode:
        engine_options["connect_args"] = {"sslmode": settings.database_ssl_mode}

engine = create_engine(settings.sqlalchemy_database_url, **engine_options)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db() -> Generator:
    """Yield a transaction-scoped database session for FastAPI."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
