"""Database configuration: SQLAlchemy engine, session factory and base class.

Also exposes ``init_db`` to create all tables and a ``get_db`` FastAPI
dependency that yields a short-lived session.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///./finance.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)  # pylint: disable=invalid-name


class Base(DeclarativeBase):  # pylint: disable=too-few-public-methods
    """Declarative base class for all ORM models."""


def init_db():
    """Create all tables declared on ``Base.metadata``.

    The local import ensures model classes register themselves on
    ``Base.metadata`` before ``create_all`` runs, avoiding a circular import
    at module load time.
    """
    # pylint: disable=import-outside-toplevel,unused-import
    from models import User, Category, Transaction  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    """Yield a database session and guarantee it is closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
