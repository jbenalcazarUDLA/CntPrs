import cv2
import numpy as np
from ultralytics import YOLO
from collections import defaultdict

def ccw(A, B, C):
    return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])

def intersect(A, B, C, D):
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)

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
                # Warm up the model
                dummy_frame = np.zeros((320, 320, 3), dtype=np.uint8)
                self.model(dummy_frame, device='cpu', verbose=False)
            except Exception as e:
                print(f"Error warming up YOLO model: {e}")

        # Optimization settings
        self.conf_threshold = 0.35
        self.classes = [0] # 0 is 'person' in COCO dataset
        
        # Tracking history and tripwire state
        self.tracks = defaultdict(list)
        self.entry_count = 0
        self.exit_count = 0
        self.counted_ids = set() # To avoid double counting the same ID crossing multiple times
        
        self.frame_count = 0
        self.last_boxes = [] # tuple of (box, track_id)
        
        # We process 1 in every N frames to save CPU. Tracking algorithm stabilizes it.
        self.frame_skip = 5

    def process_frame(self, frame, source_id, tripwire_data=None):
        """
        Process a frame applying YOLO tracking and pure geometric intersection.
        """
        if self.model is None or frame is None:
            return frame

        self.frame_count += 1
        original_h, original_w = frame.shape[:2]

        # 320 instead of 640 dramatically speeds up YOLO on CPU
        inference_size = 320 
        
        # Use model.track with ByteTrack for high performance CPU ID assigning
        results = self.model.track(
            frame, 
            classes=self.classes, 
            conf=self.conf_threshold, 
            imgsz=inference_size, 
            verbose=False,
            device='cpu',
            persist=True,
            tracker="bytetrack.yaml"
        )
        
        new_boxes = []
        
        # Validar si el tripwire completo viene del DB
        valid_tripwire = False
        if tripwire_data and hasattr(tripwire_data, 'x1') and getattr(tripwire_data, 'x1') is not None and getattr(tripwire_data, 'y1') is not None and getattr(tripwire_data, 'x2') is not None and getattr(tripwire_data, 'y2') is not None:
            tx1 = int(tripwire_data.x1 * original_w)
            ty1 = int(tripwire_data.y1 * original_h)
            tx2 = int(tripwire_data.x2 * original_w)
            ty2 = int(tripwire_data.y2 * original_h)
            valid_tripwire = True
            A = (tx1, ty1)
            B = (tx2, ty2)
            dx = tx2 - tx1
            dy = ty2 - ty1
        
        for r in results:
            boxes = r.boxes
            if boxes.id is not None:
                track_ids = boxes.id.int().cpu().tolist()
                xyxys = boxes.xyxy.cpu().numpy().astype(int)
                
                for box, track_id in zip(xyxys, track_ids):
                    new_boxes.append((box, track_id))
                    
                    # Calculate center mass of the person
                    cx = int((box[0] + box[2]) / 2)
                    cy = int((box[1] + box[3]) / 2)
                    
                    history = self.tracks[track_id]
                    history.append((cx, cy))
                    
                    if len(history) > 30:
                        history.pop(0)

                    # Try to intersect with Tripwire if available and this ID hasn't been counted recently
                    if valid_tripwire and len(history) >= 2 and track_id not in self.counted_ids:
                        P_prev = history[-2]
                        P_curr = history[-1]
                        
                        # Verify distance between prev and curr to avoid fake jumps when Video files loop
                        dist = np.sqrt((P_curr[0] - P_prev[0])**2 + (P_curr[1] - P_prev[1])**2)
                        if dist < original_w / 3.0:  # Must move less than 33% of screen in one frame
                            # 1. Did the trajectory segment physically intersect the Tripwire segment?
                            if intersect(A, B, P_prev, P_curr):
                                # 2. Calculate direction using 2D Determinant (Cross Product)
                                side_prev = dx * (P_prev[1] - ty1) - dy * (P_prev[0] - tx1)
                                side_curr = dx * (P_curr[1] - ty1) - dy * (P_curr[0] - tx1)
                                
                                # Front-end arrow matrix correlation
                                # 'IN' points to cross < 0. 'OUT' points to cross > 0
                                dir_cfg = getattr(tripwire_data, 'direction', 'IN')
                                
                                # Avoid counting twice in same exact timestamp (sometimes lines intersect cleanly on boundary)
                                if side_prev > 0 and side_curr <= 0:
                                    # Crossed towards negative (The arrow side if IN)
                                    if dir_cfg == 'IN':
                                        self.entry_count += 1
                                    else:
                                        self.exit_count += 1
                                    self.counted_ids.add(track_id)
                                    
                                elif side_prev < 0 and side_curr >= 0:
                                    # Crossed towards positive (The arrow side if OUT)
                                    if dir_cfg == 'IN':
                                        self.exit_count += 1
                                    else:
                                        self.entry_count += 1
                                    self.counted_ids.add(track_id)

        self.last_boxes = new_boxes
        
        # Cleanup untracked IDs to avoid memory leaks
        active_ids = {tid for _, tid in new_boxes}
        for track_id in list(self.tracks.keys()):
            if track_id not in active_ids:
                pass
        
        # Render tracking visually
        for box, track_id in self.last_boxes:
            x1, y1, x2, y2 = box
            
            # Draw box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 165, 0), 2)
            cv2.putText(frame, f'ID:{track_id}', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 2)
            
            # Draw trail
            history = self.tracks[track_id]
            for i in range(1, len(history)):
                cv2.line(frame, history[i-1], history[i], (0, 255, 255), 2)

        # Render global overlays
        if valid_tripwire:
            cv2.line(frame, (tx1, ty1), (tx2, ty2), (0, 0, 255), 3)
            # Add label for tripwire direction
            dir_str = getattr(tripwire_data, 'direction', 'IN')
            if dir_str is None:
                dir_str = 'IN'
            cv2.putText(frame, f"LINE ({dir_str})", (tx1, ty1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        # Draw Counts (Improved HUD in Top-Right Corner)
        text_entries = f"Entradas: {self.entry_count}"
        text_exits = f"Salidas: {self.exit_count}"
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.45  # Reducido un 25% respecto a 0.6
        thickness = 1
        
        # Get text dimensions
        (w_ent, h_ent), _ = cv2.getTextSize(text_entries, font, font_scale, thickness)
        (w_ext, h_ext), _ = cv2.getTextSize(text_exits, font, font_scale, thickness)
        
        box_width = max(w_ent, w_ext) + 40
        box_height = h_ent + h_ext + 40
        
        # Position: Top Right
        x_offset = original_w - box_width - 20
        y_offset = 20
        
        # Semi-transparent background
        overlay = frame.copy()
        cv2.rectangle(overlay, (x_offset, y_offset), (x_offset + box_width, y_offset + box_height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        
        # Add a sleek border
        cv2.rectangle(frame, (x_offset, y_offset), (x_offset + box_width, y_offset + box_height), (255, 255, 255), 1)
        
        # Render Text
        cv2.putText(frame, text_entries, (x_offset + 20, y_offset + h_ent + 15), font, font_scale, (100, 255, 100), thickness)
        cv2.putText(frame, text_exits, (x_offset + 20, y_offset + h_ent + h_ext + 25), font, font_scale, (100, 100, 255), thickness)

        return frame

# Export a single dummy instance for backward compatibility just in case, but processes will make their own.
detector = YoloDetector()
