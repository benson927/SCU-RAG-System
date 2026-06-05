from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def get_engine():
    global _engine, _session_factory
    settings = get_settings()
    if not settings.database_enabled:
        return None
    if _engine is None:
        url = normalize_database_url(settings.database_url)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session() -> Generator[Session, None, None]:
    engine = get_engine()
    if engine is None or _session_factory is None:
        raise RuntimeError("DATABASE_URL 尚未設定")
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope():
    session = next(get_session())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database_health() -> dict:
    engine = get_engine()
    if engine is None:
        return {"status": "not_configured"}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "online"}
    except Exception as exc:
        return {"status": "offline", "error": str(exc)}


def get_migration_revision() -> str | None:
    engine = get_engine()
    if engine is None:
        return None
    try:
        with engine.connect() as connection:
            return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except Exception:
        return None
