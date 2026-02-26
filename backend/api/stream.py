from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import cv2
import os
import time
from ..database import get_db, SessionLocal
from .. import crud, models
from ..services.async_yolo import MultiprocessYOLO

router = APIRouter()

# Global dictionary to hold multiprocessing instances (one per camera)
yolo_processors = {}

def get_tripwire_data(source_id):
    db = SessionLocal()
    try:
        return crud.get_tripwire(db, source_id=source_id)
    finally:
        db.close()

def generate_frames(source_id: int, source_path: str, is_rtsp: bool):
    """
    Pipeline de Streaming Súper Eficiente (Multi-Procesos).
    La lectura de la cámara y la web corren en el thread actual libremente.
    El cálculo pesado de YOLO e IA corre en otro proceso 100% independiente.
    """
    if is_rtsp:
        # Optimizar conexión RTSP sin los parámetros que causaban OOM y suprimir logs HEVC
        os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
        os.environ["AV_LOG_LEVEL"] = "-8"
        os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|fflags;discardcorrupt|flags;low_delay"
        
    cap = cv2.VideoCapture(source_path)
    
    if is_rtsp and "OPENCV_FFMPEG_CAPTURE_OPTIONS" in os.environ:
        del os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]
        os.environ.pop("OPENCV_FFMPEG_LOGLEVEL", None)
        os.environ.pop("AV_LOG_LEVEL", None)
        
    if not cap.isOpened():
        print(f"[STREAM-{source_id}] ERROR: No se pudo conectar a la fuente de video {source_path}")
        return

    # Forzar bajo buffering para que la cámara siempre entregue el present frame (evita delay)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
    
    video_fps = 30.0
    if not is_rtsp:
        fps_prop = cap.get(cv2.CAP_PROP_FPS)
        if fps_prop > 0:
            video_fps = fps_prop
            
    tripwire_data = get_tripwire_data(source_id)
    last_tripwire_update = time.time()

    # Iniciar motor IA en segundo plano aislado para esta cámara específica
    if source_id not in yolo_processors:
        yolo_processors[source_id] = MultiprocessYOLO(source_id)
    
    processor = yolo_processors[source_id]
    
    # Virtual clock para VOD usando conteo de frames en lugar de MSEC (que falla en algunos codecs MP4)
    start_time_real = time.time()
    
    try:
        while True:
            # 1. Ingesta
            # Si es VOD, adelantamos el puntero (grab) si el video físico se quedó atrás del tiempo real
            if not is_rtsp:
                curr_real = (time.time() - start_time_real)
                curr_frame = cap.get(cv2.CAP_PROP_POS_FRAMES)
                curr_video_time = curr_frame / video_fps
                
                # Si el reloj real va más rápido que los frames mostrados
                diff = curr_real - curr_video_time
                if diff > (1.0 / video_fps):
                    # Calcular cuántos frames estamos atrasados
                    frames_to_skip = int(diff * video_fps)
                    for _ in range(frames_to_skip):
                        if not cap.grab():
                            break
                    
            success, frame = cap.read()
            if not success:
                if not is_rtsp:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    start_time_real = time.time()
                    continue
                else:
                    time.sleep(1)
                    continue

            # Recargar metadata cada 5s
            if time.time() - last_tripwire_update > 5:
                tripwire_data = get_tripwire_data(source_id)
                last_tripwire_update = time.time()

            # Preparar tripwire (evitar errores de Pickling de SQLAlchemy en la Queue)
            tw_dict = None
            if tripwire_data:
                tw_dict = {
                    'x1': tripwire_data.x1, 'y1': tripwire_data.y1,
                    'x2': tripwire_data.x2, 'y2': tripwire_data.y2,
                    'direction': tripwire_data.direction
                }

            # 2. IA Delegada (No Bloqueante)
            processor.update_frame(frame, tw_dict)
            processed_frame = processor.get_latest_processed_frame(frame)

            # 3. Salida a Cliente Web
            ret, buffer = cv2.imencode('.jpg', processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
            # Restricción obligada para VOD: Si procesamos muy RÁPIDO, dormimos para no ir en cámara rápida.
            if not is_rtsp:
                curr_real = (time.time() - start_time_real)
                curr_frame = cap.get(cv2.CAP_PROP_POS_FRAMES)
                curr_video_time = curr_frame / video_fps
                sleep_time = curr_video_time - curr_real
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
    finally:
        print(f"[STREAM-{source_id}] Conexión de cliente cerrada. Liberando stream...")
        cap.release()
        # Si somos el último usuario, podríamos detener el processor, pero de momento
        # los mantenemos vivos para conexiones rápidas sucesivas.


@router.get("/rtsp/{source_id}")
def stream_rtsp(source_id: int, db: Session = Depends(get_db)):
    db_source = crud.get_video_source(db, source_id=source_id)
    if not db_source or db_source.type != "rtsp":
        raise HTTPException(status_code=404, detail="RTSP source not found")
    
    return StreamingResponse(generate_frames(source_id, db_source.path_url, is_rtsp=True),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/file/{source_id}")
def stream_file(source_id: int, db: Session = Depends(get_db)):
    db_source = crud.get_video_source(db, source_id=source_id)
    if not db_source or db_source.type != "file":
        raise HTTPException(status_code=404, detail="Video file not found")
    
    if not os.path.exists(db_source.path_url):
        raise HTTPException(status_code=404, detail="File does not exist on disk")
    
    return StreamingResponse(generate_frames(source_id, db_source.path_url, is_rtsp=False),
                             media_type="multipart/x-mixed-replace; boundary=frame")
