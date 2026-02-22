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
