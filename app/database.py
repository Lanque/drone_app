import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")

    return value


database_url = URL.create(
    drivername="postgresql+psycopg",
    username=get_required_env("DB_USER"),
    password=get_required_env("DB_PASSWORD"),
    host=get_required_env("DB_HOST"),
    port=int(get_required_env("DB_PORT")),
    database=get_required_env("DB_NAME"),
)

engine = create_engine(database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()