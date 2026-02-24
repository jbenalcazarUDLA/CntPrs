from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
import cv2
import os
from .. import crud, models, schemas
from ..database import get_db

router = APIRouter()

@router.get("/source/{source_id}", response_model=schemas.Tripwire)
def get_tripwire(source_id: int, db: Session = Depends(get_db)):
    db_tripwire = crud.get_tripwire(db, source_id=source_id)
    if not db_tripwire:
        raise HTTPException(status_code=404, detail="Tripwire not found for this source")
    return db_tripwire

@router.post("/", response_model=schemas.Tripwire)
def save_tripwire(tripwire: schemas.TripwireCreate, db: Session = Depends(get_db)):
    return crud.create_or_update_tripwire(db, tripwire=tripwire)

@router.delete("/source/{source_id}")
def delete_tripwire(source_id: int, db: Session = Depends(get_db)):
    success = crud.delete_tripwire(db, source_id=source_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tripwire not found")
    return {"message": "Tripwire deleted successfully"}

@router.get("/frame/{source_id}")
def get_source_frame(source_id: int, db: Session = Depends(get_db)):
    db_source = crud.get_video_source(db, source_id=source_id)
    if not db_source:
        print(f"ERROR: Source {source_id} not found in DB")
        raise HTTPException(status_code=404, detail="Source not found")
    
    path = db_source.path_url
    print(f"DEBUG: Attempting to capture frame from: {path} (type: {db_source.type})")
    
    # Check if path is local file and exists
    if db_source.type == "file":
        if not os.path.exists(path):
            abs_path = os.path.abspath(path)
            print(f"ERROR: Local file not found at {path} (Abs: {abs_path})")
            # Try to see if it's relative to backend/
            if os.path.exists(os.path.join("backend", path)):
                path = os.path.join("backend", path)
                print(f"DEBUG: Found file at {path}")
            else:
                raise HTTPException(status_code=404, detail=f"File not found at {path}")

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"ERROR: Could not open video source: {path}")
        raise HTTPException(status_code=400, detail=f"Could not open video source: {path}")
    
    # Set a timeout for RTSP if possible (backend dependent)
    # cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
    
    print("DEBUG: Skipping 5 frames...")
    # Try to skip some frames to avoid black frames at the beginning of some streams
    for i in range(5):
        cap.grab()
    
    print("DEBUG: Reading frame...")
    success, frame = cap.read()
    cap.release()
    
    if not success:
        print("ERROR: Could not read frame from source")
        raise HTTPException(status_code=400, detail="Could not read frame from source")
    
    print("DEBUG: Encoding frame as JPEG...")
    _, buffer = cv2.imencode('.jpg', frame)
    print("DEBUG: Frame capture successful")
    return Response(content=buffer.tobytes(), media_type="image/jpeg")

@router.get("/debug/all", tags=["debug"])
def get_all_tripwires(db: Session = Depends(get_db)):
    """Debug endpoint to see all saved tripwires."""
    return db.query(models.Tripwire).all()
