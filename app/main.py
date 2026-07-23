import asyncio
import logging
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.models import Location, LocationPhoto
from app.schemas import (
    FlightConditions,
    LocationCreate,
    LocationPhotoResponse,
    LocationResponse,
    LocationUpdate,
    SunConditions,
    WindConditions,
)
from app.services.sun import SunServiceError, get_sun_conditions
from app.services.weather import WeatherServiceError, get_current_wind

app = FastAPI(
    title="Drone Locations API",
    version="0.1.0",
)

logger = logging.getLogger(__name__)

project_directory = Path(__file__).resolve().parent.parent
uploads_directory = project_directory / "uploads"
uploads_directory.mkdir(parents=True, exist_ok=True)

MAX_PHOTO_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}


def build_photo_response(photo: LocationPhoto) -> LocationPhotoResponse:
    return LocationPhotoResponse(
        id=photo.id,
        location_id=photo.location_id,
        original_name=photo.original_name,
        content_type=photo.content_type,
        size_bytes=photo.size_bytes,
        caption=photo.caption,
        url=f"/uploads/locations/{photo.location_id}/{photo.stored_name}",
        created_at=photo.created_at,
    )


def get_photo_path(photo: LocationPhoto) -> Path:
    return (
        uploads_directory
        / "locations"
        / str(photo.location_id)
        / Path(photo.stored_name).name
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


@app.post(
    "/locations/{location_id}/photos",
    response_model=LocationPhotoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_location_photo(
    location_id: int,
    photo: UploadFile = File(...),
    caption: str | None = Form(default=None, max_length=500),
    db: Session = Depends(get_db),
) -> LocationPhotoResponse:
    location = db.get(Location, location_id)

    if location is None:
        raise HTTPException(
            status_code=404,
            detail="Location not found",
        )

    contents = await photo.read(MAX_PHOTO_SIZE_BYTES + 1)
    await photo.close()

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="Image file is empty",
        )

    if len(contents) > MAX_PHOTO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image must be 10 MB or smaller",
        )

    try:
        with Image.open(BytesIO(contents)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError) as error:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid image",
        ) from error

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise HTTPException(
            status_code=400,
            detail="Only JPEG, PNG and WebP images are allowed",
        )

    extension, content_type = ALLOWED_IMAGE_FORMATS[image_format]
    stored_name = f"{uuid4().hex}{extension}"
    original_name = Path(photo.filename or "photo").name[:255]
    location_directory = uploads_directory / "locations" / str(location_id)
    location_directory.mkdir(parents=True, exist_ok=True)
    stored_path = location_directory / stored_name

    try:
        await asyncio.to_thread(stored_path.write_bytes, contents)
    except OSError as error:
        raise HTTPException(
            status_code=500,
            detail="Could not save image file",
        ) from error

    photo_record = LocationPhoto(
        location_id=location_id,
        stored_name=stored_name,
        original_name=original_name,
        content_type=content_type,
        size_bytes=len(contents),
        caption=caption.strip() if caption else None,
    )
    db.add(photo_record)

    try:
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="Could not save image information",
        ) from error

    db.refresh(photo_record)

    return build_photo_response(photo_record)


@app.get(
    "/locations/{location_id}/photos",
    response_model=list[LocationPhotoResponse],
)
def list_location_photos(
    location_id: int,
    db: Session = Depends(get_db),
) -> list[LocationPhotoResponse]:
    location = db.get(Location, location_id)

    if location is None:
        raise HTTPException(
            status_code=404,
            detail="Location not found",
        )

    statement = (
        select(LocationPhoto)
        .where(LocationPhoto.location_id == location_id)
        .order_by(LocationPhoto.created_at.desc())
    )
    photos = db.scalars(statement).all()

    return [build_photo_response(photo) for photo in photos]


@app.delete(
    "/locations/{location_id}/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_location_photo(
    location_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
) -> None:
    statement = select(LocationPhoto).where(
        LocationPhoto.id == photo_id,
        LocationPhoto.location_id == location_id,
    )
    photo = db.scalar(statement)

    if photo is None:
        raise HTTPException(
            status_code=404,
            detail="Photo not found",
        )

    photo_path = get_photo_path(photo)
    staged_path: Path | None = None

    if photo_path.exists():
        staged_path = photo_path.with_name(f".{photo_path.name}.deleting")

        try:
            photo_path.replace(staged_path)
        except OSError as error:
            raise HTTPException(
                status_code=500,
                detail="Could not prepare image file for deletion",
            ) from error

    db.delete(photo)

    try:
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()

        if staged_path is not None:
            staged_path.replace(photo_path)

        raise HTTPException(
            status_code=500,
            detail="Could not delete image information",
        ) from error

    if staged_path is not None:
        try:
            staged_path.unlink()
        except OSError:
            logger.exception("Could not remove image file after database deletion")


@app.patch(
    "/locations/{location_id}",
    response_model=LocationResponse,
)
def update_location(
    location_id: int,
    update_data: LocationUpdate,
    db: Session = Depends(get_db),
):
    location = db.get(Location, location_id)

    if location is None:
        raise HTTPException(
            status_code=404,
            detail="Location not found",
        )
    fields_to_update = update_data.model_dump(exclude_unset=True)
    for field_name, value in fields_to_update.items():
        setattr(location, field_name, value)
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
frontend_directory = project_directory / "frontend"

app.mount(
    "/uploads",
    StaticFiles(directory=uploads_directory),
    name="uploads",
)
app.mount(
    "/",
    StaticFiles(directory=frontend_directory, html=True),
    name="frontend",
)
