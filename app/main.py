import asyncio
import json
import logging
import os
import shutil
from collections.abc import Iterator
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from authlib.integrations.base_client.errors import OAuthError
from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.database import engine, get_db
from app.models import Location, LocationPhoto, User
from app.oauth import (
    GOOGLE_OAUTH_ENABLED,
    OAUTH_SESSION_SECRET,
    oauth,
)
from app.schemas import (
    FlightConditions,
    LocationCreate,
    LocationPhotoResponse,
    LocationResponse,
    LocationUpdate,
    SunConditions,
    WindConditions,
    UserCreate,
    UserResponse,
    LoginRequest,
)
from app.services.sun import SunServiceError, get_sun_conditions
from app.services.weather import WeatherServiceError, get_current_wind
from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

register_heif_opener(thumbnails=False)

COOKIE_SECURE = (
    os.getenv("COOKIE_SECURE", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
TERMS_VERSION = "2026-07-24"
LEGAL_CONTROLLER_NAME = (
    os.getenv("LEGAL_CONTROLLER_NAME", "").strip()
    or "FrameScouti haldaja"
)
LEGAL_CONTACT_EMAIL = (
    os.getenv("LEGAL_CONTACT_EMAIL", "").strip()
    or "Kontakt ei ole veel seadistatud"
)

app = FastAPI(
    title="Drone Locations API",
    version="0.1.0",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=OAUTH_SESSION_SECRET,
    session_cookie="oauth_state",
    max_age=10 * 60,
    same_site="lax",
    https_only=COOKIE_SECURE,
)

logger = logging.getLogger(__name__)

project_directory = Path(__file__).resolve().parent.parent
uploads_directory = project_directory / "uploads"
uploads_directory.mkdir(parents=True, exist_ok=True)
legal_templates_directory = project_directory / "app" / "templates"

MAX_PHOTO_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}
JPEG_INPUT_FORMATS = {"JPEG", "MPO"}
PHONE_IMAGE_FORMATS = {"HEIF", "HEIC"}


def record_terms_acceptance(user: User) -> None:
    if user.terms_version == TERMS_VERSION:
        return

    user.terms_accepted_at = datetime.now(timezone.utc)
    user.terms_version = TERMS_VERSION


def render_legal_page(filename: str) -> HTMLResponse:
    template = (legal_templates_directory / filename).read_text(
        encoding="utf-8",
    )
    rendered = (
        template
        .replace("{{CONTROLLER_NAME}}", escape(LEGAL_CONTROLLER_NAME))
        .replace("{{CONTACT_EMAIL}}", escape(LEGAL_CONTACT_EMAIL))
        .replace("{{TERMS_VERSION}}", escape(TERMS_VERSION))
    )
    return HTMLResponse(rendered)


def normalize_uploaded_image(
    contents: bytes,
) -> tuple[bytes, str]:
    try:
        with Image.open(BytesIO(contents)) as image:
            image_format = image.format

            if (
                image_format not in JPEG_INPUT_FORMATS
                and image_format not in ALLOWED_IMAGE_FORMATS
                and image_format not in PHONE_IMAGE_FORMATS
            ):
                detected_format = image_format or "unknown"
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Only JPEG, PNG, WebP and HEIC images "
                        "are allowed. "
                        f"Detected format: {detected_format}"
                    ),
                )

            image.load()
            normalized_image = ImageOps.exif_transpose(image)
            output_format = (
                "JPEG"
                if (
                    image_format in JPEG_INPUT_FORMATS
                    or image_format in PHONE_IMAGE_FORMATS
                )
                else image_format
            )
            output = BytesIO()

            if output_format == "JPEG":
                if normalized_image.mode not in {"RGB", "L"}:
                    normalized_image = normalized_image.convert("RGB")
                normalized_image.save(
                    output,
                    format="JPEG",
                    quality=90,
                    optimize=True,
                )
            elif output_format == "PNG":
                normalized_image.save(
                    output,
                    format="PNG",
                    optimize=True,
                )
            else:
                normalized_image.save(
                    output,
                    format="WEBP",
                    quality=90,
                    method=6,
                )

            return output.getvalue(), output_format
    except HTTPException:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
    ) as error:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid image",
        ) from error


def build_photo_response(photo: LocationPhoto) -> LocationPhotoResponse:
    return LocationPhotoResponse(
        id=photo.id,
        location_id=photo.location_id,
        original_name=photo.original_name,
        content_type=photo.content_type,
        size_bytes=photo.size_bytes,
        caption=photo.caption,
        url=(
            f"/locations/{photo.location_id}"
            f"/photos/{photo.id}/content"
        ),
        created_at=photo.created_at,
    )


def get_photo_path(photo: LocationPhoto) -> Path:
    return (
        uploads_directory
        / "locations"
        / str(photo.location_id)
        / Path(photo.stored_name).name
    )


