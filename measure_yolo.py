import time
from ultralytics import YOLO
import numpy as np
model = YOLO('yolo11n.pt')
frame = np.zeros((640, 640, 3), dtype=np.uint8)
for i in range(5):
    t0 = time.time()
    model(frame, device='cpu', verbose=False, imgsz=640)
    t1 = time.time()
    print(f"640x640: {t1-t0:.4f}s")
for i in range(5):
    t0 = time.time()
    model(frame, device='cpu', verbose=False, imgsz=320)
    t1 = time.time()
    print(f"320x320: {t1-t0:.4f}s")
