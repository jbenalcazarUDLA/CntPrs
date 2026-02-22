from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from .database import Base

class VideoSource(Base):
    __tablename__ = "video_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    type = Column(String)  # 'file' or 'rtsp'
    path_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
