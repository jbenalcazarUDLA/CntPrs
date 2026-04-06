import argparse
import cv2
import sys
import os
import numpy as np

# Adjust path to import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.services.detection import YoloDetector
from backend.services.metrics import evaluate_detection_frame, calculate_iou, evaluate_tracking_frame
from backend.database import SessionLocal
from backend.models import Tripwire

class DummyTripwire:
    def __init__(self, x1, y1, x2, y2, direction):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.direction = direction

def get_tripwire_from_db(source_id):
    db = SessionLocal()
    try:
        tw = db.query(Tripwire).filter(Tripwire.source_id == source_id).first()
        if tw:
            return DummyTripwire(tw.x1, tw.y1, tw.x2, tw.y2, tw.direction or 'IN')
    finally:
        db.close()
    return None

def parse_events_gt(gt_path):
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

def parse_mot_gt(gt_path):
    gt_frames = {}
    if not os.path.exists(gt_path):
        return gt_frames
    with open(gt_path, 'r') as f:
        for line in f:
            parts = line.strip().split(',')
            if len(parts) >= 6:
                try:
                    frame_id = int(float(parts[0])) - 1
                    track_id = int(float(parts[1]))
                    x1, y1 = float(parts[2]), float(parts[3])
                    w, h = float(parts[4]), float(parts[5])
                    if frame_id not in gt_frames: gt_frames[frame_id] = []
                    gt_frames[frame_id].append({'id': track_id, 'box': [x1, y1, x1+w, y1+h]})
                except ValueError: continue
    return gt_frames

