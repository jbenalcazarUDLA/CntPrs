from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
import cv2
import os
from ..database import get_db
from .. import crud, models

router = APIRouter()

@router.get("/file/{source_id}")
def stream_file(source_id: int, db: Session = Depends(get_db)):
    db_source = crud.get_video_source(db, source_id=source_id)
    if not db_source or db_source.type != "file":
        raise HTTPException(status_code=404, detail="Video file not found")
    
    if not os.path.exists(db_source.path_url):
        raise HTTPException(status_code=404, detail="File does not exist on disk")
    
    return FileResponse(db_source.path_url, media_type="video/mp4")

import threading
import time

class RTSPStreamReader:
    def __init__(self, rtsp_url):
        self.rtsp_url = rtsp_url
        self.cap = None
        self.frame = None
        self.running = False
        self.lock = threading.Lock()
        self.thread = None
        
        # Optimize OpenCV connection and disable heavy FFMPEG logging for HEVC errors
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;500000|probesize;500000|timeout;3000000|fflags;discardcorrupt"
        os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "quiet"
        os.environ["OPENCV_LOG_LEVEL"] = "SILENT"

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        return self

    def _update(self):
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.rtsp_url)
                if not self.cap.isOpened():
                    time.sleep(2) # Wait before retrying connection
                    continue
                    
            success, frame = self.cap.read()
            if success:
                with self.lock:
                    self.frame = frame
            else:
                self.cap.release()
                self.cap = None
                time.sleep(1) # Wait before retrying if stream dropped

    def read_jpeg(self):
        with self.lock:
            if self.frame is not None:
                # Resize for better performance if needed
                # frame = cv2.resize(self.frame, (640, 360))
                ret, buffer = cv2.imencode('.jpg', self.frame)
                if ret:
                    return buffer.tobytes()
        return None

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        if self.cap:
            self.cap.release()

def gen_frames(rtsp_url: str):
    reader = RTSPStreamReader(rtsp_url).start()
    try:
        while True:
            frame_bytes = reader.read_jpeg()
            if frame_bytes is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.03) # Cap at ~30 FPS to save CPU
    finally:
        reader.stop()

@router.get("/rtsp/{source_id}")
def stream_rtsp(source_id: int, db: Session = Depends(get_db)):
    db_source = crud.get_video_source(db, source_id=source_id)
    if not db_source or db_source.type != "rtsp":
        raise HTTPException(status_code=404, detail="RTSP source not found")
    
    return StreamingResponse(gen_frames(db_source.path_url),
                             media_type="multipart/x-mixed-replace; boundary=frame")
