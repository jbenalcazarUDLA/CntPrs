import cv2
import numpy as np
from backend.services.async_yolo import MultiprocessYOLO
import time

processor = MultiprocessYOLO(1)
frame = np.zeros((480, 640, 3), dtype=np.uint8)
tw_dict = {'x1': 0.1, 'y1': 0.5, 'x2': 0.9, 'y2': 0.5, 'direction': 'IN'}

# Submit a few frames
for _ in range(5):
    processor.update_frame(frame, tw_dict)
    time.sleep(0.5)

# Get processed frame
processed = processor.get_latest_processed_frame(frame)
if processed is frame:
    print("Failed to get processed frame, got original")
else:
    print("Success: got processed frame")

processor.stop()
