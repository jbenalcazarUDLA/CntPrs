import sys
import os
import cv2
import time
sys.path.append('.')
from backend.services.async_yolo import MultiprocessYOLO

source_id = 999
processor = MultiprocessYOLO(source_id)

tw_dict = {
    'x1': 0.1, 'y1': 0.5, 'x2': 0.9, 'y2': 0.5, 'direction': 'IN'
}

frame = __import__('numpy').zeros((1080, 1920, 3), dtype='uint8')

print("Starting feed...")
# Feed frame
processor.update_frame(frame, tw_dict)

# Wait a chunk so worker processes
time.sleep(3)

# Fetch latest
processed = processor.get_latest_processed_frame(frame)
print("Is processed identical to raw array?", id(processed) == id(frame))
print("Any Red pixels?", processed[:,:,2].max())

processor.stop()
print("Done")
