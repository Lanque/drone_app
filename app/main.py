from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.models import Location
from app.services.weather import WeatherServiceError, get_current_wind
from pathlib import Path

from fastapi.staticfiles import StaticFiles
from app.schemas import (
    FlightConditions,
    LocationCreate,
    LocationResponse,
    SunConditions,
    WindConditions,
)

from app.services.sun import SunServiceError, get_sun_conditions
import asyncio

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

@app.post(
    "/locations",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_location(
    location_data: LocationCreate,
    db: Session = Depends(get_db),
) -> Location:
    location = Location(**location_data.model_dump())

    db.add(location)
    db.commit()
    db.refresh(location)

    return location

@app.delete(
    "/locations/{location_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_location(
    location_id: int,
    db: Session = Depends(get_db),
) -> None:
    location = db.get(Location, location_id)

    if location is None:
        raise HTTPException(
            status_code=404,
            detail="Location not found",
        )

    db.delete(location)
    db.commit()

@app.get(
    "/locations/{location_id}/weather",
    response_model=WindConditions,
)
async def get_location_weather(
    location_id: int,
    db: Session = Depends(get_db),
) -> WindConditions:
    location = db.get(Location, location_id)

    if location is None:
        raise HTTPException(
            status_code=404,
            detail="Location not found",
        )

    try:
        wind_data = await get_current_wind(
            latitude=float(location.latitude),
            longitude=float(location.longitude),
        )
    except WeatherServiceError as error:
        raise HTTPException(
            status_code=502,
            detail="Weather service unavailable",
        ) from error

    return WindConditions(**wind_data)

@app.get(
    "/locations/{location_id}/sun",
    response_model=SunConditions,
)
async def get_location_sun(
    location_id: int,
    db: Session = Depends(get_db),
) -> SunConditions:
    location = db.get(Location, location_id)

    if location is None:
        raise HTTPException(
            status_code=404,
            detail="Location not found",
        )

    try:
        sun_data = await get_sun_conditions(
            latitude=float(location.latitude),
            longitude=float(location.longitude),
        )
    except SunServiceError as error:
        raise HTTPException(
            status_code=502,
            detail="Sun service unavailable",
        ) from error

    return SunConditions(**sun_data)

@app.get(
    "/locations/{location_id}/flight-conditions",
    response_model=FlightConditions,
)
async def get_flight_conditions(
    location_id: int,
    db: Session = Depends(get_db),
) -> FlightConditions:
    location = db.get(Location, location_id)

    if location is None:
        raise HTTPException(
            status_code=404,
            detail="Location not found",
        )

    latitude = float(location.latitude)
    longitude = float(location.longitude)

    weather_result, sun_result = await asyncio.gather(
        get_current_wind(latitude, longitude),
        get_sun_conditions(latitude, longitude),
        return_exceptions=True,
    )

    if isinstance(sun_result, SunServiceError):
        raise HTTPException(
            status_code=502,
            detail="Sun service unavailable",
        ) from sun_result

    if isinstance(sun_result, Exception):
        raise HTTPException(
            status_code=502,
            detail="Sun service unavailable",
        ) from sun_result

    weather_available = not isinstance(weather_result, Exception)
    wind = (
        WindConditions(**weather_result)
        if weather_available
        else None
    )

    return FlightConditions(
        location=LocationResponse.model_validate(location),
        wind=wind,
        weather_available=weather_available,
        sun=SunConditions(**sun_result),
    )
frontend_directory = Path(__file__).resolve().parent.parent / "frontend"

app.mount(
    "/",
    StaticFiles(directory=frontend_directory, html=True),
    name="frontend",
)
