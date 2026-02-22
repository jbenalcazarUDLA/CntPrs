from sqlalchemy.orm import Session
from . import models, schemas

def get_video_source(db: Session, source_id: int):
    return db.query(models.VideoSource).filter(models.VideoSource.id == source_id).first()

def get_video_sources(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.VideoSource).offset(skip).limit(limit).all()

def create_video_source(db: Session, source: schemas.VideoSourceCreate):
    db_source = models.VideoSource(
        name=source.name,
        type=source.type,
        path_url=source.path_url
    )
    db.add(db_source)
    db.commit()
    db.refresh(db_source)
    return db_source

def delete_video_source(db: Session, source_id: int):
    db_source = db.query(models.VideoSource).filter(models.VideoSource.id == source_id).first()
    if db_source:
        db.delete(db_source)
        db.commit()
        return True
    return False
