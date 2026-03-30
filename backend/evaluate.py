import argparse
import cv2
import sys
import os
import numpy as np

# Adjust path to import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.services.detection import YoloDetector
from backend.services.metrics import evaluate_detection_frame, calculate_iou, evaluate_tracking_frame

class DummyTripwire:
    def __init__(self, x1, y1, x2, y2, direction):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.direction = direction

def parse_events_gt(gt_path):
    """
    Parses an Event Ground Truth file.
    Format: <frame>, <direction> (1 for IN, -1 for OUT)
    """
    events = []
    if not gt_path or not os.path.exists(gt_path):
        return events
    with open(gt_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'): continue
            parts = line.split(',')
            if len(parts) >= 2:
                events.append({
                    'frame': int(parts[0]),
                    'direction': int(parts[1])
                })
    return sorted(events, key=lambda x: x['frame'])
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
    parser.add_argument('--gt', type=str, required=False, help="Path to the Ground Truth text file (MOT format)", default="")
    parser.add_argument('--gt-counts', type=str, required=False, help="Path to Counting Events Ground Truth CSV", default="")
    parser.add_argument('--tw', type=str, required=False, help="Tripwire format: x1,y1,x2,y2,DIR (e.g. 0.1,0.5,0.9,0.5,IN)", default="")
    parser.add_argument('--iou', type=float, default=0.5, help="IoU threshold for matching")
    parser.add_argument('--show', action='store_true', help="Show the video with metrics rendered")
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"Error: Video file {args.video} not found.")
        sys.exit(1)

    if args.gt and os.path.exists(args.gt):
        print(f"Loading Ground Truth MOT from: {args.gt}")
        gt_data = parse_mot_gt(args.gt)
        print(f"Loaded {sum(len(f) for f in gt_data.values())} GT boxes across {len(gt_data)} frames.")
    else:
        gt_data = {}
        
    gt_events = []
    if args.gt_counts and os.path.exists(args.gt_counts):
        print(f"Loading Ground Truth Counts from: {args.gt_counts}")
        gt_events = parse_events_gt(args.gt_counts)
        print(f"Loaded {len(gt_events)} GT counting events.")
        
    tripwire_config = None
    if args.tw:
        try:
            parts = args.tw.split(',')
            tripwire_config = DummyTripwire(float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]), parts[4].upper())
            print(f"Loaded Dummy Tripwire: {args.tw}")
        except Exception as e:
            print(f"Failed to parse tripwire: {e}")

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
    pred_to_gt = {} 

    # Counting Metrics
    system_events = []
    prev_entries = 0
    prev_exits = 0

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
        processed_frame, metadata = detector.process_frame(frame, source_id="eval_source", tripwire_data=tripwire_config)
        
        # Capture counting events
        current_entries = metadata.get("entry_count", 0)
        current_exits = metadata.get("exit_count", 0)
        
        if current_entries > prev_entries:
            for _ in range(current_entries - prev_entries):
                system_events.append({'frame': frame_idx, 'direction': 1})
        if current_exits > prev_exits:
            for _ in range(current_exits - prev_exits):
                system_events.append({'frame': frame_idx, 'direction': -1})
                
        prev_entries = current_entries
        prev_exits = current_exits
        
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

    # --- Match Counting Events ---
    count_tp = 0
    count_fp = 0
    count_fn = 0
    count_dir_err = 0
    
    if len(gt_events) > 0:
        matched_sys = set()
        matched_gt = set()
        TOLERANCE = 20 # frames
        
        for g_idx, g_ev in enumerate(gt_events):
            best_match_idx = -1
            min_dist = TOLERANCE + 1
            
            for s_idx, s_ev in enumerate(system_events):
                if s_idx in matched_sys: continue
                dist = abs(g_ev['frame'] - s_ev['frame'])
                if dist <= TOLERANCE and dist < min_dist:
                    min_dist = dist
                    best_match_idx = s_idx
                    
            if best_match_idx != -1:
                matched_gt.add(g_idx)
                matched_sys.add(best_match_idx)
                if system_events[best_match_idx]['direction'] == g_ev['direction']:
                    count_tp += 1
                else:
                    count_dir_err += 1
            else:
                count_fn += 1 # GT event missed by system
                
        count_fp = len(system_events) - len(matched_sys) # Ghost counts

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
    
    if len(gt_events) > 0:
        count_precision = count_tp / (count_tp + count_fp) if (count_tp + count_fp) > 0 else 0
        count_recall = count_tp / (count_tp + count_fn) if (count_tp + count_fn) > 0 else 0
        
        print("\n[ Tripwire ] COUNTING METRICS:")
        print(f"Total Ground Truth Events:  {len(gt_events)}")
        print(f"System Detected Events:     {len(system_events)}")
        print(f"True Positives (TP):        {count_tp}")
        print(f"False Positives (Ghost):    {count_fp}")
        print(f"False Negatives (Missed):   {count_fn}")
        print(f"Direction Errors:           {count_dir_err}")
        print(f"Counting Precision:         {count_precision:.4f}")
        print(f"Counting Recall:            {count_recall:.4f}")
    
    print("----------------------------------------------")
    if mota < 0.5 and mot_gt_total > 0:
        print("💡 INSIGHT: El problema recae gravemente en el TRACKING. Considera aumentar el framerate de la cámara u optimizar max_age en bytetrack")
    elif (precision < 0.5 or recall < 0.5) and mot_gt_total > 0:
        print("💡 INSIGHT: El problema de conteo recae en la DETECCION. YOLO esta fallando en encontrar a las personas de forma consistente.")
    elif len(gt_events) > 0:
        if count_precision < 0.8:
            print("💡 INSIGHT: La línea virtual es MUY SENSIBLE (genera conteos falsos/fantasmas o hay rebotes). Ajusta su posición.")
        elif count_recall < 0.8:
            print("💡 INSIGHT: La línea virtual NO ALCANZA A CONTAR. Las personas la cruzan muy rápido o antes de ser marcados (distancia mínima de historial).")
        else:
            print("💡 INSIGHT: ¡El sistema de conteo es Óptimo!")
    else:
        print("💡 INSIGHT: El modelo de detección es relativamente consistente.")

if __name__ == '__main__':
    main()
