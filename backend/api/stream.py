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
    
    tripwire_data = get_tripwire_data(source_id)
    last_tripwire_update = time.time()

    # Iniciar motor IA en segundo plano aislado para esta cámara específica
    if source_id not in yolo_processors:
        yolo_processors[source_id] = MultiprocessYOLO(source_id)
    
    processor = yolo_processors[source_id]
    
    try:
        while True:
            # 1. Ingesta a FPS Máximos Libres
            success, frame = cap.read()
            if not success:
                # Si es un archivo local o stream se corta, manejarlo
                if not is_rtsp:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    time.sleep(1)
                    continue
            
            # Recargar metadata cada 5s
            if time.time() - last_tripwire_update > 5:
                tripwire_data = get_tripwire_data(source_id)
                last_tripwire_update = time.time()

            # 2. IA Delegada (No Bloqueante)
            # a) Mandamos frame crudo a la tubería del Worker (este lo procesará si está desocupado)
            processor.update_frame(frame, tripwire_data)
            
            # b) Pedimos inmediatamente el último dibujo disponible (0 delay)
            processed_frame = processor.get_latest_processed_frame(frame)

            # 3. Salida a Cliente Web
            # Reducir quality baja brutalmente el ancho de banda y uso de CPU en codificación
            ret, buffer = cv2.imencode('.jpg', processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
            # Restricción obligada para no consumir el 100% CPU del hilo principal en VOD
            if not is_rtsp:
                time.sleep(1.0 / 30.0) 
                
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
