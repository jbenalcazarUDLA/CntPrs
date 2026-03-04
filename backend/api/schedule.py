from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import crud, models, schemas
from ..database import get_db

router = APIRouter()

@router.get("/{source_id}", response_model=schemas.CameraSchedule)
def get_camera_schedule(source_id: int, db: Session = Depends(get_db)):
    schedule = crud.get_camera_schedule(db, source_id=source_id)
    if schedule is None:
        # Return a default inactive schedule if none is found so the frontend doesn't crash
        return schemas.CameraSchedule(
            id=0,
            source_id=source_id,
            monday=True, tuesday=True, wednesday=True, thursday=True, friday=True, saturday=True, sunday=True,
            start_time="00:00", end_time="23:59", is_active=False
        )
    return schedule

@router.put("/{source_id}", response_model=schemas.CameraSchedule)
def update_camera_schedule(source_id: int, schedule: schemas.CameraScheduleCreate, db: Session = Depends(get_db)):
    if source_id != schedule.source_id:
        raise HTTPException(status_code=400, detail="Path ID does not match Body Source ID")
    return crud.create_or_update_camera_schedule(db=db, schedule=schedule)

@router.post("/historico", response_model=schemas.HistoricoConteo)
def add_historico_conteo(historico: schemas.HistoricoConteoCreate, db: Session = Depends(get_db)):
    return crud.create_historico_conteo(db=db, historico=historico)
