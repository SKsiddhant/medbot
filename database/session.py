"""
Database + Redis session helpers.

`SessionLocal` — SQLAlchemy session factory (audit trail, bookings).
`redis_client` — Redis connection for dialogue-state persistence
                 across pod restarts.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config import settings
from database.models import Base


# ---------------------------------------------------------------------
# SQLAlchemy engine
# ---------------------------------------------------------------------
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create tables if they don't exist. Called on FastAPI startup."""
    logger.info(f"Initialising DB at {settings.DATABASE_URL}")
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------
# Redis (optional — used by dialogue manager in production)
# ---------------------------------------------------------------------
try:
    import redis
    _redis_client = redis.Redis.from_url(
        settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2
    )
    try:
        _redis_client.ping()
        redis_client = _redis_client
        logger.info(f"Redis connected at {settings.REDIS_URL}")
    except Exception:
        redis_client = None
        logger.warning("Redis unavailable — using in-memory session store.")
except ImportError:                          # pragma: no cover
    redis_client = None
    logger.warning("redis-py not installed — using in-memory session store.")
