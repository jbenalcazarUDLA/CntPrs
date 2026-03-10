from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import cv2
import os
import time
import logging
import socket
from urllib.parse import urlparse
import threading
import numpy as np
import uuid
import asyncio
from pydantic import BaseModel

from ..database import get_db, SessionLocal
from .. import crud, models
from ..services.async_yolo import MultiprocessYOLO

try:
    from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, RTCConfiguration, RTCIceServer
    from av import VideoFrame
except ImportError:
    pass

router = APIRouter()

metrics_logger = logging.getLogger("stream_metrics")
metrics_logger.setLevel(logging.INFO)
if not metrics_logger.handlers:
    rfh = logging.FileHandler("stream_metrics.log")
    rfh.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    metrics_logger.addHandler(rfh)

class FrontendMetric(BaseModel):
    source_id: int
    camera_name: str
    load_time_sec: float

@router.post("/metrics")
def save_frontend_metric(metric: FrontendMetric):
    metrics_logger.info(f"[FRONTEND Metrics] Camera '{metric.camera_name}' (ID: {metric.source_id}) loaded in {metric.load_time_sec:.2f} seconds.")
    return {"status": "logged"}

yolo_processors = {}
active_viewers = {}
camera_threads = {}
processor_lock = threading.Lock()
pcs = set()

def cleanup_all_processes():
    print("[STREAM] Limpiando todos los procesos YOLO...")
    with processor_lock:
        for p in list(yolo_processors.values()):
            try:
                p.stop()
            except Exception:
                pass
        yolo_processors.clear()
        active_viewers.clear()
        
        # We can't easily kill threads, but we set active_viewers to 0 so they exit naturally
        for pc in list(pcs):
            asyncio.run_coroutine_threadsafe(pc.close(), asyncio.get_event_loop())
        pcs.clear()

def get_tripwire_data(source_id):
    db = SessionLocal()
    try:
        return crud.get_tripwire(db, source_id=source_id)
    finally:
        db.close()

def camera_worker(source_id: int, source_path: str, is_rtsp: bool):
    """Background thread that consumes the Main Stream and feeds YOLO."""
    try:
        if is_rtsp:
            os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
            os.environ["AV_LOG_LEVEL"] = "-8"
            # Optimiza tiempo de conexion reduciendo probing y timeouts
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|fflags;discardcorrupt|flags;low_delay|analyzeduration;500000|probesize;50000|stimeout;3000000|rw_timeout;3000000"
            
        raw_cap = cv2.VideoCapture(source_path, cv2.CAP_FFMPEG) if is_rtsp else cv2.VideoCapture(source_path)
        from ..services.video_reader import VideoReaderWrapper
        cap = VideoReaderWrapper(raw_cap, is_rtsp=is_rtsp)
        
        if is_rtsp and "OPENCV_FFMPEG_CAPTURE_OPTIONS" in os.environ:
            del os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]
            
        if not cap.isOpened():
            print(f"[STREAM-{source_id}] ERROR: No se pudo conectar a la fuente principal {source_path}")
            return
            
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        
        tripwire_data = get_tripwire_data(source_id)
        last_tripwire_update = time.time()
        
        video_fps = 30.0
        if not is_rtsp:
            fps_prop = cap.get(cv2.CAP_PROP_FPS)
            if fps_prop > 0: video_fps = fps_prop

        start_time_real = time.time()
        frame_idx = 0
            
        with processor_lock:
            if source_id not in yolo_processors:
                initial_in, initial_out = 0, 0
                if is_rtsp:
                    try:
                        db = SessionLocal()
                        db_in, db_out = crud.get_todays_historico_totals(db, source_id)
                        initial_in += db_in
                        initial_out += db_out
                        db.close()
                    except Exception: pass
                yolo_processors[source_id] = MultiprocessYOLO(source_id, initial_in, initial_out)
            processor = yolo_processors[source_id]

        while True:
            # Check if anyone is still watching
            with processor_lock:
                if active_viewers.get(source_id, 0) <= 0:
                    break
                    
            success, frame = cap.read()
            if not success:
                if not is_rtsp:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    start_time_real = time.time()
                    frame_idx = 0
                    continue
                else:
                    time.sleep(1)
                    continue
                    
            if not is_rtsp:
                frame_idx += 1
                
            if time.time() - last_tripwire_update > 5:
                tripwire_data = get_tripwire_data(source_id)
                last_tripwire_update = time.time()
                
            tw_dict = None
            if tripwire_data:
                tw_dict = {'x1': tripwire_data.x1, 'y1': tripwire_data.y1, 'x2': tripwire_data.x2, 'y2': tripwire_data.y2, 'direction': tripwire_data.direction}
                
            processor.update_frame(frame, tw_dict)
            
            if not is_rtsp:
                curr_real = (time.time() - start_time_real)
                curr_video_time = frame_idx / video_fps
                sleep_time = curr_video_time - curr_real
                if sleep_time > 0:
                    time.sleep(sleep_time)

    finally:
        if 'cap' in locals(): cap.release()
        import gc
        gc.collect()
        print(f"[STREAM-{source_id}] Camera worker finalizado.")
        
        with processor_lock:
            if source_id in camera_threads:
                del camera_threads[source_id]
            if source_id in yolo_processors and active_viewers.get(source_id, 0) <= 0:
                yolo_processors[source_id].stop()
                del yolo_processors[source_id]


