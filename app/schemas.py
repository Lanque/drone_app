from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LocationResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    description: str | None
    no_fly_zone_status: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)