import argparse
import os
import sys
import numpy as np
import cv2

# Adjust path to import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.database import SessionLocal
from backend.models import Tripwire
from backend.evaluate_vision import parse_mot_gt
from backend.evaluate import parse_events_gt

def ccw(A, B, C):
    return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])

def intersect(A, B, C, D):
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)

def get_tripwire_from_db(source_id):
    db = SessionLocal()
    try:
        tw = db.query(Tripwire).filter(Tripwire.source_id == source_id).first()
        if tw:
            return {
                'x1': tw.x1,
                'y1': tw.y1,
                'x2': tw.x2,
                'y2': tw.y2,
                'direction': tw.direction or 'IN'
            }
    finally:
        db.close()
    return None

def main():
    parser = argparse.ArgumentParser(description="Evaluación de Eficiencia Trigonométrica (Conteo con Rastreo Ideal)")
    parser.add_argument('--video', type=str, required=True, help="Ruta al video (para obtener dimensiones)")
    parser.add_argument('--gt-mot', type=str, required=True, help="Archivo MOT Ground Truth (Rastreo Ideal)")
    parser.add_argument('--gt-counts', type=str, required=True, help="Archivo Ground Truth de Conteo (Eventos)")
    parser.add_argument('--source-id', type=int, required=True, help="ID de la cámara en la BD para el Tripwire")
    parser.add_argument('--tolerance', type=int, default=20, help="Tolerancia de frames para emparejar eventos (default: 20)")
    parser.add_argument('--show', action='store_true', help="Habilitar visualización en tiempo real")
    parser.add_argument('--delay', type=int, default=1, help="Pausa entre frames en ms (default: 1, 0 para pausar)")
    args = parser.parse_args()

    # 1. Cargar Video
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"Error: No se pudo abrir el video {args.video}")
        sys.exit(1)
    original_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    original_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # 2. Cargar Tripwire desde BD
    tw_cfg = get_tripwire_from_db(args.source_id)
    if not tw_cfg:
        print(f"Error: No se encontró configuración de Tripwire para source_id={args.source_id}")
        sys.exit(1)
    
    print(f"--- Configuración del Tripwire (Cámara {args.source_id}) ---")
    print(f"Coordenadas Norm: ({tw_cfg['x1']:.4f}, {tw_cfg['y1']:.4f}) a ({tw_cfg['x2']:.4f}, {tw_cfg['y2']:.4f})")
    print(f"Dirección esperada: {tw_cfg['direction']}")
    
    # Escalar coordenadas a píxeles
    tx1, ty1 = int(tw_cfg['x1'] * original_w), int(tw_cfg['y1'] * original_h)
    tx2, ty2 = int(tw_cfg['x2'] * original_w), int(tw_cfg['y2'] * original_h)
    A = (tx1, ty1)
    B = (tx2, ty2)
    dx = tx2 - tx1
    dy = ty2 - ty1

    # 3. Cargar Ground Truths
    print("\nCargando Ground Truths...")
    gt_tracks = parse_mot_gt(args.gt_mot)
    gt_events = parse_events_gt(args.gt_counts)
    print(f"Sincronizados {len(gt_tracks)} frames con rastreo y {len(gt_events)} eventos de conteo.")

    # 4. Simulación de Conteo con Rastreo Ideal
    print("\nSimulando cruces...")
    system_events = []
    track_histories = {} # track_id -> list of (cx, cy)
    counted_ids = set()
    
    # Métricas de conteo durante la simulación
    sim_entry = 0
    sim_exit = 0

    frame_idx = 0
    paused = False
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        frame_objs = gt_tracks.get(frame_idx, [])
        active_ids = set()
        
        # Color para el tripwire (Rojo)
        tw_color = (0, 0, 255)
        
        for obj in frame_objs:
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
            
            if len(history) > 30:
                history.pop(0)

            # Lógica de Intersección
            is_crossing = False
            if len(history) >= 2 and tid not in counted_ids:
                P_prev = history[-2]
                P_curr = history[-1]
                
                # Evitar saltos por loop de video
                dist = np.sqrt((P_curr[0] - P_prev[0])**2 + (P_curr[1] - P_prev[1])**2)
                if dist < original_w / 3.0:
                    if intersect(A, B, P_prev, P_curr):
                        # Cálculo de dirección
                        side_prev = dx * (P_prev[1] - ty1) - dy * (P_prev[0] - tx1)
                        side_curr = dx * (P_curr[1] - ty1) - dy * (P_curr[0] - tx1)
                        
                        event_dir = 0
                        if side_prev > 0 and side_curr <= 0:
                            event_dir = 1 if tw_cfg['direction'] == 'IN' else -1
                        elif side_prev < 0 and side_curr >= 0:
                            event_dir = -1 if tw_cfg['direction'] == 'IN' else 1
                            
                        if event_dir != 0:
                            is_crossing = True
                            if event_dir == 1: sim_entry += 1
                            else: sim_exit += 1
                            
                            print(f"[DEBUG] Cruce Detectado: Frame {frame_idx}, Dirección {event_dir}, ID {tid}")
                            system_events.append({'frame': frame_idx, 'direction': event_dir})
                            counted_ids.add(tid)
                            tw_color = (0, 255, 0) # Destello Verde en la línea al cruzar
            
            # Visualización por objeto
            if args.show:
                x1, y1, x2, y2 = map(int, box)
                # BBox Green
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"ID:{tid}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                
                # Trail (Amarillo)
                for i in range(1, len(history)):
                    cv2.line(frame, history[i-1], history[i], (0, 255, 255), 2)
                
                # Centro de Masa Actual (Punto Azul)
                cv2.circle(frame, (cx, cy), 5, (255, 0, 0), -1)
                
                if is_crossing:
                    cv2.putText(frame, "CRUCE!", (cx, cy - 20), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 3)

        # Limpieza de historiales inactivos
        for tid in list(track_histories.keys()):
            if tid not in active_ids:
                del track_histories[tid]
                counted_ids.discard(tid)

        if args.show:
            # Dibujar Tripwire
            cv2.line(frame, (tx1, ty1), (tx2, ty2), tw_color, 3)
            cv2.putText(frame, f"LINEA ({tw_cfg['direction']})", (tx1, ty1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, tw_color, 2)
            
            # HUD
            cv2.rectangle(frame, (10, 10), (250, 120), (0, 0, 0), -1)
            cv2.putText(frame, f"Frame: {frame_idx}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.putText(frame, f"Entradas: {sim_entry}", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 255, 100), 2)
            cv2.putText(frame, f"Salidas:  {sim_exit}", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 255), 2)
            
            cv2.imshow("Validacion Trigonométrica - Rastreo Ideal", frame)
            
            key = cv2.waitKey(0 if paused else args.delay) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):
                paused = not paused
        
        frame_idx += 1

    cap.release()
    if args.show:
        cv2.destroyAllWindows()

    # 5. Comparación (Matching) de Eventos (Se mantiene igual)
    count_tp = 0
    count_fp = 0
    count_fn = 0
    count_dir_err = 0
    
    matched_sys = set()
    for g_idx, g_ev in enumerate(gt_events):
        best_match_idx = -1
        min_dist = args.tolerance + 1
        for s_idx, s_ev in enumerate(system_events):
            if s_idx in matched_sys: continue
            dist = abs(g_ev['frame'] - s_ev['frame'])
            if dist <= args.tolerance and dist < min_dist:
                min_dist = dist
                best_match_idx = s_idx
        
        if best_match_idx != -1:
            matched_sys.add(best_match_idx)
            if system_events[best_match_idx]['direction'] == g_ev['direction']:
                count_tp += 1
            else:
                count_dir_err += 1
        else:
            count_fn += 1
            
    count_fp = len(system_events) - len(matched_sys)

    # 6. Reporte Final
    print("\n" + "="*50)
    print("EVALUACIÓN DE EFICIENCIA TRIGONOMÉTRICA (Final)")
    print("="*50)
    print(f"Total Eventos Reales (GT):  {len(gt_events)}")
    print(f"Total Eventos Simulados:    {len(system_events)}")
    print("-" * 50)
    print(f"Verdaderos Positivos (TP):  {count_tp}")
    print(f"Falsos Positivos (Fantasmas): {count_fp}")
    print(f"Falsos Negativos (Omisiones): {count_fn}")
    print(f"Errores de Dirección:        {count_dir_err}")
    print("-" * 50)
    
    precision = count_tp / (count_tp + count_fp) if (count_tp + count_fp) > 0 else 0
    recall = count_tp / (count_tp + count_fn) if (count_tp + count_fn) > 0 else 0
    
    print(f"PRECISIÓN DEL CONTEO:       {precision:.4f}")
    print(f"RECALL DEL CONTEO:          {recall:.4f}")
    print("="*50)

if __name__ == "__main__":
    main()
