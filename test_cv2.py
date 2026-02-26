import cv2
import time
import os
import sys

# Test 1: Normal read
def test_read(video_path, name):
    print(f"\n--- Testing {name} ---")
    t0 = time.time()
    cap = cv2.VideoCapture(video_path)
    t1 = time.time()
    print(f"[{name}] cv2.VideoCapture took: {t1 - t0:.4f} seconds")
    
    if not cap.isOpened():
        print(f"[{name}] Failed to open {video_path}")
        return
        
    for i in range(5):
        t0 = time.time()
        cap.grab()
        t1 = time.time()
        print(f"[{name}] cap.grab() {i} took: {t1 - t0:.4f} seconds")
        
    t0 = time.time()
    success, frame = cap.read()
    t1 = time.time()
    print(f"[{name}] cap.read() took: {t1 - t0:.4f} seconds")
    cap.release()

if __name__ == "__main__":
    video_path = "test_video.mp4"
    if not os.path.exists(video_path):
        print(f"Error: {video_path} does not exist.")
        sys.exit(1)
        
    test_read(video_path, "Without Env Vars")
    
    # Set the env vars like stream.py does
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|strict;experimental"
    os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
    os.environ["AV_LOG_LEVEL"] = "-8"
    os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
    
    # Need to reload or just call it?
    # Some OpenCV properties cache the environment variable. 
    # Calling VideoCapture again should use the new env.
    test_read(video_path, "With RTSP Env Vars")
