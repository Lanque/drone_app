from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LocationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    description: str | None = Field(default=None, max_length=2_000)
    no_fly_zone_status: bool = False

class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    description: str | None = Field(default=None, max_length=2_000)
    no_fly_zone_status: bool | None = None

class LocationResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    description: str | None
    no_fly_zone_status: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LocationPhotoResponse(BaseModel):
    id: int
    location_id: int
    original_name: str
    content_type: str
    size_bytes: int
    caption: str | None
    url: str
    created_at: datetime


class WindConditions(BaseModel):
    speed_mps: float
    direction_degrees: float | None
    gust_mps: float | None

class TimeWindow(BaseModel):
    begin: datetime | None
    end: datetime | None


class SunConditions(BaseModel):
    sunrise: datetime | None
    sunset: datetime | None
    timezone: str
    golden_hour_morning: TimeWindow
    golden_hour_evening: TimeWindow
    blue_hour_morning: TimeWindow
    blue_hour_evening: TimeWindow

class FlightConditions(BaseModel):
    location: LocationResponse
    wind: WindConditions | None
    weather_available: bool
    sun: SunConditions

class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    display_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)