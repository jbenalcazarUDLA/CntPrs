from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import cv2
import os
import time
import logging
import socket
from urllib.parse import urlparse
from ..database import get_db, SessionLocal
from .. import crud, models
from ..services.async_yolo import MultiprocessYOLO

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
        # Rollback: Las opciones extremadamente agresivas de 'analyzeduration' causan que algunas cámaras se ahoguen
        # Revertimos a la cadena TCP original súper estable, agregando solo TIMEOUTS para evitar colgarse
        os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
        os.environ["AV_LOG_LEVEL"] = "-8"
        os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
        # stimeout = socket timeout en microsegundos. 10,000,000 us = 10 segundos (rompe los 180s de espera)
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|fflags;discardcorrupt|flags;low_delay|stimeout;10000000|rw_timeout;10000000"
        
    msg_init = f"[BACKEND STREAM-{source_id}] Iniciando solicitud de conexión RTSP/File a {source_path}"
    print(msg_init)
    metrics_logger.info(msg_init)
    connect_start_time = time.time()
    
    if is_rtsp:
        # Pre-chequeo de red directo con Sockets para evadir el timeout de 180s de TCP del sistema operativo
        try:
            parsed = urlparse(source_path)
            host = parsed.hostname
            # Puerto 554 es el default de RTSP
            port = parsed.port or 554
            if host:
                msg_ping = f"[BACKEND STREAM-{source_id}] Pinging {host}:{port}..."
                print(msg_ping)
                metrics_logger.info(msg_ping)
                sock = socket.create_connection((host, port), timeout=3.0)
                sock.close()
                msg_ping_ok = f"[BACKEND STREAM-{source_id}] Ping OK, delegando a OpenCV..."
                print(msg_ping_ok)
                metrics_logger.info(msg_ping_ok)
        except Exception as e:
            msg_fail = f"[BACKEND STREAM-{source_id}] FALLO PRE-RED O TIMEOUT (3s): Host {host}:{port} inalcanzable. Evitando hang de 180s. ({e})"
            print(msg_fail)
            metrics_logger.error(msg_fail)
            return

    # Usar explícitamente el backend de FFMPEG para forzar que respete las variables de entorno
    cap = cv2.VideoCapture(source_path, cv2.CAP_FFMPEG) if is_rtsp else cv2.VideoCapture(source_path)
    
    connect_end_time = time.time()
    msg_vc = f"[BACKEND STREAM-{source_id}] VideoCapture inicializado en {connect_end_time - connect_start_time:.2f} segundos."
    print(msg_vc)
    metrics_logger.info(msg_vc)
    
    if is_rtsp and "OPENCV_FFMPEG_CAPTURE_OPTIONS" in os.environ:
        del os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]
        os.environ.pop("OPENCV_FFMPEG_LOGLEVEL", None)
        os.environ.pop("AV_LOG_LEVEL", None)
        
    if not cap.isOpened():
        print(f"[STREAM-{source_id}] ERROR: No se pudo conectar a la fuente de video {source_path}")
        return

    msg_wait = f"[BACKEND STREAM-{source_id}] Esperando el primer frame real..."
    print(msg_wait)
    metrics_logger.info(msg_wait)
    first_frame_start = time.time()

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
    
    # Virtual clock para VOD usando conteo de frames en lugar de MSEC o POS_FRAMES (que falla en algunos codecs MP4)
    start_time_real = time.time()
    frame_idx = 0
    
    # Contador para limitar los fotogramas codificados hacia la web
    skip_encode_counter = 0
    
    first_frame_rendered = False
    total_load_time = 0.0

    try:
        while True:
            # 1. Ingesta secuencial
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
            
            if not first_frame_rendered:
                total_load_time = time.time() - connect_start_time
                msg_ff = f"[BACKEND STREAM-{source_id}] PRIMER FRAME PROCESADO. Tiempo total TTFF Backend: {total_load_time:.2f} segundos."
                print(msg_ff)
                metrics_logger.info(msg_ff)
                first_frame_rendered = True
            
            if not is_rtsp:
                frame_idx += 1

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
            # Siempre enviamos el frame a la IA para que mantenga el conteo sin perder movimiento
            processor.update_frame(frame, tw_dict)
            processed_frame = processor.get_latest_processed_frame(frame)
            
            # 3. Salida a Cliente Web
            # Optimización: En hardware limitado, codificar JPG (cv2.imencode) 30 veces por segundo destroza el CPU.
            # Solo codificamos y enviamos la imagen al navegador a ~15 FPS (la mitad de los frames).
            # El conteo y la IA seguirán viendo todos los frames de forma independiente.
            skip_encode_counter += 1
            if skip_encode_counter % 2 == 0:
                ret, buffer = cv2.imencode('.jpg', processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
            # Restricción obligada para VOD: Si procesamos muy RÁPIDO, dormimos para no ir en cámara rápida.
            if not is_rtsp:
                curr_real = (time.time() - start_time_real)
                curr_video_time = frame_idx / video_fps
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
