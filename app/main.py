from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.models import Location
from app.schemas import LocationResponse

app = FastAPI(
    title="Drone Locations API",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/database")
def database_health_check() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503,
            detail="Database connection unavailable",
        ) from error

    return {"status": "ok"}


@app.get("/locations", response_model=list[LocationResponse])
def list_locations(db: Session = Depends(get_db)) -> list[Location]:
    statement = select(Location).order_by(Location.created_at.desc())

    return list(db.scalars(statement).all())