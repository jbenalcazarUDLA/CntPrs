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
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0
    frame_time = 1.0 / fps

    consecutive_failures = 0
    frame_count = 0
    
    # --- Asynchronous Processing Cache Setup ---
    # The main thread reads and streams the video at its native FPS.
    # The background thread runs the heavy YOLO detection asynchronously.
    # The main thread simply draws whatever bounding boxes are currently in the cache.
    class AsyncYOLOProcessor:
        def __init__(self):
            self.running = True
            self.current_frame = None
            self.processed_frame_cache = None
            self.lock = threading.Lock()
            self.tripwire_data = None
            self.last_tripwire_check = 0
            
            self.thread = threading.Thread(target=self._process_loop, daemon=True)
            self.thread.start()

        def update_frame(self, frame):
            with self.lock:
                # We only want to process the *latest* frame, not build a queue
                self.current_frame = frame.copy()

        def _process_loop(self):
            while self.running:
                frame_to_process = None
                with self.lock:
                    if self.current_frame is not None:
                        frame_to_process = self.current_frame
                        self.current_frame = None # Consume it
                
                if frame_to_process is not None:
                    # Update tripwire
                    current_time = time.time()
                    if current_time - self.last_tripwire_check > 5:
                        db = SessionLocal()
                        try:
                            self.tripwire_data = crud.get_tripwire(db, source_id=source_id)
                        finally:
                            db.close()
                        self.last_tripwire_check = current_time

                    # Run heavy inference
                    processed = detector.process_frame(frame_to_process, source_id, self.tripwire_data)
                    with self.lock:
                        self.processed_frame_cache = processed
                else:
                    time.sleep(0.01) # Wait for a new frame

        def stop(self):
            self.running = False
            self.thread.join(timeout=2)

    yolo_processor = AsyncYOLOProcessor()
    
    try:
        while cap.isOpened():
            start_time = time.time()
            
            # --- MEASURE READ ---
            t_r1 = time.time()
            success, frame = cap.read()
            t_r2 = time.time()
            
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
                print(f"[STREAM-FILE-{source_id}] First frame decoded successfully! Starting async YOLO...")
            elif frame_count % 30 == 0:
                pass # We will print debug logs below instead
            
            # 1. Dispatch frame to background thread for YOLO (non-blocking)
            yolo_processor.update_frame(frame)
            
            # 2. Retrieve the *latest available* processed frame from cache
            # If YOLO is slow, this will just return a slightly older frame with older bounding boxes
            with yolo_processor.lock:
                frame_to_stream = yolo_processor.processed_frame_cache if yolo_processor.processed_frame_cache is not None else frame

            # 3. Stream to browser immediately
            # --- MEASURE ENCODE ---
            t_e1 = time.time()
            ret, buffer = cv2.imencode('.jpg', frame_to_stream, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            t_e2 = time.time()
            
            t_y1 = time.time()
            t_y2 = time.time()
            if ret:
                frame_bytes = buffer.tobytes()
                # --- MEASURE NETWORK YIELD ---
                t_y1 = time.time()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                t_y2 = time.time()
            
            # 4. Synchronize native video speed
            elapsed_time = time.time() - start_time
            sleep_time = frame_time - elapsed_time
            if sleep_time > 0:
                time.sleep(sleep_time)
                
            if frame_count % 30 == 0:
                print(f"[STREAM-FILE-{source_id}] FPS={fps:.1f} | Frame={frame_count} | read={(t_r2-t_r1)*1000:.1f}ms | encode={(t_e2-t_e1)*1000:.1f}ms | yield={(t_y2-t_y1)*1000:.1f}ms | total_loop={elapsed_time*1000:.1f}ms")
                
    finally:
        print(f"[STREAM-FILE-{source_id}] Closing video capture descriptor...")
        yolo_processor.stop()
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

