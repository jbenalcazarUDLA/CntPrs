import cv2
import numpy as np
import os

class PreprocessingModule:
    """
    Standardizes and optimizes frames for detection models.
    """
    def __init__(self, config=None):
        self.config = {
            "resize": {
                "width": 640,
                "height": 640,
                "maintain_aspect_ratio": True,
                "padding": True
            },
            "color_space": "BGR", # "BGR" or "RGB"
            "normalization": False, # Scale to [0, 1]
            "frame_skip": 1, # Process every Nth frame
            "roi": None, # [x1, y1, x2, y2] normalized 0-1
            "enhancement": {
                "enabled": False,
                "brightness": 0,    # -100 to 100
                "contrast": 1.0,    # 1.0 to 3.0
                "gamma": 1.0,       # 0.1 to 3.0
                "denoise": False
            }
        }
        if config:
            self.set_config(config)
        
        self.frame_count = 0

    def set_config(self, config):
        """
        Updates the configuration dynamically.
        """
        if "resize" in config:
            self.config["resize"].update(config["resize"])
        if "enhancement" in config:
            self.config["enhancement"].update(config["enhancement"])
        
        # Simple top-level update for others
        for key in ["color_space", "normalization", "frame_skip", "roi"]:
            if key in config:
                self.config[key] = config[key]

    def _apply_roi(self, frame):
        if self.config["roi"] is None:
            return frame
        
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = self.config["roi"]
        
        # Convert normalized to pixel coordinates
        ix1, iy1 = int(x1 * w), int(y1 * h)
        ix2, iy2 = int(x2 * w), int(y2 * h)
        
        # Ensure within bounds
        ix1, iy1 = max(0, ix1), max(0, iy1)
        ix2, iy2 = min(w, ix2), min(h, iy2)
        
        if ix2 <= ix1 or iy2 <= iy1:
            return frame # Fallback to full frame if ROI is invalid
            
        return frame[iy1:iy2, ix1:ix2]

    def _apply_resize(self, frame):
        target_w = self.config["resize"]["width"]
        target_h = self.config["resize"]["height"]
        
        if not self.config["resize"]["maintain_aspect_ratio"]:
            return cv2.resize(frame, (target_w, target_h))
        
        h, w = frame.shape[:2]
        scale = min(target_w / w, target_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        
        resized = cv2.resize(frame, (new_w, new_h))
        
        if not self.config["resize"]["padding"]:
            return resized
            
        # Add padding (letterboxing)
        canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        # Center the image
        x_offset = (target_w - new_w) // 2
        y_offset = (target_h - new_h) // 2
        canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
        return canvas

    def _apply_enhancements(self, frame):
        cfg = self.config["enhancement"]
        if not cfg["enabled"]:
            return frame
            
        # Brightness and Contrast
        # new_image = alpha * image + beta
        if cfg["brightness"] != 0 or cfg["contrast"] != 1.0:
            frame = cv2.convertScaleAbs(frame, alpha=cfg["contrast"], beta=cfg["brightness"])
            
        # Gamma Correction
        if cfg["gamma"] != 1.0:
            invGamma = 1.0 / cfg["gamma"]
            table = np.array([((i / 255.0) ** invGamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
            frame = cv2.LUT(frame, table)
            
        # Denoising (Lightweight FastNlMeansDenoisingColored is usually too slow for real-time)
        # Using GaussianBlur for "light reduction of noise" as requested for efficiency
        if cfg["denoise"]:
            frame = cv2.GaussianBlur(frame, (3, 3), 0)
            
        return frame

    def process_frame(self, frame, metadata: dict):
        """
        Processes a single frame. returns (processed_frame, metadata)
        If frame should be skipped, returns (None, metadata).
        """
        if frame is None:
            return None, metadata
            
        self.frame_count += 1
        
        if (self.frame_count - 1) % self.config["frame_skip"] != 0:
            return None, metadata
            
        # 1. ROI
        frame = self._apply_roi(frame)
        
        # 2. Resize
        frame = self._apply_resize(frame)
        
        # 3. Enhancements
        frame = self._apply_enhancements(frame)
        
        # 4. Color Conversion
        if self.config["color_space"] == "RGB":
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
        # 5. Normalization
        if self.config["normalization"]:
            frame = frame.astype(np.float32) / 255.0
            
        # Metadata is conserved as requested
        return frame, metadata
