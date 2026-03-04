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
        if self.is_rtsp:
            with self.cond:
                if len(self.q) == 0:
                    # Esperar hasta 1 segundo por un nuevo frame
                    self.cond.wait(timeout=1.0)
                
                if len(self.q) > 0:
                    return True, self.q.pop()
                else:
                    return False, None
        else:
            return self.cap.read()
            
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
