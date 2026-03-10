import cv2
import collections
import threading
import time

class VideoReaderWrapper:
    """
    Un Wrapper para cv2.VideoCapture que usa un hilo en segundo plano (solo para RTSP)
    Garantiza que leemos el frame MÁS RECIENTE bloqueando hasta que llega, 
    evitando enviar False si el consumidor es más rápido que la cámara.
    """
    def __init__(self, cap, is_rtsp=False):
        self.cap = cap
        self.is_rtsp = is_rtsp
        self.q = collections.deque(maxlen=1)
        self.cond = threading.Condition()
        self.running = False
        self.thread = None
        
        if self.is_rtsp and self.cap.isOpened():
            self.running = True
            self.thread = threading.Thread(target=self._reader, daemon=True)
            self.thread.start()
            
    def _reader(self):
        # Continually drain frames from the OpenCV buffer as fast as possible
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.cond:
                    self.q.append(frame)
                    self.cond.notify()
            else:
                time.sleep(0.005)
                
    def read(self):
        ret, frame = False, None
        if self.is_rtsp:
            with self.cond:
                if len(self.q) == 0:
                    # Esperar hasta 1 segundo por un nuevo frame
                    self.cond.wait(timeout=1.0)
                
                if len(self.q) > 0:
                    ret, frame = True, self.q.pop()
        else:
            ret, frame = self.cap.read()
            
        # Reducir el tamano del frame si es muy grande para optimizar el stream y la red
        if ret and frame is not None:
            h, w = frame.shape[:2]
            if w > 800:
                scale = 800 / float(w)
                frame = cv2.resize(frame, (800, int(h * scale)))
                
        return ret, frame
            
    def release(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()

    def set(self, prop, value):
        return self.cap.set(prop, value)
        
    def isOpened(self):
        return self.cap.isOpened()
        
    def get(self, prop):
        return self.cap.get(prop)
