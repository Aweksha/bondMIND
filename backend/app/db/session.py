from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_url = get_settings().database_url
# SQLite (single-container public demo): allow FastAPI's worker threads to share connections.
_connect_args = {"check_same_thread": False, "timeout": 15} if _url.startswith("sqlite") else {}
engine = create_engine(_url, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
