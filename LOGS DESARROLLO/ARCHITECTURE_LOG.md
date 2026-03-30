# Debugging Detection and Tracking Issues

We are observed a low detection rate and an imbalance where more entries are counted than exits. This typically occurs because:
1. Tracks are lost before people fully cross the exit line, often due to decreasing bounding box size or confidence when moving away or towards the edges.
2. The center of the bounding box [(cx, cy)](file:///home/jbenalcazar/TITA/CntPrs/backend/services/detection.py#6-8) is used for crossing detection. As people approach the edges of the camera view, their bounding box gets cut off, shifting the center point such that it might never technically cross the tripwire.

## Proposed Changes

### Backend - Detection and Tracking

#### [MODIFY] [detection.py](file:///home/jbenalcazar/TITA/CntPrs/backend/services/detection.py)
- **Lower Confidence Thresholds**: Decrease `self.conf_threshold` from `0.35` to `0.25` to detect individuals at further distances and more obscure angles, preventing early track loss.
- **Update Centroid Calculation**: Change the tracking point from the exact center [(cx, cy)](file:///home/jbenalcazar/TITA/CntPrs/backend/services/detection.py#6-8) to the bottom-center (feet level). This is achieved by calculating `cy = int(box[3] - (box[3] - box[1]) * 0.1)`. This makes crossing lines at the bottom or top of the frame consistently measurable, as the feet position remains stable relative to the ground plane even if the top of the bounding box is clipped.
- **Reduce History Requirement**: Decrease the requirement from `len(history) >= 4` to `len(history) >= 3` to allow individuals who emerge very close to the tripwire to be counted without requiring 4 consecutive tracked frames prior to crossing.

#### [MODIFY] [custom_bytetrack.yaml](file:///home/jbenalcazar/TITA/CntPrs/backend/custom_bytetrack.yaml)
- **Adjust ByteTrack Thresholds**: Lower `track_high_thresh` from `0.40` to `0.30` and `new_track_thresh` from `0.40` to `0.30`. This ensures that tracks are maintained even if YOLO's detection confidence drops briefly, preventing ID switches right over the tripwire which cause lost exit tracking.
- **Increase Track Buffer**: Consider verifying or increasing `track_buffer` if required (currently 60, which should suffice, but we might increase up to 90 for more resilience).

## Verification Plan

### Manual Verification
1. The user will deploy the changes and monitor the live RTSP stream using the dashboard.
2. Observe the bounding box trails to ensure the tracking lines now originate near the feet/bottom of the subjects.
3. Validate over a period of actual traffic that the "entradas" versus "salidas" values are well-balanced and more closely align with real traffic, demonstrating that exits are no longer being prematurely lost.
