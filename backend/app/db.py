import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def build_engine(db_url: str):
    connect_args = {}
    pool_kwargs = {}
    if db_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        if ":memory:" in db_url:
            from sqlalchemy.pool import StaticPool
            pool_kwargs = {"poolclass": StaticPool}
    elif db_url.startswith("postgresql"):
        connect_args = {"connect_timeout": 2}

    return create_engine(db_url, pool_pre_ping=True, connect_args=connect_args, **pool_kwargs)


active_url = settings.database_url

if active_url.startswith("postgresql"):
    try:
        temp_engine = build_engine(active_url)
        with temp_engine.connect() as test_conn:
            pass
        engine = temp_engine
    except Exception as exc:
        print(f"[DB Warning] PostgreSQL at {active_url} is unreachable ({exc}).")
        print("[DB Warning] Automatically falling back to local SQLite database: sqlite:///./hub.db")
        active_url = "sqlite:///./hub.db"
        engine = build_engine(active_url)
else:
    engine = build_engine(active_url)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
