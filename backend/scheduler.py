import threading
import time
import cv2
import datetime
import logging
import os
from apscheduler.schedulers.background import BackgroundScheduler
from .database import SessionLocal
from . import crud, models, schemas
from .services.async_yolo import MultiprocessYOLO

scheduler_logger = logging.getLogger("scheduler")
scheduler_logger.setLevel(logging.INFO)
if not scheduler_logger.handlers:
    rfh = logging.FileHandler("scheduler.log")
    rfh.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    scheduler_logger.addHandler(rfh)

active_tasks = {}

class HeadlessStreamTask(threading.Thread):
    def __init__(self, source_id, source_path, is_rtsp):
        super().__init__(daemon=True)
        self.source_id = source_id
        self.source_path = source_path
        self.is_rtsp = is_rtsp
        self.stop_event = threading.Event()
        self.processor = None
        self.start_time_record = datetime.datetime.now()
        
    def run(self):
        scheduler_logger.info(f"[SCHEDULER] Iniciando pipeline headless para fuente {self.source_id}")
        
        if self.is_rtsp:
            os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
            os.environ["AV_LOG_LEVEL"] = "-8"
            os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|fflags;discardcorrupt|flags;low_delay|stimeout;10000000|rw_timeout;10000000"

        raw_cap = cv2.VideoCapture(self.source_path, cv2.CAP_FFMPEG) if self.is_rtsp else cv2.VideoCapture(self.source_path)
        from .services.video_reader import VideoReaderWrapper
        cap = VideoReaderWrapper(raw_cap, is_rtsp=self.is_rtsp)
        
        if self.is_rtsp and "OPENCV_FFMPEG_CAPTURE_OPTIONS" in os.environ:
            del os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]

        if not cap.isOpened():
            scheduler_logger.error(f"[SCHEDULER] No se pudo abrir la fuente {self.source_id}")
            return
            
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        
        self.processor = MultiprocessYOLO(self.source_id)
        
        last_tripwire_update = 0
        tw_dict = None
        
        while not self.stop_event.is_set():
            success, frame = cap.read()
            if not success:
                if not self.is_rtsp:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    time.sleep(1)
                    continue
            
            curr_time = time.time()
            if curr_time - last_tripwire_update > 5:
                db = SessionLocal()
                tripwire_data = crud.get_tripwire(db, self.source_id)
                db.close()
                if tripwire_data:
                    tw_dict = {
                        'x1': tripwire_data.x1, 'y1': tripwire_data.y1,
                        'x2': tripwire_data.x2, 'y2': tripwire_data.y2,
                        'direction': tripwire_data.direction
                    }
                last_tripwire_update = curr_time
                
            self.processor.update_frame(frame, tw_dict)
            self.processor.get_latest_processed_frame(frame)
            
            if not self.is_rtsp:
                time.sleep(0.033)
                
        # Cleanup and Save History
        scheduler_logger.info(f"[SCHEDULER] Deteniendo pipeline headless para fuente {self.source_id}")
        cap.release()
        
        if self.processor:
            total_in, total_out = self.processor.get_counts()
            self.processor.stop()
            
        import gc
        gc.collect()
            
        if self.processor:
            # Guardamos historial
            db = SessionLocal()
            end_time_record = datetime.datetime.now()
            try:
                historico = schemas.HistoricoConteoCreate(
                    source_id=self.source_id,
                    fecha_registro=self.start_time_record.strftime("%Y-%m-%d"),
                    hora_apertura=self.start_time_record.strftime("%H:%M:%S"),
                    hora_cierre=end_time_record.strftime("%H:%M:%S"),
                    total_in=total_in,
                    total_out=total_out
                )
                crud.create_historico_conteo(db, historico)
                scheduler_logger.info(f"[SCHEDULER] Historial guardado: IN {total_in}, OUT {total_out}")
            except Exception as e:
                scheduler_logger.error(f"[SCHEDULER] Error guardando historial: {e}")
            finally:
                db.close()

def check_schedules():
    """Esta función es llamada cada minuto por APScheduler"""
    now = datetime.datetime.now()
    current_time_str = now.strftime("%H:%M")
    day_mapping = {
        0: 'monday', 1: 'tuesday', 2: 'wednesday',
        3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'
    }
    current_day_str = day_mapping[now.weekday()]
    
    db = SessionLocal()
    try:
        sources = crud.get_video_sources(db)
        for source in sources:
            schedule = crud.get_camera_schedule(db, source.id)
            if not schedule or not schedule.is_active:
                if source.id in active_tasks:
                    active_tasks[source.id].stop_event.set()
                    del active_tasks[source.id]
                continue
                
            is_active_today = getattr(schedule, current_day_str)
            
            should_run = False
            if is_active_today:
                if schedule.start_time <= current_time_str < schedule.end_time:
                    should_run = True
            
            if should_run and source.id not in active_tasks:
                # IMPORTANT: Start the task in a detached thread so we don't block the scheduler 
                # while cv2.VideoCapture connects (which can take seconds for RTSP)
                def launch_task(sid, spath, srtsp):
                    try:
                        t = HeadlessStreamTask(sid, spath, srtsp)
                        active_tasks[sid] = t
                        t.start()
                        scheduler_logger.info(f"[SCHEDULER] Started camera {sid}")
                    except Exception as e:
                        scheduler_logger.error(f"[SCHEDULER] Failed to start camera {sid}: {e}")
                        
                threading.Thread(target=launch_task, args=(source.id, source.path_url, source.type == 'rtsp'), daemon=True).start()
                scheduler_logger.info(f"[SCHEDULER] Requesting start for camera {source.id} in background thread")
                
            elif not should_run and source.id in active_tasks:
                scheduler_logger.info(f"[SCHEDULER] Stopping camera {source.id}")
                active_tasks[source.id].stop_event.set()
                active_tasks[source.id].join(timeout=2.0)
                del active_tasks[source.id]
                
    finally:
        db.close()

scheduler = None

def start_scheduler():
    global scheduler
    if scheduler is None:
        scheduler = BackgroundScheduler()
        # Call every minute at 00 seconds
        scheduler.add_job(check_schedules, 'cron', minute='*', max_instances=3)
        scheduler.start()
        scheduler_logger.info("[SCHEDULER] Background scheduler started")

def stop_scheduler():
    global scheduler
    if scheduler is not None:
        scheduler_logger.info("[SCHEDULER] Shutting down scheduler...")
        scheduler.shutdown(wait=False)
        for source_id, task in list(active_tasks.items()):
            task.stop_event.set()
            if task.processor:
                try:
                    task.processor.stop()
                except Exception:
                    pass
        scheduler = None
