import multiprocessing as mp
import time
import numpy as np

def yolo_worker(frame_queue, result_queue, source_id):
    """
    Este Worker corre en su *propio proceso* (núcleo de CPU).
    Mantiene su propia instancia del detector YOLO para evadir el GIL de Python.
    """
    # Mantendremos la memoria de la última detección para devolverla rápido si no hay nuevo frame
    last_processed_frame = None
    
    try:
        from .detection import YoloDetector # Import lazy para no inicializar CUDA/MPS en proceso padre
        detector = YoloDetector()
    except Exception as e:
        import traceback
        print(f"Init Error: {e}")
        return

    while True:
        try:
            # Obtiene el frame más reciente. Bloquea hasta tener algo que hacer.
            data = frame_queue.get()
            if data is None:
                break # Señal de apagado
                
            frame, tripwire_data = data
            
            # Procesar el frame (Aproximadamente 100-200ms en CPU)
            # tripwire_data will arrive as a raw dictionary over the Queue, because SQLAlchemy models fail Pickling.
            class DummyTripwire: pass
            tw_obj = None
            if tripwire_data and tripwire_data.get('x1') is not None:
                tw_obj = DummyTripwire()
                tw_obj.x1 = float(tripwire_data.get('x1', 0.0) or 0.0)
                tw_obj.y1 = float(tripwire_data.get('y1', 0.0) or 0.0)
                tw_obj.x2 = float(tripwire_data.get('x2', 0.0) or 0.0)
                tw_obj.y2 = float(tripwire_data.get('y2', 0.0) or 0.0)
                tw_obj.direction = tripwire_data.get('direction', 'any') or 'any'
                
            last_processed_frame = detector.process_frame(frame, source_id, tw_obj)
            
            # Enviar resultado de vuelta
            # Vaciamos la cola de resultados vieja para asegurar insertar el último
            while not result_queue.empty():
                try:
                    result_queue.get_nowait()
                except Exception:
                    pass
            
            result_queue.put(last_processed_frame)
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            import traceback
            print(f"!!! CRASH IN YOLO WORKER !!!")
            print(f"[YOLO-WORKER-{source_id}] Exception: {e}")
            traceback.print_exc()
            time.sleep(0.5)

class MultiprocessYOLO:
    """
    Contenedor para delegar inferencia a un núcleo del CPU independiente.
    El flujo web (FastAPI) deposita frames aquí y solicita la última inferencia
    sin bloquear la cámara.
    """
    def __init__(self, source_id):
        self.source_id = source_id
        # Colas de tamaño 1: Solo guardamos el frame más reciente y olvidamos el resto
        self.frame_queue = mp.Queue(maxsize=1)
        self.result_queue = mp.Queue(maxsize=1)
        
        self.process = mp.Process(
            target=yolo_worker, 
            args=(self.frame_queue, self.result_queue, self.source_id),
            daemon=True
        )
        self.process.start()
        
        self.latest_result = None

    def update_frame(self, frame, tripwire_data=None):
        """Envía frame a procesar reemplazando el anterior si no se ha consumido."""
        try:
            # Vaciar fotogramas antiguos no procesados
            while not self.frame_queue.empty():
                try:
                    self.frame_queue.get_nowait()
                except Exception:
                    pass
                
            self.frame_queue.put_nowait((frame, tripwire_data))
        except Exception:
            pass # Si la cola se llena justo ahora, simplemente saltamos este frame

    def get_latest_processed_frame(self, fallback_frame):
        """Devuelve el resultado. Si YOLO aún no acaba, devuelve el último conocido o el original sin procesar"""
        try:
            # Verificar si el worker terminó de procesar un nuevo frame
            if not self.result_queue.empty():
                self.latest_result = self.result_queue.get_nowait()
        except Exception:
            pass
            
        return self.latest_result if self.latest_result is not None else fallback_frame

    def stop(self):
        """Apaga el proceso y libera memoria."""
        try:
            self.frame_queue.put(None) # Enviar señal de muerte
        except:
            pass
        self.process.terminate()
        self.process.join()
