import argparse
import cv2
import os
import sys
import numpy as np
import zipfile
import shutil
import subprocess
from ultralytics import YOLO

# Adjust path to import backend modules or helper functions
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.services.metrics import evaluate_detection_frame, calculate_iou
from backend.preprocessing import PreprocessingModule

def get_accurate_frame_count(video_path):
    """
    Intenta obtener el conteo exacto de frames usando ffprobe (nb_read_packets).
    Es más lento que los metadatos pero mucho más confiable.
    """
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-count_packets", "-show_entries", "stream=nb_read_packets",
        "-of", "csv=p=0", video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        count_str = result.stdout.strip()
        if count_str.isdigit():
            return int(count_str)
    except Exception:
        pass
    return None

def parse_mot_gt(gt_path):
    """
    Parses a MOT format Ground Truth file.
    Format: <frame>, <id>, <bb_left>, <bb_top>, <bb_width>, <bb_height>, <conf>, <x>, <y>, <z>
    Note: frame id is 1-based in MOT.
    Returns: A dict mapping frame_id (int, 0-indexed) to a list of dicts:
      {'id': int, 'box': [x1, y1, x2, y2]}
    """
    gt_frames = {}
    if not os.path.exists(gt_path):
        return gt_frames
        
    with open(gt_path, 'r') as f:
        for line in f:
            parts = line.strip().split(',')
            if len(parts) >= 6:
                try:
                    frame_id = int(parts[0]) - 1 # 0-indexed internal
                    track_id = int(parts[1])
                    x1 = float(parts[2])
                    y1 = float(parts[3])
                    w = float(parts[4])
                    h = float(parts[5])
                    x2 = x1 + w
                    y2 = y1 + h
                    
                    if track_id < 0:
                        continue # Ignorar regiones 'Don't Care' o IDs no válidos (ej. -1)
                    
                    if frame_id not in gt_frames:
                        gt_frames[frame_id] = []
                        
                    gt_frames[frame_id].append({
                        'id': track_id,
                        'box': [x1, y1, x2, y2]
                    })
                except ValueError:
                    continue
                
    return gt_frames

def save_mot_format(output_path, detections):
    """
    Saves detections in MOT format.
    detections: list of (frame_id, track_id, x1, y1, w, h, conf)
    """
    with open(output_path, 'w') as f:
        for det in detections:
            # <frame>, <id>, <bb_left>, <bb_top>, <bb_width>, <bb_height>, <conf>, <class_id>, <visibility>, -1
            # Using 1 for class_id (assumes task has label 'person')
            line = f"{det[0]+1},{det[1]},{det[2]:.2f},{det[3]:.2f},{det[4]:.2f},{det[5]:.2f},{det[6]:.4f},1,-1,-1\n"
            f.write(line)

