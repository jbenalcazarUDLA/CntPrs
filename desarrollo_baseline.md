# Baseline de Inferencias (Primeras Detecciones de IA)

El módulo de **Baseline** representa la primera versión fundacional del sistema y sirve como punto de referencia arquitectónico. Este hito corresponde a la etapa del desarrollo donde la plataforma logró realizar con éxito sus primeras inferencias apoyadas enteramente por un modelo de Inteligencia Artificial (Visión Computacional), antes de incorporar optimizaciones extremas o algoritmos complejos de rastreo temporal.

## 1. Contexto del Baseline

En su estado fundamental, el objetivo de esta etapa era certificar la viabilidad técnica: conectar un flujo de video en vivo (o almacenado) con un modelo neuronal profundo (Deep Learning), extraer el análisis y devolver cajas delimitadoras para seres humanos sobre la imagen.

Las características técnicas de este estado inicial contemplaron:
- **Modelo Pre-entrenado:** Uso directo de pesos estándar de YOLO (formato embebido nativo `.pt`) cargados directamente en el entorno de backend.
- **Ejecución Síncrona Estricta:** El bucle (loop) del programa consumía el fotograma, ejecutaba la inferencia neuronal y renderizaba el resultado en un hilo único y secuencial. El siguiente *frame* no se procesaba hasta que la IA terminara con el microscopio del actual.
- **Detección por Cuadro (Frame-by-Frame):** El análisis era amnésico. La IA encontraba dónde estaba una persona en el cuadro número 1, pero si la persona daba un paso y aparecía en el cuadro 2, el sistema la evaluaba como una entidad matemática completamente nueva. No existía la persistencia.

## 2. Inferencia Temprana (Código Base)

Durante esta fase, el esfuerzo se centró en aplicar los primeros filtros algorítmicos al modelo (`classes=[0]` y umbrales de confianza) para ignorar animales o mobiliario, enfocando el tensor exclusivamente sobre el cuerpo humano.

**Lógica Representativa del Baseline:**
```python
from ultralytics import YOLO
import cv2

# 1. Carga ingenua y pesada del modelo 
model = YOLO('yolo11n.pt')

cap = cv2.VideoCapture('stream.mp4')

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break
    
    # 2. Inferencia estática (bloqueando el hilo principal)
    results = model(
        frame, 
        classes=[0],     # Solo detectar 'Personas'
        conf=0.35        # Umbral probabilístico mínimo
    )
    
    # 3. Representación Gráfica Simple
    for result in results:
        boxes = result.boxes
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
```

## 3. Limitaciones del Baseline (El Catalizador de Evolución)

Si bien este Baseline validó la prueba de concepto, exhibió comportamientos de cuellos de botella ("Bottlenecks") que justificaron toda la evolución posterior del ecosistema al nivel industrial actual:

*   **Rendimiento y Bloqueo de I/O:** Extraer y decodificar frames en el mismo plano de memoria que la red neuronal generaba caídas graves en los *Frames Per Second* (FPS), saturando el núcleo único asignado.
*   **Imposibilidad de Conteo Real:** Sin la retención en memoria temporal de la persona entre frame y frame (lo que hoy hacen las IDs), una persona podía generar 100 detecciones al caminar por un pasillo, arrojando conteos infinitos en lugar de ser interpretada como un transeúnte solitario.
*   **Lentitud Térmica:** La falta de serialización matemática forzaba tiempos masivos de "Cold Start" al levantar la plataforma.

### De Baseline a Producción
Este documento avala el salto algorítmico logrado. Superando esta etapa base, el ecosistema maduró implementando **Motores ONNX** para compilación rápida de los grafos C++, **ByteTrack** para memorización espacial, y tuberías **Multiproceso** de ingesta asíncrona, dejando la limitación estática en el pasado.
