from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LocationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    description: str | None = Field(default=None, max_length=2_000)
    no_fly_zone_status: bool = False


class LocationResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    description: str | None
    no_fly_zone_status: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)