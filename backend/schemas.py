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
    is_scheduled: Optional[bool] = False

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

class CameraScheduleBase(BaseModel):
    monday: bool = True
    tuesday: bool = True
    wednesday: bool = True
    thursday: bool = True
    friday: bool = True
    saturday: bool = True
    sunday: bool = True
    start_time: str = "00:00"
    end_time: str = "23:59"
    is_active: bool = True

class CameraScheduleCreate(CameraScheduleBase):
    source_id: int

class CameraScheduleUpdate(CameraScheduleBase):
    pass

class CameraSchedule(CameraScheduleBase):
    id: int
    source_id: int

    class Config:
        orm_mode = True

class HistoricoConteoBase(BaseModel):
    source_id: int
    fecha_registro: str
    hora_apertura: str
    hora_cierre: str
    total_in: int
    total_out: int

class HistoricoConteoCreate(HistoricoConteoBase):
    pass

class HistoricoConteo(HistoricoConteoBase):
    id: int

    class Config:
        orm_mode = True