def set_access_token_cookie(
    response: Response,
    user_id: int,
) -> None:
    response.set_cookie(
        key="access_token",
        value=create_access_token(user_id),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=60 * 60,
        path="/",
    )


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/privacy", response_class=HTMLResponse)
def privacy_notice() -> HTMLResponse:
    return render_legal_page("privacy.html")


@app.get("/terms", response_class=HTMLResponse)
def terms_of_use() -> HTMLResponse:
    return render_legal_page("terms.html")


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

@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    normalized_email = str(user_data.email).strip().lower()

    existing_user = db.scalar(
        select(User).where(User.email == normalized_email)
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    user = User(
        email=normalized_email,
        display_name=user_data.display_name.strip(),
        password_hash=hash_password(user_data.password),
    )
    record_terms_acceptance(user)

    db.add(user)

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from error

    db.refresh(user)

    return user

@app.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout_user(response: Response) -> None:
    response.delete_cookie(
        key="access_token",
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )


@app.get("/auth/google")
async def start_google_login(
    request: Request,
) -> RedirectResponse:
    if not GOOGLE_OAUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google login is not configured",
        )

    redirect_uri = request.url_for("google_auth_callback")

    return await oauth.google.authorize_redirect(
        request,
        redirect_uri,
    )


@app.get(
    "/auth/google/callback",
    name="google_auth_callback",
)
async def google_auth_callback(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if not GOOGLE_OAUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google login is not configured",
        )

    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        request.session.clear()
        return RedirectResponse(
            url="/?auth_error=google",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    request.session.clear()
    user_info: dict[str, Any] | None = token.get("userinfo")

    if (
        not user_info
        or not user_info.get("sub")
        or not user_info.get("email")
        or user_info.get("email_verified") is not True
    ):
        return RedirectResponse(
            url="/?auth_error=google_profile",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    google_subject = str(user_info["sub"])
    normalized_email = str(user_info["email"]).strip().lower()

    user = db.scalar(
        select(User).where(
            User.google_subject == google_subject,
        )
    )

    if user is None:
        user = db.scalar(
            select(User).where(User.email == normalized_email)
        )

    if user is None:
        display_name = (
            str(user_info.get("name") or "").strip()
            or normalized_email.split("@", maxsplit=1)[0]
        )
        user = User(
            email=normalized_email,
            display_name=display_name[:120],
            password_hash=None,
            google_subject=google_subject,
        )
        db.add(user)
    elif (
        user.google_subject is not None
        and user.google_subject != google_subject
    ):
        return RedirectResponse(
            url="/?auth_error=google_account_conflict",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    else:
        user.google_subject = google_subject

    record_terms_acceptance(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            url="/?auth_error=google_account_conflict",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db.refresh(user)

    response = RedirectResponse(
        url="/",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_access_token_cookie(response, user.id)

    return response


@app.post(
    "/auth/login",
    response_model=UserResponse,
)
def login_user(
    login_data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    normalized_email = str(login_data.email).strip().lower()

    user = db.scalar(
        select(User).where(User.email == normalized_email)
    )

    if (
        user is None
        or user.password_hash is None
        or not verify_password(
            login_data.password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    record_terms_acceptance(user)

    try:
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update account terms",
        ) from error

    set_access_token_cookie(response, user.id)

    return user

def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    if access_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    user_id = decode_access_token(access_token)

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )

    return user


def get_owned_location(
    location_id: int,
    current_user: User,
    db: Session,
) -> Location:
    statement = select(Location).where(
        Location.id == location_id,
        Location.owner_id == current_user.id,
    )
    location = db.scalar(statement)

    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        )

    return location


@app.get(
    "/auth/me",
    response_model=UserResponse,
)
def get_authenticated_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@app.get("/auth/export")
def export_account_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    locations = list(
        db.scalars(
            select(Location)
            .where(Location.owner_id == current_user.id)
            .order_by(Location.created_at)
        ).all()
    )

    export_data: dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {
            "id": current_user.id,
            "email": current_user.email,
            "display_name": current_user.display_name,
            "created_at": current_user.created_at.isoformat(),
            "authentication_provider": (
                "google"
                if current_user.google_subject
                else "password"
            ),
            "terms_accepted_at": (
                current_user.terms_accepted_at.isoformat()
                if current_user.terms_accepted_at
                else None
            ),
            "terms_version": current_user.terms_version,
        },
        "locations": [],
    }

    archive = SpooledTemporaryFile(
        max_size=50 * 1024 * 1024,
        mode="w+b",
    )

    with ZipFile(
        archive,
        mode="w",
        compression=ZIP_DEFLATED,
    ) as zip_file:
        for location in locations:
            photos = list(
                db.scalars(
                    select(LocationPhoto)
                    .where(
                        LocationPhoto.location_id == location.id,
                    )
                    .order_by(LocationPhoto.created_at)
                ).all()
            )
            photo_data = []

            for photo in photos:
                photo_data.append(
                    {
                        "id": photo.id,
                        "original_name": photo.original_name,
                        "content_type": photo.content_type,
                        "size_bytes": photo.size_bytes,
                        "caption": photo.caption,
                        "created_at": photo.created_at.isoformat(),
                    }
                )
                photo_path = get_photo_path(photo)

                if photo_path.is_file():
                    safe_name = (
                        Path(photo.original_name).name
                        .replace("\\", "_")
                        .replace("/", "_")
                    )
                    zip_file.write(
                        photo_path,
                        arcname=(
                            f"photos/location-{location.id}/"
                            f"{photo.id}-{safe_name}"
                        ),
                    )

            export_data["locations"].append(
                {
                    "id": location.id,
                    "name": location.name,
                    "latitude": float(location.latitude),
                    "longitude": float(location.longitude),
                    "description": location.description,
                    "no_fly_zone_status": (
                        location.no_fly_zone_status
                    ),
                    "created_at": location.created_at.isoformat(),
                    "photos": photo_data,
                }
            )

        zip_file.writestr(
            "framescout-data.json",
            json.dumps(
                export_data,
                ensure_ascii=False,
                indent=2,
            ),
        )

    archive.seek(0)

    def stream_archive() -> Iterator[bytes]:
        try:
            while chunk := archive.read(1024 * 1024):
                yield chunk
        finally:
            archive.close()

    filename = (
        f"framescout-export-"
        f"{datetime.now(timezone.utc).date().isoformat()}.zip"
    )
    return StreamingResponse(
        stream_archive(),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
        },
    )


@app.delete(
    "/auth/account",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_account(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    location_ids = list(
        db.scalars(
            select(Location.id).where(
                Location.owner_id == current_user.id,
            )
        ).all()
    )
    locations_root = uploads_directory / "locations"
    staged_paths: list[tuple[Path, Path]] = []

    try:
        for location_id in location_ids:
            original_path = locations_root / str(location_id)

            if not original_path.exists():
                continue

            staged_path = locations_root / (
                f".account-{current_user.id}-"
                f"{location_id}-{uuid4().hex}.deleting"
            )
            original_path.replace(staged_path)
            staged_paths.append((original_path, staged_path))

        db.delete(current_user)
        db.commit()
    except (OSError, SQLAlchemyError) as error:
        db.rollback()

        for original_path, staged_path in reversed(staged_paths):
            if staged_path.exists() and not original_path.exists():
                staged_path.replace(original_path)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete account",
        ) from error

    for _, staged_path in staged_paths:
        try:
            await asyncio.to_thread(
                shutil.rmtree,
                staged_path,
            )
        except OSError:
            logger.exception(
                "Could not remove deleted account photo directory %s",
                staged_path,
            )

    response.delete_cookie(
        key="access_token",
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )


@app.get(
    "/locations",
    response_model=list[LocationResponse],
)
def list_locations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Location]:
    statement = (
        select(Location)
        .where(Location.owner_id == current_user.id)
        .order_by(Location.created_at.desc())
    )

    return list(db.scalars(statement).all())
@app.post(
    "/locations",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_location(
    location_data: LocationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Location:
    location = Location(
        owner_id=current_user.id,
        **location_data.model_dump(),
    )

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LocationPhotoResponse:
    get_owned_location(location_id, current_user, db)

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

    contents, image_format = normalize_uploaded_image(contents)

    if len(contents) > MAX_PHOTO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Processed image must be 10 MB or smaller",
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LocationPhotoResponse]:
    get_owned_location(location_id, current_user, db)

    statement = (
        select(LocationPhoto)
        .where(LocationPhoto.location_id == location_id)
        .order_by(LocationPhoto.created_at.desc())
    )
    photos = db.scalars(statement).all()

    return [build_photo_response(photo) for photo in photos]


@app.get(
    "/locations/{location_id}/photos/{photo_id}/content",
    response_class=FileResponse,
)
def get_location_photo_content(
    location_id: int,
    photo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    get_owned_location(location_id, current_user, db)

    statement = select(LocationPhoto).where(
        LocationPhoto.id == photo_id,
        LocationPhoto.location_id == location_id,
    )
    photo = db.scalar(statement)

    if photo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )

    photo_path = get_photo_path(photo)

    if not photo_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo file not found",
        )

    return FileResponse(
        path=photo_path,
        media_type=photo.content_type,
    )


@app.delete(
    "/locations/{location_id}/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_location_photo(
    location_id: int,
    photo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    get_owned_location(location_id, current_user, db)

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Location:
    location = get_owned_location(location_id, current_user, db)

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    location = get_owned_location(location_id, current_user, db)

    db.delete(location)
    db.commit()

@app.get(
    "/locations/{location_id}/weather",
    response_model=WindConditions,
)
async def get_location_weather(
    location_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WindConditions:
    location = get_owned_location(location_id, current_user, db)

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SunConditions:
    location = get_owned_location(location_id, current_user, db)

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FlightConditions:
    location = get_owned_location(location_id, current_user, db)

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
    "/",
    StaticFiles(directory=frontend_directory, html=True),
    name="frontend",
)
