from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class VideoSourceBase(BaseModel):
    name: str
    type: str # 'file' or 'rtsp'
    path_url: str

class VideoSourceCreate(VideoSourceBase):
    pass

class VideoSource(VideoSourceBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

class TripwireBase(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    direction: str

class TripwireCreate(TripwireBase):
    source_id: int

class TripwireUpdate(TripwireBase):
    pass

class Tripwire(TripwireBase):
    id: int
    source_id: int
    updated_at: datetime

    class Config:
        orm_mode = True
