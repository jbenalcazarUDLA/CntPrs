from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import cv2
import os
import threading
import time
from ..database import get_db
from .. import crud, models
from ..services.detection import detector # Import the new detector

router = APIRouter()

class RTSPStreamReader:
    def __init__(self, source_id, rtsp_url, db_session_maker):
        self.source_id = source_id
        self.rtsp_url = rtsp_url
        self.db_session_maker = db_session_maker
        self.cap = None
        self.frame = None
        self.running = False
        self.lock = threading.Lock()
        self.thread = None
        self.tripwire_data = None
        self.last_tripwire_check = 0
        
        # Optimize OpenCV connection and disable FFMPEG logging for HEVC/RTP errors globally
        os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
        os.environ["AV_LOG_LEVEL"] = "-8"
        os.environ["OPENCV_LOG_LEVEL"] = "SILENT"


    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        return self

    def _update_tripwire(self):
        # Refresh tripwire data every 5 seconds to avoid constant DB hitting
        current_time = time.time()
        if current_time - self.last_tripwire_check > 5:
            try:
                # We need a fresh session here because this runs in a separate thread
                db = self.db_session_maker()
                self.tripwire_data = crud.get_tripwire(db, source_id=self.source_id)
                db.close()
            except Exception as e:
                print(f"Error fetching tripwire: {e}")
            self.last_tripwire_check = current_time

    def _update(self):
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                # Enforce RTSP-specific options safely, minimizing probe time
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|strict;experimental|analyzeduration;0|probesize;32"
                self.cap = cv2.VideoCapture(self.rtsp_url)
                if "OPENCV_FFMPEG_CAPTURE_OPTIONS" in os.environ:
                    del os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]
                    
                if not self.cap.isOpened():
                    time.sleep(2) # Wait before retrying connection
                    continue
                    
            success, frame = self.cap.read()
            if success:
                self._update_tripwire()
                # Process frame with YOLO before storing it
                processed_frame = detector.process_frame(frame, self.source_id, self.tripwire_data)
                
                with self.lock:
                    self.frame = processed_frame
            else:
                self.cap.release()
                self.cap = None
                time.sleep(1) # Wait before retrying if stream dropped

    def read_jpeg(self):
        with self.lock:
            if self.frame is not None:
                ret, buffer = cv2.imencode('.jpg', self.frame)
                if ret:
                    return buffer.tobytes()
        return None

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()

def rtsp_gen_frames(source_id: int, rtsp_url: str):
    from ..database import SessionLocal # Local import to avoid circular dep
    reader = RTSPStreamReader(source_id, rtsp_url, SessionLocal).start()
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
    
    return StreamingResponse(rtsp_gen_frames(source_id, db_source.path_url),
                             media_type="multipart/x-mixed-replace; boundary=frame")


# --- FILE STREAMING WITH YOLO ---

def file_gen_frames(source_id: int, file_path: str):
    from ..database import SessionLocal
    print(f"[STREAM-FILE-{source_id}] Starting file generator thread for path: {file_path}")
    cap = cv2.VideoCapture(file_path)
    
    if not cap.isOpened():
        print(f"[STREAM-FILE-{source_id}] ERROR: Cannot open file path: {file_path}")
        return
        
    print(f"[STREAM-FILE-{source_id}] System successfully opened cv2.VideoCapture descriptor.")
        
    consecutive_failures = 0
    last_tripwire_check = 0
    tripwire_data = None
    frame_count = 0
    
    try:
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
               current_frame = cap.get(cv2.CAP_PROP_POS_FRAMES)
               total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
               
               print(f"[STREAM-FILE-{source_id}] DEBUG: Read failed. pos: {current_frame}, total: {total_frames}")
               
               # If we are at the end (or very close), loop the video
               if total_frames > 0 and current_frame >= total_frames - 1:
                   print(f"[STREAM-FILE-{source_id}] Reached end of video file. Looping back to frame 0...")
                   cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                   consecutive_failures = 0
                   continue
                   
               consecutive_failures += 1
               if consecutive_failures > 30:
                   print(f"[STREAM-FILE-{source_id}] ERROR: Too many consecutive frame read failures in file streaming. Aborting.")
                   break
                   
               # Just a bad frame, skip it
               continue
               
            consecutive_failures = 0
            frame_count += 1
            
            if frame_count == 1:
                print(f"[STREAM-FILE-{source_id}] First frame decoded successfully! Sending to YOLO...")
            elif frame_count % 300 == 0:
                print(f"[STREAM-FILE-{source_id}] Processed {frame_count} frames so far...")
            
            current_time = time.time()
            if current_time - last_tripwire_check > 5:
                db = SessionLocal()
                try:
                    tripwire_data = crud.get_tripwire(db, source_id=source_id)
                finally:
                    db.close()
                last_tripwire_check = current_time
            
            processed_frame = detector.process_frame(frame, source_id, tripwire_data)
            ret, buffer = cv2.imencode('.jpg', processed_frame)
            
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            if frame_count == 1:
                print(f"[STREAM-FILE-{source_id}] First frame successfully encoded to MJPEG and yielded to network.")
                
            time.sleep(0.03) # Try to maintain ~30fps playback speed
    finally:
        print(f"[STREAM-FILE-{source_id}] Closing video capture descriptor...")
        cap.release()

@router.get("/file/{source_id}")
def stream_file(source_id: int, db: Session = Depends(get_db)):
    print(f"[STREAM-ENDPOINT] Received HTTP GET request for /api/stream/file/{source_id}...")
    db_source = crud.get_video_source(db, source_id=source_id)
    if not db_source or db_source.type != "file":
        print(f"[STREAM-ENDPOINT] ERROR: Source {source_id} is not a valid video file in DB.")
        raise HTTPException(status_code=404, detail="Video file not found")
    
    if not os.path.exists(db_source.path_url):
        print(f"[STREAM-ENDPOINT] ERROR: The physical file at {db_source.path_url} does not exist.")
        raise HTTPException(status_code=404, detail="File does not exist on disk")
    
    print(f"[STREAM-ENDPOINT] Returning MJPEG StreamingResponse for {db_source.path_url}...")
    # We now stream the file exactly like we do RTSP so YOLO processing can be viewed real-time
    return StreamingResponse(file_gen_frames(source_id, db_source.path_url),
                             media_type="multipart/x-mixed-replace; boundary=frame")

