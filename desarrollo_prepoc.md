El desarrollo del módulo de preprocesamiento se encargó de estandarizar y optimizar los flujos de video extraídos en la etapa de ingesta antes de que sean evaluados por los modelos de Inteligencia Artificial (ej. YOLO). Estas transformaciones minimizan la variabilidad (por condiciones de luz, diferentes resoluciones de cámara, ruido) asegurando que el modelo reciba datos en el formato matemático exacto para el cual fue entrenado.

Todo el flujo se encapsuló en la clase `PreprocessingModule` dentro de `backend/preprocessing.py`.

A continuación, el detalle de las transformaciones clave implementadas:

### 1. Normalización de Resolución y Relación de Aspecto (Letterboxing)
Los modelos de IA requieren dimensiones de entrada estrictas (típicamente 640x640). Sin embargo, forzar un redimensionamiento destruye la proporción original (aspect ratio), deformando los objetos (personas, vehículos) y perjudicando la detección.
Para solucionarlo, se implementó un redimensionamiento con preservación de ratio y **Padding (Letterboxing)**, donde se añaden franjas negras a los bordes para completar los 640x640 sin distorsionar la imagen central.

**Código Clave: Resize y Padding (`_apply_resize`)**
```python
def _apply_resize(self, frame):
    target_w = self.config["resize"]["width"]
    target_h = self.config["resize"]["height"]
    
    h, w = frame.shape[:2]
    scale = min(target_w / w, target_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    
    # Redimensiona manteniendo la proporción original
    resized = cv2.resize(frame, (new_w, new_h))
    
    if not self.config["resize"]["padding"]:
        return resized
        
    # Agrega relleno (padding) para encajar en el canvas exigido (ej. 640x640)
    canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    
    # Centra la imagen redimensionada
    x_offset = (target_w - new_w) // 2
    y_offset = (target_h - new_h) // 2
    canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
    
    return canvas
```

### 2. Ajustes de Iluminación y Reducción de Ruido
Las fuentes de video varían drásticamente en exposición a la luz (mañana, noche, cámaras en sombra). Se dotó al módulo de la capacidad de compensar dinámicamente estas variaciones utilizando operaciones matemáticas sobre la matriz de píxeles:
- **Brillo y Contraste**: Ecuación lineal `alpha * image + beta`.
- **Corrección Gamma**: Mapeo no lineal usando una tabla de búsqueda (`LUT`) para aclarar sombras sin quemar las luces.
- **Reducción de ruido**: Un filtro Gaussiano ligero (`GaussianBlur`) que resulta ser computacionalmente eficiente para modalidades en tiempo real, homogeneizando artefactos o imperfecciones del propio lente.

**Código Clave: Enhancements (`_apply_enhancements`)**
```python
def _apply_enhancements(self, frame):
    cfg = self.config["enhancement"]
    
    # Brillo y Contraste
    if cfg["brightness"] != 0 or cfg["contrast"] != 1.0:
        frame = cv2.convertScaleAbs(frame, alpha=cfg["contrast"], beta=cfg["brightness"])
        
    # Corrección Gamma mediante L.U.T. (Look-Up Table) 
    if cfg["gamma"] != 1.0:
        invGamma = 1.0 / cfg["gamma"]
        table = np.array([((i / 255.0) ** invGamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        frame = cv2.LUT(frame, table)
        
    # Denoising liviano orientado a tiempo real (Real-Time)
    if cfg["denoise"]:
        frame = cv2.GaussianBlur(frame, (3, 3), 0)
        
    return frame
```

### 3. Estandarización de Formato y Tasa de Cuadros (Frame Skipping)
Para ensamblar la entrada matemática del modelo, el módulo interviene directamente sobre el tensor:
1. **Conservación Cíclica (Frame Skip)**: Descarta ciclos de frames específicos (ej. evaluar 1 de cada 3 frames) para liberar recursos de la CPU/GPU sin perder la trazabilidad de los objetos.
2. **Espacio de Color**: Transforma el espectro BGR (por defecto en OpenCV) al RGB estándar esperado por PyTorch/YOLO.
3. **Escalamiento Min-Max**: Transforma los rangos de [0, 255] a floats de [0.0, 1.0].

**Código Clave: Integración y Estandarización (`process_frame`)**
```python
def process_frame(self, frame, metadata: dict):
    # Optimización del Pipeline matemático descartando frames no necesarios
    self.frame_count += 1
    if (self.frame_count - 1) % self.config["frame_skip"] != 0:
        return None, metadata
        
    frame = self._apply_roi(frame)          # Recorte de área
    frame = self._apply_resize(frame)       # Normalización 640x640
    frame = self._apply_enhancements(frame) # Limpieza e Iluminación
    
    # Estandarización Matemática Tensorial de Formato
    if self.config["color_space"] == "RGB":
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
    if self.config["normalization"]:
        # Transforma enteros de 8-bits a Flotantes de 32-bits de 0 a 1
        frame = frame.astype(np.float32) / 255.0
        
    return frame, metadata
```

Este encapsulamiento en `backend/preprocessing.py` actúa como el motor central que neutraliza anomalías en el feed de video y entrega un bloque de memoria (tensor) impecable, que maximiza drásticamente la precisión (Precision) y exhaustividad (Recall) de las detecciones aguas abajo.