def main():
    parser = argparse.ArgumentParser(description="Evaluación Integral de Video Analytics (YOLO + ByteTrack + Counting)")
    parser.add_argument('--video', type=str, required=True, help="Ruta al video")
    parser.add_argument('--gt', type=str, required=False, help="Ruta al MOT Ground Truth", default="")
    parser.add_argument('--gt-counts', type=str, required=False, help="Ruta al Conteo Ground Truth", default="")
    parser.add_argument('--source-id', type=int, required=False, help="ID de la cámara en la BD para el Tripwire")
    parser.add_argument('--tw', type=str, required=False, help="Tripwire manual: x1,y1,x2,y2,DIR", default="")
    parser.add_argument('--iou', type=float, default=0.5, help="Umbral de IoU para matching")
    parser.add_argument('--show', action='store_true', help="Habilitar visualización")
    args = parser.parse_args()

    # 1. Cargar Configuración del Tripwire
    tripwire_config = None
    if args.source_id is not None:
        tripwire_config = get_tripwire_from_db(args.source_id)
        if tripwire_config: print(f"Loaded Tripwire from DB (Source {args.source_id})")
    
    if not tripwire_config and args.tw:
        try:
            parts = args.tw.split(',')
            tripwire_config = DummyTripwire(float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]), parts[4].upper())
            print(f"Loaded Manual Tripwire: {args.tw}")
        except: pass

    if not tripwire_config:
        print("Warning: No Tripwire configuration found. Counting evaluation will be disabled.")

    # 2. Cargar Ground Truths
    gt_data = parse_mot_gt(args.gt) if args.gt else {}
    gt_events = parse_events_gt(args.gt_counts) if args.gt_counts else []
    print(f"Loaded {len(gt_data)} frames of MOT GT and {len(gt_events)} Counting Events.")

    detector = YoloDetector()
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"Error: No se pudo abrir {args.video}")
        sys.exit(1)

    # Métricas
    total_tp, total_fp_det, total_fn_det = 0, 0, 0
    mot_mismatches, mot_fps, mot_misses, mot_gt_total = 0, 0, 0, 0
    pred_to_gt = {}
    
    system_events = []
    prev_entries, prev_exits = 0, 0

    frame_idx = 0
    print(f"Evaluando video en tiempo real...")
    
    while True:
        ret, frame = cap.read()
        if not ret: break

        current_gt = gt_data.get(frame_idx, [])
        gt_boxes = [g['box'] for g in current_gt]
        gt_tracks_dict = {g['id']: g['box'] for g in current_gt}
        
        # Procesamiento Real del Sistema
        processed_frame, metadata = detector.process_frame(frame, source_id=f"eval_{args.source_id}", tripwire_data=tripwire_config)
        
        # Capturar Eventos de Conteo
        cur_e = metadata.get("entry_count", 0)
        cur_x = metadata.get("exit_count", 0)
        if cur_e > prev_entries:
            for _ in range(cur_e - prev_entries): system_events.append({'frame': frame_idx, 'direction': 1})
        if cur_x > prev_exits:
            for _ in range(cur_x - prev_exits): system_events.append({'frame': frame_idx, 'direction': -1})
        prev_entries, prev_exits = cur_e, cur_x
        
        pred_boxes_data = metadata.get("boxes", [])
        pred_boxes = [b[0] for b in pred_boxes_data]
        pred_tracks_dict = {b[1]: b[0] for b in pred_boxes_data}

        # --- Evaluación de Visión (YOLO) ---
        det_res = evaluate_detection_frame(gt_boxes, pred_boxes, iou_threshold=args.iou)
        total_tp += det_res['tp']
        total_fp_det += det_res['fp']
        total_fn_det += det_res['fn']

        # --- Evaluación de Memoria (Tracking) ---
        matches, fps, misses = evaluate_tracking_frame(gt_tracks_dict, pred_tracks_dict, distance_threshold=args.iou)
        mot_gt_total += len(gt_tracks_dict)
        mot_fps += len(fps)
        mot_misses += len(misses)
        for g_id, p_id in matches:
            if p_id in pred_to_gt and pred_to_gt[p_id] != g_id: mot_mismatches += 1
            pred_to_gt[p_id] = g_id

        if args.show:
            cv2.imshow("Integración Analytics - Evaluación", processed_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break

        print(f"\rProgreso: Frame {frame_idx}... YOLO TP:{det_res['tp']} | Tracks:{len(pred_tracks_dict)}", end="")
        frame_idx += 1

    cap.release()
    cv2.destroyAllWindows()

    # 3. Matching de Conteo (Global Bipartite)
    count_tp, count_fp, count_fn, count_dir_err, total_lag = 0, 0, 0, 0, 0
    if len(gt_events) > 0:
        matched_sys = set()
        for g_ev in sorted(gt_events, key=lambda x: x['frame']):
            best_m = -1
            min_d = 500
            for s_idx, s_ev in enumerate(system_events):
                if s_idx in matched_sys: continue
                d = abs(g_ev['frame'] - s_ev['frame'])
                if d < min_d:
                    min_d = d
                    best_m = s_idx
            if best_m != -1:
                matched_sys.add(best_m)
                total_lag += min_d
                if system_events[best_m]['direction'] == g_ev['direction']: count_tp += 1
                else: count_dir_err += 1
            else: count_fn += 1
        count_fp = len(system_events) - len(matched_sys)

    # 4. Reporte Final
    print("\n\n" + "="*50)
    print("      RESULTADOS DE EVALUACIÓN INTEGRAL (CLIP)")
    print("="*50)
    
    # YOLO
    p_det = total_tp / (total_tp + total_fp_det) if (total_tp + total_fp_det) > 0 else 0
    r_det = total_tp / (total_tp + total_fn_det) if (total_tp + total_fn_det) > 0 else 0
    print(f"\n[ VISIÓN (YOLO) ]")
    print(f"Precision: {p_det:.4f} | Recall: {r_det:.4f} | F1: {(2*p_det*r_det/(p_det+r_det) if p_det+r_det>0 else 0):.4f}")
    
    # Tracking
    mota = 1.0 - (mot_fps + mot_misses + mot_mismatches) / mot_gt_total if mot_gt_total > 0 else 0.0
    print(f"\n[ MEMORIA (BYTETRACK) ]")
    print(f"MOTA Score: {mota:.4f} | ID Switches: {mot_mismatches} | FN-MOT: {mot_misses}")
    
    # Conteo
    if len(gt_events) > 0:
        print(f"\n[ DECISIÓN (TRIPWIRE) ]")
        p_cnt = count_tp / (count_tp + count_fp) if (count_tp + count_fp) > 0 else 0
        r_cnt = count_tp / (count_tp + count_fn) if (count_tp + count_fn) > 0 else 0
        print(f"Counting Precision: {p_cnt:.4f} (Against Ghosts)")
        print(f"Counting Recall:    {r_cnt:.4f} (Against Misses)")
        print(f"Direction Errors:   {count_dir_err}")
        if count_tp > 0: print(f"Average Lag:        {total_lag/count_tp:.1f} frames")
    
    print("\n" + "="*50)

if __name__ == '__main__':
    main()