def save_mot_zip(output_zip, detections, video_info=None, label_name='person'):
    """
    Creates a ZIP file compatible with CVAT MOT 1.1.
    Includes seqinfo.ini to avoid NoneType errors in CVAT.
    """
    temp_dir = "temp_mot_cvat"
    gt_dir = os.path.join(temp_dir, "gt")
    os.makedirs(gt_dir, exist_ok=True)
    
    gt_file = os.path.join(gt_dir, "gt.txt")
    with open(gt_file, 'w') as f:
        current_frame = -1
        id_in_frame = 1
        for det in detections:
            frame_idx = det[0]
            if frame_idx != current_frame:
                current_frame = frame_idx
                id_in_frame = 1
            
            # <frame>, <id>, <bb_left>, <bb_top>, <bb_width>, <bb_height>, <conf>, <class_id>, <visibility>, -1
            # Using integer coordinates and 1 for class_id (mapped by labels.txt)
            line = f"{frame_idx+1},{id_in_frame},{int(det[2])},{int(det[3])},{int(det[4])},{int(det[5])},{det[6]:.4f},1,-1,-1\n"
            f.write(line)
            id_in_frame += 1
            
    # Create seqinfo.ini - This is often required by CVAT to avoid internal errors
    seq_info = [
        "[Sequence]",
        f"name={os.path.basename(output_zip).replace('.zip', '')}",
        "imDir=img1",
        "imExt=.jpg",
        f"seqLength={video_info['length'] if video_info else 5000}",
        f"imWidth={video_info['width'] if video_info else 1920}",
        f"imHeight={video_info['height'] if video_info else 1080}",
        "frameRate=30"
    ]
    seq_file = os.path.join(temp_dir, "seqinfo.ini")
    with open(seq_file, 'w') as f:
        f.write("\n".join(seq_info))

    # Create the ZIP file
    actual_length = detections[-1][0] + 1 if detections else 0
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(gt_file, arcname="gt/gt.txt")
        # Update seqinfo with actual exported length
        seq_info = [
            "[Sequence]",
            f"name={os.path.basename(output_zip).replace('.zip', '')}",
            "imDir=img1",
            "imExt=.jpg",
            f"seqLength={video_info['length'] if video_info else actual_length}",
            f"imWidth={video_info['width'] if video_info else 1920}",
            f"imHeight={video_info['height'] if video_info else 1080}",
            "frameRate=30"
        ]
        seq_file_updated = os.path.join(temp_dir, "seqinfo_final.ini")
        with open(seq_file_updated, 'w') as f:
            f.write("\n".join(seq_info))
        zf.write(seq_file_updated, arcname="seqinfo.ini")
        # Add labels.txt at root and inside gt/ with specified label
        # Important: must include newline
        label_content = f"{label_name}\n"
        zf.writestr("labels.txt", label_content)
        zf.writestr("gt/labels.txt", label_content) 
        
    # Cleanup temp directory
    shutil.rmtree(temp_dir)
    print(f"CVAT-compatible ZIP created successfully: {output_zip} (Frames: {actual_length})")
    print(f"Label mapped in labels.txt: {label_name}")

