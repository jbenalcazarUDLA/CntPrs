# Análisis de Rendimiento de YOLO y ByteTrack

## ¿Qué se ha implementado?

Dado que necesitas poder medir con números concretos dónde está fallando el sistema (si en la **detección** de personas por parte de YOLO, o si en el **tracking/seguimiento** de IDs por parte de ByteTrack), hemos creado un subsistema matemático de evaluación.

1. **[services/metrics.py](file:///home/jbenalcazar/TITA/CntPrs/backend/services/metrics.py)**: Este nuevo archivo incluye funciones puras sin side-effects que comparan listas de predicciones contra la Verdad Terreno (Ground Truth / GT).
   - `calculate_iou`: Mide la superposición geométrica de 2 cajas (Intersection over Union).
   - `evaluate_detection_frame`: Mide falsos positivos y falsos negativos visuales calculando así la **Precisión y Recall** de la red neuronal.
   - `evaluate_tracking_frame`: Mide los Mismatches (o ID Switches) calculando el famoso score **MOTA** (Multi-Object Tracking Accuracy).
2. **[evaluate.py](file:///home/jbenalcazar/TITA/CntPrs/backend/evaluate.py)**: Este es un nuevo script ejecutable en consola diseñado específicamente para evaluar el rendimiento.

## ¿Cómo utilizar la herramienta cuando tengas tu GT?

Debido a que las métricas (Precisión, Recall, MOTA) implican que se compare el resultado del modelo con un humano que haya dicho "aquí está mi verdad absoluta" (GT), debes primero anotar algunos cuantos segundos de un video usando un formato estándar MOT Challenge.

El **Formato MOT** es un archivo `.txt` donde cada línea es un objeto en cada frame:
```
<frame>, <id>, <bb_left>, <bb_top>, <bb_width>, <bb_height>, <conf>, <x>, <y>, <z>
```
*(Ejemplo de un frame: `1, 1, 136, 122, 54, 167, 1, -1, -1, -1`)*

### Para lanzar una evaluación:
Una vez que tengas tu `video.mp4`, tu archivo de anotación manual MOT `gt.txt` (y opcionalmente tu archivo de eventos de cruce `events_gt.txt`), ejecuta el script:

```bash
# Solo Visión
python backend/evaluate.py --video sample_video.mp4 --gt gt.txt --show

# Visión + Conteo Geométrico
python backend/evaluate.py --video sample.mp4 --gt gt.txt --gt-counts events_gt.txt --show
```
- La bandera `--show` renderiza el video evaluado frame a frame.
- Obtendrás en consola los resultados finales (tanto de Tracking como de Conteo) al terminar el video de prueba.

### Interpretación de Resultados:

Dependiendo de qué números obtengas en consola, el script te recomendará:
> [!CAUTION]
> - **Si MOTA es bajo y Precision de Detección es Alta**: El problema está en ByteTrack (Tracking). Los IDs se están perdiendo porque los sujetos se cruzan o la cámara está lenta (bajo FPS). Tienes que aumentar el parámetro **max_age** en tu tracker.
> - **Si MOTA es bajo y la Precisión también es Baja**: El problema lo origina YOLO (Detección). No está viendo a las personas, lo que causa en cadena que ByteTrack también pierda los IDs. Debes mejorar la resolución, cambiar de `yolo11n` a `yolo11s`, o mejorar la iluminación.
> - **Si todo es Alto pero cuenta mal**: Revisa la lógica geométrica que detecta cuándo cruzan el tripwire (línea virtual).

---
*Con esto, la base de tu análisis de Sprint 6 está completamente lista.*
