import cv2
import numpy as np
import os

class PreprocessingModule:
    """
    Standardizes and optimizes frames for detection models.
    """
    def __init__(self, config=None):
        self.config = {
            "source_resize": {
                "enabled": True,
                "width": 800
            },
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
        self.last_orig_dim = None # (w, h)
        self.last_reader_scale = 1.0
        self.last_p_scale = 1.0
        self.last_offsets = (0, 0) # (x, y) padding

    def set_config(self, config):
        """
        Updates the configuration dynamically.
        """
        if "source_resize" in config:
            self.config["source_resize"].update(config["source_resize"])
        if "resize" in config:
            self.config["resize"].update(config["resize"])
        if "enhancement" in config:
            self.config["enhancement"].update(config["enhancement"])
        
        # Simple top-level update for others
        for key in ["color_space", "normalization", "frame_skip", "roi"]:
            if key in config:
                self.config[key] = config[key]

    def _apply_source_resize(self, frame):
        """
        Simulates the VideoReaderWrapper behavior (Initial downscaling).
        """
        h, w = frame.shape[:2]
        target_w = self.config["source_resize"]["width"]
        if self.config["source_resize"]["enabled"] and w > target_w:
            scale = target_w / float(w)
            new_w = target_w
            new_h = int(h * scale)
            self.last_reader_scale = scale
            return cv2.resize(frame, (new_w, new_h))
        self.last_reader_scale = 1.0
        return frame

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
            self.last_p_scale = (target_w / frame.shape[1], target_h / frame.shape[0])
            self.last_offsets = (0, 0)
            return cv2.resize(frame, (target_w, target_h))
        
        h, w = frame.shape[:2]
        scale = min(target_w / w, target_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        self.last_p_scale = scale
        
        resized = cv2.resize(frame, (new_w, new_h))
        
        if not self.config["resize"]["padding"]:
            self.last_offsets = (0, 0)
            return resized
            
        # Add padding (letterboxing)
        canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        # Center the image
        x_offset = (target_w - new_w) // 2
        y_offset = (target_h - new_h) // 2
        self.last_offsets = (x_offset, y_offset)
        canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
        return canvas

    def reverse_box(self, box):
        """
        Maps a box [x1, y1, x2, y2] from processed space back to original space.
        """
        x1, y1 = self.reverse_point((box[0], box[1]))
        x2, y2 = self.reverse_point((box[2], box[3]))
        return [x1, y1, x2, y2]

    def reverse_point(self, point):
        """
        Maps a point (x, y) from processed space back to original space.
        """
        px, py = point
        
        # 1. Reverse Preprocessor Resize/Padding
        ox, oy = self.last_offsets
        # Correctly handle scale if it was a tuple (non-aspect ratio)
        if isinstance(self.last_p_scale, tuple):
            sx, sy = self.last_p_scale
        else:
            sx = sy = self.last_p_scale
            
        unscaled_x = (px - ox) / sx
        unscaled_y = (py - oy) / sy
        
        # 2. Reverse ROI
        if self.config["roi"]:
            h_pre, w_pre = self.last_reader_dim # Dim after reader resize but before ROI
            unscaled_x += self.config["roi"][0] * w_pre
            unscaled_y += self.config["roi"][1] * h_pre
            
        # 3. Reverse Source Resize
        final_x = unscaled_x / self.last_reader_scale
        final_y = unscaled_y / self.last_reader_scale
        
        return final_x, final_y

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

    def process_frame(self, frame, metadata: dict = None):
        """
        Processes a single frame. returns (processed_frame, metadata)
        If frame should be skipped, returns (None, metadata).
        """
        if frame is None:
            return None, metadata
            
        self.frame_count += 1
        
        if (self.frame_count - 1) % self.config["frame_skip"] != 0:
            return None, metadata
            
        # Store original dimensions for coordinate reversal
        h_orig, w_orig = frame.shape[:2]
        self.last_orig_dim = (w_orig, h_orig)
        
        # 1. Source Resize (Simulating VideoReaderWrapper)
        frame = self._apply_source_resize(frame)
        self.last_reader_dim = (frame.shape[1], frame.shape[0])
        
        # 2. ROI
        frame = self._apply_roi(frame)
        
        # 3. Resize (Model Input)
        frame = self._apply_resize(frame)
        
        # 4. Enhancements
        frame = self._apply_enhancements(frame)
        
        # 5. Color Conversion
        if self.config["color_space"] == "RGB":
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
        # 6. Normalization
        if self.config["normalization"]:
            frame = frame.astype(np.float32) / 255.0
            
        # Metadata is conserved as requested
        return frame, metadata