def main():
    parser = argparse.ArgumentParser(description="3.1 Capa de Visión (Detección - YOLO) Evaluation Script")
    parser.add_argument('--video', type=str, required=True, help="Ruta al video de prueba")
    parser.add_argument('--gt', type=str, help="Ruta al Ground Truth (archivo MOT .txt)", default=None)
    parser.add_argument('--model', type=str, default='yolo11n.pt', help="Nombre o ruta del modelo YOLO")
    parser.add_argument('--iou', type=float, default=0.5, help="Umbral IoU para considerar detección correcta (default: 0.5)")
    parser.add_argument('--conf', type=float, default=0.25, help="Umbral de confianza para YOLO")
    parser.add_argument('--save-detections', type=str, help="Ruta para guardar las detecciones de YOLO en formato MOT (para corrección manual)")
    parser.add_argument('--max-frames', type=int, default=None, help="Límite máximo de frames a procesar (para coincidir con CVAT)")
    parser.add_argument('--label', type=str, default='person', help="Etiqueta para las detecciones (ej: person, pedestrian). Default: person")
    parser.add_argument('--first-frame', type=int, default=1, help="Índice del primer frame en el archivo MOT (default: 1)")
    parser.add_argument('--show', action='store_true', help="Mostrar visualización en tiempo real")
    parser.add_argument('--roi', type=str, default=None, help="Formato x1,y1,x2,y2 (normalizado 0.0-1.0) para evaluar solo un área")
    parser.add_argument('--simulate-system', action='store_true', default=True, help="Simular el preprocesamiento real del sistema (Resize 800px, etc)")
    parser.add_argument('--brightness', type=int, default=0, help="Ajuste de brillo (-100 a 100)")
    parser.add_argument('--contrast', type=float, default=1.0, help="Ajuste de contraste (1.0 a 3.0)")
    parser.add_argument('--gamma', type=float, default=1.0, help="Corrección gamma (0.1 a 3.0)")
    parser.add_argument('--denoise', action='store_true', help="Activar reducción de ruido (GaussianBlur)")
    parser.add_argument('--save-video', type=str, help="Ruta para guardar el video PREPROCESADO (sin cajas)")
    parser.add_argument('--no-reverse', action='store_true', help="NO revertir coordenadas (usar coordenadas del video procesado)")
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"Error: Video no encontrado en {args.video}")
        sys.exit(1)

    print(f"Cargando modelo: {args.model}")
    model = YOLO(args.model)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"Error: No se pudo abrir el video {args.video}")
        sys.exit(1)

    # Get video info for seqinfo.ini
    print(f"Analizando video: {args.video}...")
    cv_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ff_count = get_accurate_frame_count(args.video)
    
    final_count = cv_count
    if ff_count is not None:
        if ff_count != cv_count:
            print(f"AVISO: OpenCV detecta {cv_count} frames, ffprobe {ff_count}. Usando {min(cv_count, ff_count)} para evitar error 501.")
            final_count = min(cv_count, ff_count)
    else:
        print(f"Info: Usando conteo de frames de OpenCV ({cv_count}).")

    if args.max_frames:
        print(f"Info: Aplicando límite manual de {args.max_frames} frames.")
        final_count = min(final_count, args.max_frames)

    video_info = {
        'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        'length': final_count,
        'fps': int(cap.get(cv2.CAP_PROP_FPS))
    }

    gt_data = {}
    if args.gt:
        print(f"Cargando Ground Truth desde: {args.gt}")
        gt_data = parse_mot_gt(args.gt)
        print(f"Frames con GT cargados: {len(gt_data)}")

    results = []
    total_tp = 0
    total_fp = 0
    total_fn = 0
    
    all_yolo_detections = [] # list of (frame_id, fake_id, x1, y1, w, h, conf)
    detection_counter = 1 # Global counter for unique IDs

    frame_idx = 0
    frames_limit = args.max_frames if args.max_frames is not None else video_info['length']
    
    # Inicializar módulo de preprocesamiento real
    preprocessor = PreprocessingModule()
    
    # Configurar simulación de sistema (Resize inicial de 800px)
    preprocessor.set_config({
        "source_resize": {
            "enabled": args.simulate_system,
            "width": 800
        }
    })

    # Configurar mejoras si se especifican
    if args.brightness != 0 or args.contrast != 1.0 or args.gamma != 1.0 or args.denoise:
        preprocessor.set_config({
            "enhancement": {
                "enabled": True,
                "brightness": args.brightness,
                "contrast": args.contrast,
                "gamma": args.gamma,
                "denoise": args.denoise
            }
        })
        print(f"Info: Mejoras de imagen activadas: B={args.brightness}, C={args.contrast}, G={args.gamma}, Denoise={args.denoise}")

    if args.roi:
        try:
            roi_values = [float(v) for v in args.roi.split(',')]
            if len(roi_values) == 4:
                preprocessor.set_config({"roi": roi_values})
                print(f"Info: Aplicando ROI de evaluación: {roi_values}")
        except Exception as e:
            print(f"Error parsing ROI: {e}")

    # Inicializar VideoWriter si se solicita
    video_writer = None
    if args.save_video:
        # Usamos dimension 640x640 por defecto del PreprocessingModule o la detectada en el primer frame
        target_w = preprocessor.config["resize"]["width"]
        target_h = preprocessor.config["resize"]["height"]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v') # Codec universal
        video_writer = cv2.VideoWriter(args.save_video, fourcc, video_info['fps'], (target_w, target_h))
        print(f"Info: Guardando video preprocesado en: {args.save_video} ({target_w}x{target_h})")

    while frame_idx < frames_limit:
        ret, frame_orig = cap.read()
        if not ret:
            break
        
        # --- Preprocesamiento Unificado ---
        # El módulo ahora maneja: Source Resize (800px), ROI, Resize (640px) con Padding y Enhancements
        frame, _ = preprocessor.process_frame(frame_orig)
        
        if frame is None:
            frame_idx += 1
            continue

        # Guardar frame en video (limpio, antes de dibujar cajas)
        if video_writer:
            video_writer.write(frame)

        # Ejecutar modelo YOLO
        # Usamos imgsz=640 para coincidir con la entrada del PreprocessingModule
        results_yolo = model(frame, device='cpu', verbose=False, conf=args.conf, imgsz=640)[0]
        
        pred_boxes = []
        for box in results_yolo.boxes:
            if int(box.cls[0]) == 0: # Person
                x1_p, y1_p, x2_p, y2_p = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                
                # --- COORDINADAS DE DESTINO (Mapeo o resolución procesada) ---
                if args.no_reverse:
                    # Usar coordenadas directas del frame que vio YOLO (ej: 640x640)
                    x1_final, y1_final, x2_final, y2_final = x1_p, y1_p, x2_p, y2_p
                else:
                    # REVERSIÓN UNIFICADA (Mapping a resolución original)
                    x1_final, y1_final, x2_final, y2_final = preprocessor.reverse_box([x1_p, y1_p, x2_p, y2_p])

                pred_boxes.append([x1_final, y1_final, x2_final, y2_final])
                
                # Para guardar en formato MOT (ID único para CVAT)
                mot_frame = frame_idx + args.first_frame
                all_yolo_detections.append((mot_frame - 1, detection_counter, x1_final, y1_final, x2_final-x1_final, y2_final-y1_final, conf))
                detection_counter += 1

        # Evaluación si hay GT
        if gt_data:
            current_gt = gt_data.get(frame_idx, [])
            gt_boxes = [g['box'] for g in current_gt]
            
            # evaluate_detection_frame usa linear_sum_assignment (Hungarian Algorithm)
            det_res = evaluate_detection_frame(gt_boxes, pred_boxes, iou_threshold=args.iou)
            total_tp += det_res['tp']
            total_fp += det_res['fp']
            total_fn += det_res['fn']
            
            if args.show:
                # Dibuja GT en verde, Pred en rojo sobre frame ORIGINAL
                for gbox in gt_boxes:
                    cv2.rectangle(frame_orig, (int(gbox[0]), int(gbox[1])), (int(gbox[2]), int(gbox[3])), (0, 255, 0), 2)
                for pbox in pred_boxes:
                    cv2.rectangle(frame_orig, (int(pbox[0]), int(pbox[1])), (int(pbox[2]), int(pbox[3])), (0, 0, 255), 1)
                
                cv2.putText(frame_orig, f"F: {frame_idx} TP:{det_res['tp']} FP:{det_res['fp']} FN:{det_res['fn']}", 
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        if args.show:
            cv2.imshow("Layer 3.1 Evaluation - Vision (System Simulation)", frame_orig)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        if frame_idx % 100 == 0:
            print(f"Procesando frame {frame_idx}...", end="\r")
        
        frame_idx += 1

    cap.release()
    if video_writer:
        video_writer.release()
    if args.show:
        cv2.destroyAllWindows()

    print(f"\nFinalizado: {frame_idx} frames procesados.")

    if gt_data:
        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        print("\n" + "="*40)
        print("MÉTRICAS CAPA DE VISIÓN (YOLO)")
        print("="*40)
        print(f"Total True Positives (TP): {total_tp}")
        print(f"Total False Positives (FP): {total_fp}")
        print(f"Total False Negatives (FN): {total_fn}")
        print("-"*40)
        print(f"PRECISIÓN: {precision:.4f}")
        print(f"RECALL:    {recall:.4f}")
        print(f"F1 SCORE:  {f1_score:.4f}")
        print("="*40)
        
        if recall < 0.8:
            print("Interpretación: Bajo recall -> el modelo no detecta personas (problema de visión).")
        if precision < 0.8:
            print("Interpretación: Baja precisión -> detecciones erróneas (ruido o falsos positivos).")
    else:
        print("\nNo se proporcionó Ground Truth para evaluación.")

    if args.save_detections:
        if args.save_detections.endswith('.zip'):
            save_mot_zip(args.save_detections, all_yolo_detections, video_info=video_info, label_name=args.label)
            print(f"IMPORTANTE: En CVAT, usa 'Upload annotations' -> 'MOT 1.1' y selecciona este archivo ZIP.")
            print(f"Asegúrate de que la etiqueta en CVAT se llame EXACTAMENTE: {args.label}")
        else:
            print(f"AVISO: Estás guardando en formato .txt puro. CVAT podría no reconocer la etiqueta '{args.label}' y usar 'pedestrian' por defecto.")
            print(f"Se recomienda usar extensión .zip para incluir el mapeo de etiquetas.")
            print(f"Guardando detecciones YOLO en formato MOT: {args.save_detections}")
            save_mot_format(args.save_detections, all_yolo_detections)

if __name__ == '__main__':
    main()
