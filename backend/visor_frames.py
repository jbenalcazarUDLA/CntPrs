import cv2
import argparse
import sys
import os
import numpy as np

# Ajustar path para importación de SQLAlchemy
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.database import SessionLocal
from backend.models import Tripwire

def parse_mot_gt(gt_path):
    """
    Parses a MOT format Ground Truth file.
    MOT format: <frame>, <id>, <bb_left>, <bb_top>, <bb_width>, <bb_height>, <conf>, <x>, <y>, <z>
    Note: Some formats use 1-based indexing for frames.
    Returns: A dict mapping frame_id (int) to a list of dicts:
      {'id': int, 'box': [x1, y1, x2, y2]}
    """
    gt_frames = {}
    if not gt_path or not os.path.exists(gt_path):
        return gt_frames
        
    with open(gt_path, 'r') as f:
        for line in f:
            parts = line.strip().split(',')
            if len(parts) >= 6:
                try:
                    # CVAT MOT tends to be 1-based, we'll try to handle it (assuming 0-indexed for simplicity in display if possible)
                    frame_id = int(float(parts[0])) - 1 # 0-indexed internal for video matching
                    track_id = int(float(parts[1]))
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
                except ValueError:
                    continue
                
    return gt_frames

def main():
    parser = argparse.ArgumentParser(description="Visor de Fotogramas para Anotación de Video con Tracking Visual")
    parser.add_argument('--video', type=str, required=True, help="Ruta al archivo de video .mp4")
    parser.add_argument('--source-id', type=int, required=False, help="ID de la cámara en la BD para cargar el Tripwire")
    parser.add_argument('--gt-mot', type=str, required=False, help="Ruta al archivo MOT (gt.txt) para mostrar líneas de rastro")
    parser.add_argument('--out', type=str, default='EVAL/gt_counts.txt', help="Archivo de salida para el conteo")
    parser.add_argument('--tw', type=str, required=False, help="Ignorado si se usa --source-id. Coordenadas manuales del Tripwire: x1,y1,x2,y2,DIR", default="")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"Error: No se pudo abrir el video {args.video}")
        return
        
    original_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    original_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    tw_data = None
    
    # 1. Intentar cargar Tripwire desde BD si se provee source-id
    if args.source_id is not None:
        db = SessionLocal()
        tw_record = db.query(Tripwire).filter(Tripwire.source_id == args.source_id).first()
        db.close()
        if tw_record:
            tw_data = {
                'x1': int(tw_record.x1 * original_w),
                'y1': int(tw_record.y1 * original_h),
                'x2': int(tw_record.x2 * original_w),
                'y2': int(tw_record.y2 * original_h),
                'dir': tw_record.direction or 'IN'
            }
            print(f"Loaded Tripwire from DB (Source {args.source_id})")
        else:
            print(f"No tripwire found in DB for source_id={args.source_id}")

    # Fallback a parámetro manual del Tripwire
    if not tw_data and args.tw:
        try:
            parts = args.tw.split(',')
            tw_data = {
                'x1': int(float(parts[0]) * original_w),
                'y1': int(float(parts[1]) * original_h),
                'x2': int(float(parts[2]) * original_w),
                'y2': int(float(parts[3]) * original_h),
                'dir': parts[4].upper() if len(parts) > 4 else 'IN'
            }
        except: pass

    # 2. Cargar MOT Tracks (Opcional)
    gt_tracks = {}
    if args.gt_mot:
        print(f"Cargando rastreo visual desde: {args.gt_mot}")
        gt_tracks = parse_mot_gt(args.gt_mot)
        print(f"Detecciones cargadas en {len(gt_tracks)} frames.")

    # Inicializar archivo de salida
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    if not os.path.exists(args.out):
        with open(args.out, 'w') as f:
            f.write("# frame_id, direction (1 = IN, -1 = OUT)\n") 

    frame_idx = 0
    paused = False
    ret, frame = cap.read()
    
    # Historial de trayectorias en memoria (track_id -> list of (cx, cy))
    track_histories = {}

    print("\n" + "="*50)
    print("      CONTROLES DEL VISOR Y ANOTADOR")
    print("="*50)
    print("[ESPACIO] : Pausar / Reproducir")
    print("[ D ]     : Avanzar un fotograma (solo en pausa)")
    print("[ I ]     : Registrar ENTRADA (1) en frame actual")
    print("[ O ]     : Registrar SALIDA (-1) en frame actual")
    print("[ Q ]     : Salir")
    print(f"Guardando tu conteo Ground Truth en: {args.out}")
    print("="*50 + "\n")

    while ret:
        display_frame = frame.copy()
        
        # Render Tracking (MOT Ground Truth / YOLO)
        current_objs = gt_tracks.get(frame_idx, [])
        active_ids = set()
        
        for obj in current_objs:
            tid = obj['id']
            box = obj['box']
            active_ids.add(tid)
            
            # Centro de masa (Centroide geométrico)
            cx = int((box[0] + box[2]) / 2)
            cy = int((box[1] + box[3]) / 2)
            
            if tid not in track_histories:
                track_histories[tid] = []
            
            history = track_histories[tid]
            history.append((cx, cy))
            if len(history) > 30: history.pop(0)
            
            # Dibujar BBox (Verde Suave)
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), (100, 255, 100), 2)
            cv2.putText(display_frame, f"ID:{tid}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 100), 2)
            
            # Dibujar Rastro (Amarillo)
            for i in range(1, len(history)):
                cv2.line(display_frame, history[i-1], history[i], (0, 255, 255), 2)
                
            # Dibujar Punto de Control (Azul) - El punto que atraviesa la línea
            cv2.circle(display_frame, (cx, cy), 5, (255, 0, 0), -1)

        # Info de Frame
        cv2.putText(display_frame, f"FRAME: {frame_idx}", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        
        # Dibujar Tripwire (Cian)
        if tw_data:
            cv2.line(display_frame, (tw_data['x1'], tw_data['y1']), (tw_data['x2'], tw_data['y2']), (255, 255, 0), 3)
            cv2.putText(display_frame, f"LINEA ({tw_data['dir']})", (tw_data['x1'], tw_data['y1'] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        
        status = "PAUSADO" if paused else "REPRODUCIENDO"
        color = (0, 0, 255) if paused else (0, 255, 0)
        cv2.putText(display_frame, status, (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.putText(display_frame, "[Espacio]: Pausa | [D]: Frame sig.", (30, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(display_frame, "[I]: Anotar ENTRADA | [O]: Anotar SALIDA", (30, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        cv2.imshow("Anotador Ground Truth de Eventos", display_frame)

        key = cv2.waitKey(0 if paused else 30) & 0xFF
        char_key = chr(key).lower() if key < 256 else ''

        if char_key == 'q':
            break
        elif key == ord(' '):
            paused = not paused
        elif char_key == 'd' and paused:
            ret, frame = cap.read()
            if ret:
                frame_idx += 1
        elif char_key == 'i':
            with open(args.out, 'a') as f:
                f.write(f"{frame_idx},1\n")
            print(f"✔️ ENTRADA anotada en el frame {frame_idx}")
        elif char_key == 'o':
            with open(args.out, 'a') as f:
                f.write(f"{frame_idx},-1\n")
            print(f"✔️ SALIDA anotada en el frame {frame_idx}")
        elif not paused:
            ret, frame = cap.read()
            if ret:
                frame_idx += 1
        
        # Limpiar historiales de ID perdidos
        for tid in list(track_histories.keys()):
            if tid not in active_ids:
                # No los borramos inmediatamente para dejar rastro visual unos frames más, 
                # pero en el visor es mejor borrarlos para no saturar memoria.
                del track_histories[tid]

    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
