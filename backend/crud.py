from sqlalchemy.orm import Session
from . import models, schemas

def get_video_source(db: Session, source_id: int):
    return db.query(models.VideoSource).filter(models.VideoSource.id == source_id).first()

def get_video_sources(db: Session, skip: int = 0, limit: int = 100):
    sources = db.query(models.VideoSource).offset(skip).limit(limit).all()
    # Populate the virtual is_scheduled field
    for s in sources:
        s.is_scheduled = s.schedule is not None and s.schedule.is_active
    return sources

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

def get_camera_schedule(db: Session, source_id: int):
    return db.query(models.CameraSchedule).filter(models.CameraSchedule.source_id == source_id).first()

def create_or_update_camera_schedule(db: Session, schedule: schemas.CameraScheduleCreate):
    db_schedule = db.query(models.CameraSchedule).filter(models.CameraSchedule.source_id == schedule.source_id).first()
    if db_schedule:
        db_schedule.monday = schedule.monday
        db_schedule.tuesday = schedule.tuesday
        db_schedule.wednesday = schedule.wednesday
        db_schedule.thursday = schedule.thursday
        db_schedule.friday = schedule.friday
        db_schedule.saturday = schedule.saturday
        db_schedule.sunday = schedule.sunday
        db_schedule.start_time = schedule.start_time
        db_schedule.end_time = schedule.end_time
        db_schedule.is_active = schedule.is_active
    else:
        db_schedule = models.CameraSchedule(**schedule.dict())
        db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)
    return db_schedule

def create_historico_conteo(db: Session, historico: schemas.HistoricoConteoCreate):
    db_historico = models.HistoricoConteo(**historico.dict())
    db.add(db_historico)
    db.commit()
    db.refresh(db_historico)
    return db_historico

def get_todays_historico_totals(db: Session, source_id: int):
    import datetime
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    records = db.query(models.HistoricoConteo).filter(
        models.HistoricoConteo.source_id == source_id,
        models.HistoricoConteo.fecha_registro == today_str
    ).all()
    
    total_in = sum(r.total_in for r in records)
    total_out = sum(r.total_out for r in records)
    return total_in, total_out

def update_historico_conteo_realtime(db: Session, source_id: int, fecha_registro: str, hora_apertura: str, hora_cierre: str, total_in: int, total_out: int):
    """
    Looks for the historic record for this specific streaming session (started at hora_apertura today)
    and updates it. If it doesn't exist, it creates it. This allows real-time updates without spamming new rows.
    """
    record = db.query(models.HistoricoConteo).filter(
        models.HistoricoConteo.source_id == source_id,
        models.HistoricoConteo.fecha_registro == fecha_registro,
        models.HistoricoConteo.hora_apertura == hora_apertura
    ).first()
    
    if record:
        record.hora_cierre = hora_cierre
        record.total_in = total_in
        record.total_out = total_out
    else:
        record = models.HistoricoConteo(
            source_id=source_id,
            fecha_registro=fecha_registro,
            hora_apertura=hora_apertura,
            hora_cierre=hora_cierre,
            total_in=total_in,
            total_out=total_out
        )
        db.add(record)
        
    db.commit()
    db.refresh(record)
    return record
