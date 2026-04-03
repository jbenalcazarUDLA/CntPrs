import argparse
import cv2
import os
import sys

# Adjust path to import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.services.metrics import evaluate_tracking_frame
from backend.evaluate_vision import parse_mot_gt
from ultralytics import YOLO

def main():
    parser = argparse.ArgumentParser(description="3.2 Capa de Memoria (Rastreo - ByteTrack) Evaluation Script")
    parser.add_argument('--video', type=str, required=True, help="Ruta al video (pre-procesado preferiblemente)")
    parser.add_argument('--gt', type=str, required=True, help="Ruta al Ground Truth (archivo MOT .txt con IDs)")
    parser.add_argument('--model', type=str, default='yolo11n.pt', help="Modelo YOLO")
    parser.add_argument('--conf', type=float, default=0.25, help="Umbral de confianza para YOLO")
    parser.add_argument('--iou', type=float, default=0.5, help="Umbral IoU para asignación de tracking con GT")
    parser.add_argument('--show', action='store_true', help="Mostrar visualización gráfica")
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"Error: Video no encontrado en {args.video}")
        sys.exit(1)
    if not os.path.exists(args.gt):
        print(f"Error: GT no encontrado en {args.gt}")
        sys.exit(1)

    print(f"Cargando modelo: {args.model}")
    model = YOLO(args.model)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print("Error al abrir video.")
        sys.exit(1)

    # El GT de MOT ya lo devuelve mapeado por frame_id basado en índice 0
    gt_data = parse_mot_gt(args.gt)

    unique_gt_ids = set()
    for frame_objs in gt_data.values():
        for obj in frame_objs:
            unique_gt_ids.add(obj['id'])
    total_unique_people = len(unique_gt_ids)

    tracker_path = os.path.join(os.path.dirname(__file__), "custom_bytetrack.yaml")
    if not os.path.exists(tracker_path):
        tracker_path = "bytetrack.yaml" # Fallback a tracker por defecto si no existe el custom

    frame_idx = 0
    total_gt_count = 0
    total_fp = 0
    total_fn = 0
    id_switches = 0
    
    gt_to_pred_map = {} # Registra el último pred_id asociado a un gt_id para detectar switches

    print("\nIniciando evaluación de memoria (Tracking puro sin procesamientos extra)...")
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Inferencia con tracker explícito, persistiendo IDs a lo largo de frames secuenciales
        # Usamos imgsz=640 asumiendo formato estandarizado
        results = model.track(
            frame, 
            conf=args.conf, 
            imgsz=640, 
            verbose=False, 
            persist=True, 
            tracker=tracker_path,
            device='cpu'
        )[0]

        pred_tracks = {}
        for box in results.boxes:
            if int(box.cls[0]) == 0 and box.id is not None:  # Person and has ID
                track_id = int(box.id[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                pred_tracks[track_id] = [x1, y1, x2, y2]

        current_gt_list = gt_data.get(frame_idx, [])
        gt_tracks = {g['id']: g['box'] for g in current_gt_list}
        
        # Incrementar conteo base del GT
        total_gt_count += len(gt_tracks)

        # Evaluar tracking
        matches, fps, misses = evaluate_tracking_frame(gt_tracks, pred_tracks, distance_threshold=args.iou)
        
        total_fp += len(fps)
        total_fn += len(misses)

        # Registrar ID Switches
        for gt_id, pred_id in matches:
            if gt_id in gt_to_pred_map:
                if gt_to_pred_map[gt_id] != pred_id:
                    id_switches += 1
                    # print(f"ID SWITCH: Track GT {gt_id} cambió de Pred {gt_to_pred_map[gt_id]} a Pred {pred_id} en frame {frame_idx}")
            gt_to_pred_map[gt_id] = pred_id

        if args.show:
             # Draw GT boxes in Green
             for gid, box in gt_tracks.items():
                 cv2.rectangle(frame, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (0, 255, 0), 2)
                 cv2.putText(frame, f"GT:{gid}", (int(box[0]), int(box[1])-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                 
             # Draw PRED boxes in Red
             for pid, box in pred_tracks.items():
                 cv2.rectangle(frame, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (0, 0, 255), 1)
                 cv2.putText(frame, f"P:{pid}", (int(box[0]), int(box[3])+15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
             
             cv2.putText(frame, f"Frame: {frame_idx} | ID Switches Acum: {id_switches}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
             cv2.imshow("Layer 3.2 Evaluation - Memory (Tracker)", frame)
             if cv2.waitKey(1) & 0xFF == ord('q'):
                 break

        if frame_idx % 100 == 0:
            print(f"Evaluando frame {frame_idx}...", end="\r")

        frame_idx += 1

    cap.release()
    if args.show:
        cv2.destroyAllWindows()

    # Cálculo final MOTA
    # Fórmula estandar: MOTA = 1 - (Sum(FP) + Sum(FN) + Sum(IDSW)) / Sum(GT)
    mota = 1.0 - ((total_fp + total_fn + id_switches) / total_gt_count) if total_gt_count > 0 else 0.0

    print("\n" + "="*50)
    print("MÉTRICAS CAPA DE MEMORIA (TRACKING - BYTETRACK)")
    print("="*50)
    print(f"Frames procesados:         {frame_idx}")
    print(f"Total Personas Únicas GT:  {total_unique_people} (identidades reales en el escenario)")
    print(f"Total Ocurrencias GT:      {total_gt_count} (bounding boxes acumulados en los frames)")
    print(f"Total Falsos Positivos:    {total_fp}")
    print(f"Total Falsos Negativos:    {total_fn}")
    print(f"Total ID Switches:         {id_switches}")
    print("-" * 50)
    print(f"MOTA (Tracking Accuracy):  {mota:.4f} ({(mota*100):.2f}%)")
    print("="*50)
    
    if id_switches > (total_gt_count * 0.05):
        print("Interpretación: Alto número de ID Switches detectado -> Riesgo alto de fragmentación (Doble conteo) al cruzar la línea virtual.")
    if mota < 0.6:
        print("Interpretación: Bajo MOTA -> Indica combinadamente pérdida de detección, exceso de falsos positivos e inestabilidad de trayectorias. Se sugiere ajustar conf o ByteTrack params.")
    else:
        print("Interpretación: Desempeño del tracker Aceptable/Bueno.")

if __name__ == '__main__':
    main()
