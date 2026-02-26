import cv2
import numpy as np
from ultralytics import YOLO

class YoloDetector:
    def __init__(self):
        # Load a lightweight model, downloading if necessary
        # We use yolo11n as the user specifically requested YOLOv11 and we need it to be fast on CPU
        try:
            self.model = YOLO('yolo11n.pt')
        except Exception as e:
            print(f"Error loading YOLO model: {e}")
            self.model = None

        if self.model is not None:
            try:
                # Warm up the model to prevent delay on first inference
                dummy_frame = np.zeros((320, 320, 3), dtype=np.uint8)
                self.model(dummy_frame, device='cpu', verbose=False)
            except Exception as e:
                print(f"Error warming up YOLO model: {e}")

        # Optimization settings
        self.conf_threshold = 0.35
        self.classes = [0] # 0 is 'person' in COCO dataset
        
        # State tracking for this specific process instance
        self.frame_count = 0
        self.last_boxes = []
        self.last_count = 0
        
        # We process 1 in every N frames to save CPU.
        self.frame_skip = 5

    def process_frame(self, frame, source_id, tripwire_data=None):
        """
        Process a frame applying YOLO detection.
        Since this runs in an isolated process, no threading locks are needed.
        """
        if self.model is None or frame is None:
            return frame

        self.frame_count += 1
        run_inference = (self.frame_count % self.frame_skip == 1)

        original_h, original_w = frame.shape[:2]

        if run_inference:
            # Downscale for faster inference
            # 320 instead of 640 dramatically speeds up YOLO on CPU, preserving real-time playback
            inference_size = 320 
            
            results = self.model(
                frame, 
                classes=self.classes, 
                conf=self.conf_threshold, 
                imgsz=inference_size, 
                verbose=False,
                device='cpu' # Explicitly force CPU
            )
            
            # Extract bounding boxes
            new_boxes = []
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    # Get box coordinates [x1, y1, x2, y2]
                    b = box.xyxy[0].cpu().numpy().astype(int)
                    new_boxes.append(b)
            
            self.last_boxes = new_boxes
            self.last_count = len(new_boxes)
        
        # 1. Draw detections using the latest known boxes
        for b in self.last_boxes:
            x1, y1, x2, y2 = b
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, 'Person', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # 2. Draw tripwire if provided
        if tripwire_data:
            # Tripwire coordinates are stored as percentages (0.0 - 1.0)
            tx1 = int(tripwire_data.x1 * original_w)
            ty1 = int(tripwire_data.y1 * original_h)
            tx2 = int(tripwire_data.x2 * original_w)
            ty2 = int(tripwire_data.y2 * original_h)
            
            cv2.line(frame, (tx1, ty1), (tx2, ty2), (0, 0, 255), 3)
            # Add label for tripwire direction
            cv2.putText(frame, f"LINE ({tripwire_data.direction})", (tx1, ty1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        # 3. Draw Count overlay
        cv2.putText(frame, f"People present: {self.last_count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        return frame

# Export a single dummy instance for backward compatibility just in case, but processes will make their own.
detector = YoloDetector()
