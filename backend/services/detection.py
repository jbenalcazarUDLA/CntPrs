import cv2
import numpy as np
from ultralytics import YOLO
import threading

class YoloDetector:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(YoloDetector, cls).__new__(cls)
                cls._instance._initialize()
            return cls._instance

    def _initialize(self):
        # Load a lightweight model, downloading if necessary
        # We use yolo11n as the user specifically requested YOLOv11 and we need it to be fast on CPU
        try:
            self.model = YOLO('yolo11n.pt')
        except Exception as e:
            print(f"Error loading YOLO model: {e}")
            self.model = None

        if self.model is not None:
            try:
                # Warm up the model to prevent 2-second delay on first inference
                dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
                self.model(dummy_frame, device='cpu', verbose=False)
            except Exception as e:
                print(f"Error warming up YOLO model: {e}")

        # Optimization settings
        self.conf_threshold = 0.35
        self.classes = [0] # 0 is 'person' in COCO dataset
        
        # We'll skip frames to save CPU.
        # This means we only run inference 1 in every N frames.
        self.frame_skip = 5
        
        # State tracking for streams (source_id -> state)
        # Keeps track of frame counts and last known bounding boxes
        self.stream_states = {}
        self.state_lock = threading.Lock()

    def process_frame(self, frame, source_id, tripwire_data=None):
        """
        Process a frame for a given source, applying YOLO detection.
        Uses frame skipping for performance.
        """
        if self.model is None or frame is None:
            return frame

        with self.state_lock:
            if source_id not in self.stream_states:
                self.stream_states[source_id] = {
                    "frame_count": 0,
                    "last_boxes": [],
                    "last_count": 0
                }
            state = self.stream_states[source_id]
            state["frame_count"] += 1
            run_inference = (state["frame_count"] % self.frame_skip == 1)

        original_h, original_w = frame.shape[:2]

        if run_inference:
            # Downscale for faster inference
            # 640 is the standard size, but we can go lower (e.g. 320) if CPU is still saturated
            inference_size = 640 
            
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
            
            with self.state_lock:
                state["last_boxes"] = new_boxes
                state["last_count"] = len(new_boxes)
        
        # Retrieve the latest boxes to draw (either new or cached)
        with self.state_lock:
            boxes_to_draw = state["last_boxes"]
            count = state["last_count"]

        # 1. Draw detections
        for b in boxes_to_draw:
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
        cv2.putText(frame, f"People present: {count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # Draw warning if we are skipping heavily
        # cv2.putText(frame, f"CPU Opt (Skip {self.frame_skip})", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        return frame

# Export a singleton instance
detector = YoloDetector()
