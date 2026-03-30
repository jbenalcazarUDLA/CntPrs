El módulo de Inferencia constituye el "cerebro" analítico del sistema. Está diseñado no solo para hallar personas en una imagen estática, sino para comprender la continuidad del tiempo (tracking) garantizando que un mismo individuo detectado en cien cuadros consecutivos sea contabilizado como "un único ente temporal" con un ID exclusivo.

El núcleo de esta lógica asícrona y persistente reside en `backend/services/detection.py`. A continuación, se detalla su implementación técnica:

### 1. Despliegue y Optimización Extrema del Modelo (ONNX)
Para cumplir con requisitos de eficiencia (evitando dependencias forzadas de GPUs costosas), la red neuronal convolucional principal es **YOLOv11 Nano**. 

En lieu de ejecutar el formato tradicional de PyTorch (`.pt`) en tiempo real, el sistema intenta de forma inteligente utilizar **ONNX (Open Neural Network Exchange)**. Si el archivo `.onnx` no existe en la primera ejecución, el propio código lo exporta dinámicamente y realiza un "_Warm-up_" (procesamiento simulado de una matriz de ceros) para calentar los grafos de ejecución en RAM, reduciendo el "Cold Start" al encender una cámara.

**Código Clave: Carga y Compilación (`__init__`)**
```python
# Intenta cargar ONNX si existe para inferencia ultrarrápida y bajo consumo de memoria
onnx_path = 'yolo11n.onnx'
pt_path = 'yolo11n.pt'

if os.path.exists(onnx_path):
    self.model = YOLO(onnx_path, task='detect')
else:
    self.model = YOLO(pt_path)
    # Exportar automáticamente a ONNX para despliegues CPU-Bound
    self.model.export(format='onnx', imgsz=320, dynamic=True)

# Warm-up (Compilación Graph C++)
dummy_frame = np.zeros((320, 320, 3), dtype=np.uint8)
self.model(dummy_frame, device='cpu', verbose=False)
```

### 2. Detección Exhaustiva Espacial
En `process_frame`, cada cuadro recibe un paso de evaluación convolucional enfocado. Para la detección, se fijan hiperparámetros duros:
*   `inferece_size = 640`: El tensor se reescala internamente en la IA para aumentar dramáticamente la detección en profundidad.
*   `classes = [0]`: Un filtro estricto alineado al dataset COCO, ordenando ignorar perros, carros, sillas o maletas, forzando la atención 100% sobre la clase "Persona".
*   `conf_threshold = 0.35`: Umbral estadístico para descartar objetos cuya probabilidad de ser humanos sea menor al 35%.

### 3. Tracking Constante e Identidad (ByteTrack)
Detectar personas es inútil para conteo si no sabemos quién es quién de un segundo a otro. Para ello, se integra **ByteTrack** (un algoritmo ligero de seguimiento _Object Tracking_), que resuelve asociaciones a través de los cuadros usando filtros espaciales y cruce de Mínimos Cuadrados (IoU).

La IA se invoca indicando persistencia `persist=True` y un archivo de configuración propietario `tracker=tracker_path` (apuntando a `custom_bytetrack.yaml`).

**Código Clave: Motor de Análisis (`process_frame`)**
```python
# Invocando Tracking en tiempo real 
results = self.model.track(
    frame, 
    classes=self.classes,      # Clase 0 (Personas)
    conf=self.conf_threshold,  # >35% probabilidad
    imgsz=inference_size,      # Matriz 640x640
    verbose=False,
    device='cpu',
    persist=True,              # Conservar estados temporales Frame-to-Frame
    tracker=tracker_path       # Lógica ByteTrack
)
```

### 4. Asociación Temporal e Historiograma
Cuando ByteTrack logra emparejar a un humano existente en un cuadro nuevo, devuelve un tensor asignándole un **Tracking ID `track_id`** exclusivo. Inmediatamente el código extrae este ID y calcula el baricentro ("centro de masa") humano usando sus coordenadas máximas y mínimas `[x1, y1, x2, y2]`.

Se estableció una estructura transitoria `defaultdict(list)` que memoriza la ruta caminada por esa persona ("Tracks") en los últimos 30 cuadros. 

**Código Clave: Centering e Historia Lineal**
```python
xyxys = boxes.xyxy.cpu().numpy().astype(int)
track_ids = boxes.id.int().cpu().tolist() # Mapea las IDs

for box, track_id in zip(xyxys, track_ids):
    # Centro visual de la persona
    cx = int((box[0] + box[2]) / 2)
    cy = int((box[1] + box[3]) / 2)
    
    # Asignación Lineal Transitoria
    history = self.tracks[track_id]
    history.append((cx, cy))
    
    # Garbage Collector temporal (Previene RAM leaks recortando la memoria a 30 posiciones)
    if len(history) > 30:
        history.pop(0)
```

### 5. Prevención Goteo RAM (ID Cleanup)
Para sistemas 24/7, el diccionario temporal de historias visuales de personas que ya no aparecen en la cámara se "ensucia", llenando los gigabytes. Para abordarlo, el sistema compara las IDs detectadas "este segundo" contra todas las llaves históricas del diccionario, eliminando aquellas personas que salieron de escena o dejaron de existir para limpiar la memoria permanentemente.

```python
active_ids = {tid for _, tid in new_boxes}
for track_id in list(self.tracks.keys()):
    if track_id not in active_ids: # Si el TrackingID no está hoy, ya no está en la escena
        del self.tracks[track_id]  # Limpieza de Memoria RAM
        self.counted_ids.discard(track_id)
```
