from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
import shutil
import os
from .. import crud, models, schemas
from ..database import get_db

router = APIRouter()

UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

@router.post("/upload", response_model=schemas.VideoSource)
def upload_video(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    source_in = schemas.VideoSourceCreate(
        name=name,
        type="file",
        path_url=file_path
    )
    return crud.create_video_source(db=db, source=source_in)

@router.post("/rtsp", response_model=schemas.VideoSource)
def register_rtsp(
    source: schemas.VideoSourceCreate,
    db: Session = Depends(get_db)
):
    if source.type != "rtsp":
        raise HTTPException(status_code=400, detail="Invalid type for RTSP registration")
        
    import cv2
    import os
    # Set timeout options so it doesn't hang indefinitely 
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|strict;experimental|analyzeduration;0|probesize;32"
    
    cap = cv2.VideoCapture(source.path_url)
    
    if "OPENCV_FFMPEG_CAPTURE_OPTIONS" in os.environ:
        del os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]
        
    if not cap.isOpened():
        raise HTTPException(status_code=400, detail="Could not connect to the RTSP stream.")
        
    success, frame = cap.read()
    cap.release()
    
    if not success:
        raise HTTPException(status_code=400, detail="Connected to RTSP stream but failed to read a frame.")
        
    return crud.create_video_source(db=db, source=source)

@router.get("/", response_model=list[schemas.VideoSource])
def list_sources(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_video_sources(db, skip=skip, limit=limit)

@router.delete("/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    # Note: In a real app, you might want to delete the file from disk if type is 'file'
    success = crud.delete_video_source(db, source_id=source_id)
    if not success:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"message": "Source deleted successfully"}
