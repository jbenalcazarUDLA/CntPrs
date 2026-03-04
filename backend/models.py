from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean
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
    schedule = relationship("CameraSchedule", back_populates="source", uselist=False)

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

class CameraSchedule(Base):
    __tablename__ = "camera_schedules"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("video_sources.id"), unique=True)
    monday = Column(Boolean, default=True)
    tuesday = Column(Boolean, default=True)
    wednesday = Column(Boolean, default=True)
    thursday = Column(Boolean, default=True)
    friday = Column(Boolean, default=True)
    saturday = Column(Boolean, default=True)
    sunday = Column(Boolean, default=True)
    start_time = Column(String, default="00:00")
    end_time = Column(String, default="23:59")
    is_active = Column(Boolean, default=True)

    source = relationship("VideoSource", back_populates="schedule")

class HistoricoConteo(Base):
    __tablename__ = "historico_conteo"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("video_sources.id"))
    fecha_registro = Column(String)
    hora_apertura = Column(String)
    hora_cierre = Column(String)
    total_in = Column(Integer, default=0)
    total_out = Column(Integer, default=0)

    source = relationship("VideoSource")
