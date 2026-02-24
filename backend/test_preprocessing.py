import cv2
import numpy as np
import sys
import os

# Add parent directory to path to import preprocessing
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from preprocessing import PreprocessingModule

def test_basic_processing():
    print("Testing basic processing...")
    proc = PreprocessingModule()
    # Create a dummy BGR frame (100x200)
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[25:75, 50:150] = [255, 0, 0] # Blue rectangle
    
    metadata = {"id": "cam1", "ts": 123456}
    
    p_frame, p_meta = proc.process_frame(frame, metadata)
    
    assert p_frame is not None
    assert p_frame.shape == (640, 640, 3)
    assert p_meta == metadata
    print("✓ Basic processing passed")

def test_frame_skipping():
    print("Testing frame skipping...")
    proc = PreprocessingModule({"frame_skip": 3})
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    
    # 1st frame: process
    f1, _ = proc.process_frame(frame, {})
    assert f1 is not None
    
    # 2nd frame: skip
    f2, _ = proc.process_frame(frame, {})
    assert f2 is None
    
    # 3rd frame: skip
    f3, _ = proc.process_frame(frame, {})
    assert f3 is None
    
    # 4th frame: process
    f4, _ = proc.process_frame(frame, {})
    assert f4 is not None
    print("✓ Frame skipping passed")

def test_roi():
    print("Testing ROI...")
    # ROI: top-left quarter
    proc = PreprocessingModule({"roi": [0, 0, 0.5, 0.5], "resize": {"maintain_aspect_ratio": False}})
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[0:50, 0:50] = [0, 255, 0] # Green in ROI
    frame[50:100, 50:100] = [0, 0, 255] # Red outside ROI
    
    p_frame, _ = proc.process_frame(frame, {})
    # Since it's resized to 640x640, we check if it's all green (Blue=0, Green=255, Red=0 in BGR)
    # The ROI was 50x50 green. After resize, it should still be mostly green.
    assert np.all(p_frame[..., 1] == 255)
    assert np.all(p_frame[..., 0] == 0)
    assert np.all(p_frame[..., 2] == 0)
    print("✓ ROI passed")

def test_normalization_and_color():
    print("Testing normalization and color conversion...")
    proc = PreprocessingModule({
        "color_space": "RGB",
        "normalization": True,
        "resize": {"width": 10, "height": 10}
    })
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[:] = [255, 0, 0] # Pure Blue in BGR
    
    p_frame, _ = proc.process_frame(frame, {})
    assert p_frame.dtype == np.float32
    assert np.max(p_frame) <= 1.0
    # In RGB, Blue is [0, 0, 1]
    assert np.all(p_frame[..., 0] == 0)
    assert np.all(p_frame[..., 1] == 0)
    assert np.all(p_frame[..., 2] == 1.0)
    print("✓ Normalization and Color passed")

def test_enhancement():
    print("Testing enhancement filters...")
    proc = PreprocessingModule({
        "enhancement": {
            "enabled": True,
            "brightness": 50,
            "contrast": 1.5,
            "denoise": True
        }
    })
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[:] = 100
    
    p_frame, _ = proc.process_frame(frame, {})
    assert p_frame is not None
    # 100 * 1.5 + 50 = 200
    assert np.all(p_frame >= 190) # Allow some variance due to denoise/rounding
    print("✓ Enhancement passed")

if __name__ == "__main__":
    try:
        test_basic_processing()
        test_frame_skipping()
        test_roi()
        test_normalization_and_color()
        test_enhancement()
        print("\nALL TESTS PASSED!")
    except Exception as e:
        print(f"\nTEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
