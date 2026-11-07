import os

os.environ.setdefault("BONDMIND_DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.seed.generate import generate
from app.seed.load import load_all


@pytest.fixture(scope="session")
def seed_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("seed")
    generate(d)
    return d


@pytest.fixture(scope="session")
def session_factory(seed_dir):
    url = os.environ["BONDMIND_DATABASE_URL"]
    kwargs = (
        {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
        if url.startswith("sqlite")
        else {}
    )
    engine = create_engine(url, **kwargs)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        load_all(s, seed_dir)
    return factory


@pytest.fixture(scope="session")
def client(session_factory):
    def _db():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def settings():
    return get_settings()
