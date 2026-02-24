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

def get_tripwire(db: Session, source_id: int):
    print(f"DEBUG: Fetching tripwire for source_id={source_id}")
    return db.query(models.Tripwire).filter(models.Tripwire.source_id == source_id).first()

def create_or_update_tripwire(db: Session, tripwire: schemas.TripwireCreate):
    print(f"DEBUG: Saving tripwire for source_id={tripwire.source_id}: {tripwire.dict()}")
    db_tripwire = db.query(models.Tripwire).filter(models.Tripwire.source_id == tripwire.source_id).first()
    if db_tripwire:
        print(f"DEBUG: Updating existing tripwire ID={db_tripwire.id}")
        db_tripwire.x1 = tripwire.x1
        db_tripwire.y1 = tripwire.y1
        db_tripwire.x2 = tripwire.x2
        db_tripwire.y2 = tripwire.y2
        db_tripwire.direction = tripwire.direction
    else:
        print(f"DEBUG: Creating new tripwire for source_id={tripwire.source_id}")
        db_tripwire = models.Tripwire(**tripwire.dict())
        db.add(db_tripwire)
    db.commit()
    db.refresh(db_tripwire)
    return db_tripwire

def delete_tripwire(db: Session, source_id: int):
    db_tripwire = db.query(models.Tripwire).filter(models.Tripwire.source_id == source_id).first()
    if db_tripwire:
        db.delete(db_tripwire)
        db.commit()
        return True
    return False