def ensure_camera_running(source_id: int, source_path: str, is_rtsp: bool):
    with processor_lock:
        if source_id not in active_viewers:
            active_viewers[source_id] = 0
        active_viewers[source_id] += 1
        
        if source_id not in camera_threads:
            t = threading.Thread(target=camera_worker, args=(source_id, source_path, is_rtsp), daemon=True)
            camera_threads[source_id] = t
            t.start()
            
def release_camera(source_id: int):
    with processor_lock:
        if source_id in active_viewers:
            active_viewers[source_id] -= 1


def generate_mjpeg_frames(source_id: int, source_path: str, is_rtsp: bool):
    """Fallback generator para archivos VOD (archivos locales) en formato MJPEG."""
    ensure_camera_running(source_id, source_path, is_rtsp)
    
    skip_encode_counter = 0
    blank_frame = np.zeros((320, 320, 3), dtype=np.uint8)
    
    try:
        while True:
            processor = yolo_processors.get(source_id)
            if processor:
                frame = processor.get_latest_processed_frame(blank_frame)
            else:
                frame = blank_frame
                
            skip_encode_counter += 1
            if skip_encode_counter % 2 == 0:
                ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            
            time.sleep(0.01)
    except Exception as e:
        print(f"[MJPEG] Error in generator for {source_id}: {e}")
    finally:
        release_camera(source_id)

@router.get("/rtsp/{source_id}")
def stream_rtsp(source_id: int, db: Session = Depends(get_db)):
    db_source = crud.get_video_source(db, source_id=source_id)
    if not db_source or db_source.type != "rtsp":
        raise HTTPException(status_code=404, detail="RTSP source not found")
        
    return StreamingResponse(generate_mjpeg_frames(source_id, db_source.path_url, is_rtsp=True),
                                media_type="multipart/x-mixed-replace; boundary=frame")

@router.get("/file/{source_id}")
def stream_file(source_id: int, db: Session = Depends(get_db)):
    db_source = crud.get_video_source(db, source_id=source_id)
    if not db_source or db_source.type != "file":
        raise HTTPException(status_code=404, detail="Video file not found")
    
    if not os.path.exists(db_source.path_url):
        raise HTTPException(status_code=404, detail="File does not exist on disk")
    
    return StreamingResponse(generate_mjpeg_frames(source_id, db_source.path_url, is_rtsp=False),
                             media_type="multipart/x-mixed-replace; boundary=frame")
