# Plan de Pruebas: Validación de Precisión del Modelo (Detección y Tracking)

## 1. Objetivo
Validar cuantitativamente la precisión del modelo YOLO (detección) y el algoritmo ByteTrack (seguimiento) para diagnosticar si las discrepancias en el conteo de entradas/salidas son causadas por fallos de detección, pérdidas de rastreo o problemas puramente geométricos en la línea virtual (Tripwire).

## 2. Herramientas Integradas
El sistema ya cuenta con la herramienta de validación necesaria:
- **Script:** `backend/evaluate.py`
- **Métricas:** Calcula Precisión, Recall, F1 Score (Detección) y MOTA, ID Switches, Misses (Tracking).
- **Formato Requerido:** Archivo de texto estructurado en formato MOT (Múltiples Objetos en Seguimiento) `[frame_id, track_id, bb_left, bb_top, bb_width, bb_height, conf, x, y, z]`.

## 3. Metodología de Pruebas (Paso a Paso)

### Fase A.1: Preparación del "Ground Truth" de Visión (Verdad Terrestre MOT)
Para automatizar la validación, el script necesita saber exactamente qué es lo correcto.
1. **Capturar Video:** Graba un clip de video representativo de 1 a 3 minutos desde el dashboard en un horario pico donde sucedan los errores de conteo más comunes.
2. **Anotar Manualmente:** Usa una herramienta como [CVAT](https://www.cvat.ai/) para etiquetar los cuadros delimitadores (bounding boxes) e IDs de las personas que cruzan durante el clip de forma manual y perfecta.
3. **Exportar:** Exporta las anotaciones en la herramienta utilizando el formato **MOT** y guárdalo como `ground_truth.txt`.

### Fase A.2: Preparación del "Ground Truth" de Conteo (Verdad Terrestre Eventos)
Para medir estrictamente el rendimiento de la Línea Virtual (Tripwire), necesitas un segundo archivo simple.
1. **Anotar Eventos:** Observa el mismo clip y anota cada vez que alguien cruza la línea en formato CSV: `frame, direccion` (donde 1 es Entrada y -1 es Salida).
2. **Exportar:** Guárdalo como `gt_counts.txt`.

Ejemplo de `gt_counts.txt`:
```csv
120, 1
250, -1
310, 1
```

### Fase B: Ejecución de la Herramienta de Evaluación
Usa el entorno virtual para lanzar el módulo de evaluación comparando tu video contra el archivo etiquetado.

```bash
cd backend
source ../venv/bin/activate
# Evaluar solo Visión/Tracking
python evaluate.py --video /ruta/al/segmento.mp4 --gt /ruta/a/ground_truth.txt --iou 0.5 --show

# Evaluar Visión/Tracking Y Conteo Estricto
python evaluate.py --video /ruta/al/segmento.mp4 --gt /ruta/a/ground_truth.txt --gt-counts /ruta/a/gt_counts.txt --show
```

### Fase C: Interpretación de Resultados Pos ejecución
Al finalizar, la consola emitirá dos bloques de resultados. Analiza los resultados según la siguiente tabla:

| Métrica | Definición Breve | Umbral Aceptable |
| :--- | :--- | :--- |
| **Precision** | De todo lo que YOLO creyó que era persona, qué % de verdad lo era. | **> 0.80** |
| **Recall** | De todas las personas reales (GT), qué % logró ver YOLO. | **> 0.80** |
| **F1 Score** | Una media armónica entre Precisón y Recall. | **> 0.80** |
| **ID Switches** | ¿Cuántas veces el sistema perdió a alguien y le reasignó un identificador nuevo? | **Lo más cercano a 0** |
| **MOTA** | Calificación global (0 a 1) penalizando todos los errores del Tracking. | **> 0.65** |
| **Counting Precision**| De los conteos que hizo el Tripwire, qué % fueron reales (no fantasmas). | **> 0.90** |
| **Counting Recall** | De todas las personas que cruzaron (GT), qué % detectó el Tripwire. | **> 0.90** |

## 4. Árbol de Diagnóstico y Toma de Acciones

Según el resumen automático que te proveerá el script `evaluate.py`, debes tomar una de estas 3 rutas de acción:

*   🔴 **Escenario 1: Fallo Severo en Detección (Precision o Recall < 0.5)**
    *   **Problema:** YOLO no puede "ver" a las personas consistentemente. Se mezclan con el fondo o tienen ángulos muy pronunciados.
    *   **Acción:** Es necesario realizar Fine-Tuning (entrenar el modelo base `yolo11n.pt` añadiendo tus propias imágenes del CCTV).

*   🟡 **Escenario 2: Fallo en Rastreo (MOTA < 0.5 y alto número de ID Switches)**
    *   **Problema:** YOLO sí detecta a las personas de forma aceptable, pero ByteTrack pierde sus registros entre fotogramas. Debido a esto, una misma persona se cuenta 2 veces o desaparece antes de tocar la línea de salida.
    *   **Acción:** Ajustar los parámetros de `backend/custom_bytetrack.yaml` (Ej: Incrementar la memoria `track_buffer`), o aumentar drásticamente el flujo de Fotogramas por Segundo (FPS) enviados al script.

*   🟢 **Escenario 3: Funcionamiento Óptimo de Visión pero Fallo en Conteo**
    *   **Problema:** La inteligencia artificial está realizando su trabajo perfecto (MOTA/Recall > 0.80), pero las métricas de `Counting Precision` o `Counting Recall` son bajas.
    *   **Acción:** Revisar estrictamente la lógica de la Línea Virtual (Tripwire). Redibujar la línea en el dashboard o revisar la función geométrica de cruce en `detection.py`.
