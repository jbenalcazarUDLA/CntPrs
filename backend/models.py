from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base

class VideoSource(Base):
    __tablename__ = "video_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    type = Column(String)  # 'file' or 'rtsp'
    path_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tripwire = relationship("Tripwire", back_populates="source", uselist=False)

class Tripwire(Base):
    __tablename__ = "tripwires"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("video_sources.id"), unique=True)
    x1 = Column(Float)
    y1 = Column(Float)
    x2 = Column(Float)
    y2 = Column(Float)
    direction = Column(String) # 'IN' or 'OUT'
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    source = relationship("VideoSource", back_populates="tripwire")
