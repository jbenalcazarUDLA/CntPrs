import cv2
import argparse

def main():
    parser = argparse.ArgumentParser(description="Visor de Fotogramas para Anotación de Video")
    parser.add_argument('--video', type=str, required=True, help="Ruta al archivo de video .mp4")
    parser.add_argument('--tw', type=str, required=False, help="Coordenadas del Tripwire: x1,y1,x2,y2,DIR", default="")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"Error: No se pudo abrir el video {args.video}")
        return
        
    original_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    original_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    tw_data = None
    if args.tw:
        try:
            parts = args.tw.split(',')
            tw_data = {
                'x1': int(float(parts[0]) * original_w),
                'y1': int(float(parts[1]) * original_h),
                'x2': int(float(parts[2]) * original_w),
                'y2': int(float(parts[3]) * original_h),
                'dir': parts[4].upper() if len(parts) > 4 else 'IN'
            }
        except Exception as e:
            print(f"Error parseando tripwire: {e}")

    frame_idx = 0
    paused = False
    ret, frame = cap.read()

    print("\n--- CONTROLES DEL VISOR ---")
    print("[ESPACIO] : Pausar / Reproducir")
    print("[ D ]     : Avanzar un fotograma (solo cuando está pausado)")
    print("[ Q ]     : Salir")
    print("---------------------------\n")

    while ret:
        display_frame = frame.copy()
        
        # Dibujar HUD (Texto en pantalla)
        cv2.putText(display_frame, f"FRAME: {frame_idx}", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 4)
        
        # Dibujar la línea de Tripwire
        if tw_data:
            cv2.line(display_frame, (tw_data['x1'], tw_data['y1']), (tw_data['x2'], tw_data['y2']), (0, 255, 255), 3)
            cv2.putText(display_frame, f"LINEA ({tw_data['dir']})", (tw_data['x1'], tw_data['y1'] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        status = "PAUSADO" if paused else "REPRODUCIENDO"
        color = (0, 0, 255) if paused else (0, 255, 0)
        cv2.putText(display_frame, f"ESTADO: {status}", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.putText(display_frame, "Espacio: Pausa | D: Frame sig. | Q: Salir", (30, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        cv2.imshow("Validador de Fotogramas (Ground Truth)", display_frame)

        # Esperar tecla: si está pausado espera infinitamente (0), si no, espera 30ms (~30 FPS)
        key = cv2.waitKey(0 if paused else 30) & 0xFF

        if key == ord('q'):
            break
        elif key == ord(' '):
            paused = not paused
        elif key == ord('d') and paused:
            # Avanzar manualmente 1 frame mientras está pausado
            ret, frame = cap.read()
            if ret:
                frame_idx += 1
        elif not paused:
            # Reproducción normal continua
            ret, frame = cap.read()
            if ret:
                frame_idx += 1

    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
