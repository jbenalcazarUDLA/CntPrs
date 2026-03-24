import argparse
import cv2
import sys
import os
import numpy as np

# Adjust path to import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.services.detection import YoloDetector
from backend.services.metrics import evaluate_detection_frame, calculate_iou, evaluate_tracking_frame

def parse_mot_gt(gt_path):
    """
    Parses a MOT format Ground Truth file.
    MOT format: <frame>, <id>, <bb_left>, <bb_top>, <bb_width>, <bb_height>, <conf>, <x>, <y>, <z>
    Note: frame id is 1-based in MOT.
    Returns: A dict mapping frame_id (int) to a list of dicts:
      {'id': int, 'box': [x1, y1, x2, y2]}
    """
    gt_frames = {}
    if not os.path.exists(gt_path):
        print(f"Error: GT file {gt_path} not found.")
        return gt_frames
        
    with open(gt_path, 'r') as f:
        for line in f:
            parts = line.strip().split(',')
            if len(parts) >= 6:
                frame_id = int(parts[0]) - 1 # 0-indexed internal
                track_id = int(parts[1])
                x1 = float(parts[2])
                y1 = float(parts[3])
                w = float(parts[4])
                h = float(parts[5])
                x2 = x1 + w
                y2 = y1 + h
                
                if frame_id not in gt_frames:
                    gt_frames[frame_id] = []
                    
                gt_frames[frame_id].append({
                    'id': track_id,
                    'box': [x1, y1, x2, y2]
                })
                
    return gt_frames

def main():
    parser = argparse.ArgumentParser(description="Evaluate YOLO + ByteTrack using MOT Ground Truth")
    parser.add_argument('--video', type=str, required=True, help="Path to the video file")
    parser.add_argument('--gt', type=str, required=True, help="Path to the Ground Truth text file (MOT format)")
    parser.add_argument('--iou', type=float, default=0.5, help="IoU threshold for matching")
    parser.add_argument('--show', action='store_true', help="Show the video with metrics rendered")
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"Error: Video file {args.video} not found.")
        sys.exit(1)

    print(f"Loading Ground Truth from: {args.gt}")
    gt_data = parse_mot_gt(args.gt)
    print(f"Loaded {sum(len(f) for f in gt_data.values())} GT boxes across {len(gt_data)} frames.")

    print(f"Loading Model and starting evaluation on: {args.video}")
    detector = YoloDetector()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print("Failed to open video source.")
        sys.exit(1)

    # Metrics Storage
    total_tp = 0
    total_fp_det = 0
    total_fn_det = 0

    # Tracking Metrics Storage
    mot_mismatches = 0
    mot_fps = 0
    mot_misses = 0
    mot_gt_total = 0
    
    # ID mappings across frames to count ID switches
    # Maps predicted object_id to the ground truth ID it was last matched with
    pred_to_gt = {} 

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Get GT for this frame
        current_gt = gt_data.get(frame_idx, [])
        gt_boxes = [g['box'] for g in current_gt]
        gt_tracks_dict = {g['id']: g['box'] for g in current_gt}
        
        # We need to hack `frame_skip` dynamically since evaluate should evaluate all frames
        # or we just let it run normally but GT is frame-by-frame. 
        # By default detector process_frame calculates on every frame passed to it if we don't skip.
        
        processed_frame, metadata = detector.process_frame(frame, source_id="eval_source")
        
        # metadata["boxes"] is format: [([x1, y1, x2, y2], track_id), ...]
        pred_boxes_data = metadata.get("boxes", [])
        pred_boxes = [b[0] for b in pred_boxes_data]
        pred_tracks_dict = {b[1]: b[0] for b in pred_boxes_data}

        # --- Detection Evaluation (IoU, precision, recall) ---
        det_res = evaluate_detection_frame(gt_boxes, pred_boxes, iou_threshold=args.iou)
        total_tp += det_res['tp']
        total_fp_det += det_res['fp']
        total_fn_det += det_res['fn']

        # --- Tracking Evaluation (MOTA) ---
        matches, fps, misses = evaluate_tracking_frame(gt_tracks_dict, pred_tracks_dict, distance_threshold=args.iou)
        mot_gt_total += len(gt_tracks_dict)
        mot_fps += len(fps)
        mot_misses += len(misses)
        
        # Count ID Switches (Mismatches)
        frame_switches = 0
        for g_id, p_id in matches:
            if p_id in pred_to_gt:
                if pred_to_gt[p_id] != g_id:
                    # ID Switch! This prediction ID was previously associated with a different GT ID
                    frame_switches += 1
            pred_to_gt[p_id] = g_id
            
        mot_mismatches += frame_switches

        if args.show:
            cv2.imshow("Evaluation", processed_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        print(f"\rProcessed frame {frame_idx}... TP:{det_res['tp']} FP:{det_res['fp']} FN:{det_res['fn']} IDSW:{frame_switches}", end="")
        frame_idx += 1

    cap.release()
    if args.show:
        cv2.destroyAllWindows()

    print("\n\n------------- EVALUATION RESULTS -------------")
    
    # Calculate Precision and Recall
    precision = total_tp / (total_tp + total_fp_det) if (total_tp + total_fp_det) > 0 else 0
    recall = total_tp / (total_tp + total_fn_det) if (total_tp + total_fn_det) > 0 else 0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    print("\n[ YOLO ] DETECTION METRICS:")
    print(f"Total True Positives (TP):  {total_tp}")
    print(f"Total False Positives (FP): {total_fp_det}")
    print(f"Total False Negatives (FN): {total_fn_det}")
    print(f"Precision:                  {precision:.4f}")
    print(f"Recall:                     {recall:.4f}")
    print(f"F1 Score:                   {f1_score:.4f}")
    print(f"IoU Threshold used:         {args.iou}")
    
    # Calculate MOTA
    # MOTA = 1 - (FP + FN + IDSW) / GT
    mota = 1.0 - (mot_fps + mot_misses + mot_mismatches) / mot_gt_total if mot_gt_total > 0 else 0.0
    
    print("\n[ ByteTrack ] TRACKING METRICS:")
    print(f"Total Ground Truth Tracks:  {mot_gt_total}")
    print(f"False Positives (MOT):      {mot_fps}")
    print(f"Misses (FN MOT):            {mot_misses}")
    print(f"ID Switches (Mismatches):   {mot_mismatches}")
    print(f"MOTA Score:                 {mota:.4f}")
    
    print("----------------------------------------------")
    if mota < 0.5:
        print("💡 INSIGHT: El problema recae gravemente en el TRACKING. Considera aumentar el framerate de la cámara u optimizar max_age en bytetrack")
    elif precision < 0.5 or recall < 0.5:
        print("💡 INSIGHT: El problema de conteo recae en la DETECCION. YOLO esta fallando en encontrar a las personas de forma consistente.")
    else:
        print("💡 INSIGHT: El modelo es relativamente consistente. Revisa la lógica geométrica del Tripwire (línea virtual).")

if __name__ == '__main__':
    main()
