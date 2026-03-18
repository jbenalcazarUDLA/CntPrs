# Especificación del Módulo de Preprocesamiento y Procesamiento

Este documento detalla la arquitectura y lógica interna del motor de visión por computador y análisis de video del sistema estructurado en el backend. El enfoque principal del módulo es lograr un alto rendimiento en hardware de CPU sin requerir procesamiento acelerado por GPU (tarjeta gráfica dedicada).

## 1. Módulo de Preprocesamiento y Captura

El preprocesamiento inicia en el consumo de la fuente de video (cámaras IP vía RTSP o archivos VOD locales). Las responsabilidades clave son:

- **Asincronismo Fuerte:** La extracción de cuadros corre independientemente del proceso de inferencia. Los fotogramas capturados se delegan a un proceso separado (`Async YOLO Worker`) habilitado mediante el módulo `multiprocessing`. Esto asegura que el stream de video transmitido al portal de usuario fluya de manera fluida y sin bloqueos (HTTP chunked multipart).
- **Decodificación de Flujo RTSP Eficiente:** Permite la ingesta de video utilizando banderas especializadas de FFmpeg (como `rtsp_transport;tcp|fflags;nobuffer|flags;low_delay`) para anular colas de buffering predeterminadas que causarían altas latencias en transmisiones en vivo.
- **Muestreo Condicionado (Frame Skipping):** El sistema captura cuadros a la cadencia natural de la cámara, pero la tubería algorítmica de IA salta cuadros de manera premeditada (ej: procesando un cuadro de cada `5`). Esta técnica reduce drásticamente los requerimientos computacionales.

## 2. Modelo de Visión por Computador

El núcleo de la inteligencia artificial reside en el servicio encapsulado por `YoloDetector` (`backend/services/detection.py`).

### 2.1. Detección de Objetos con YOLOv11
- **Modelo Ultraligero:** Emplea el modelo más liviano de la última iteración de Ultralytics: `YOLO11n` (Nano).
- **Optimización de Exportación ONNX:** Proactivamente, el modelo en formato estándar de PyTorch (`.pt`) es exportado a formato binario ONNX (`.onnx`). El runtime de ONNX le proporciona al CPU una velocidad de inferencia notablemente más rápida frente a la retención en tensores nativos de PyTorch.
- **Reducción de Escala Dimensional:** La fase de análisis se realiza escalando la imagen internamente y de forma dinámica a `320x320` píxeles, un decremento estratégico frente a los estándares de redes neuronales convencionales. Alimenta la red convolucional con detalles suficientes para lograr el discernimiento del cuerpo humano bajando en un 70% la carga sobre los registros de cálculo.
- **Sesgo de Clase:** Todos los objetos irrelevantes en la transmisión se excluyen; la lógica restringe las Bounding Boxes generadas a la lista preestablecida de clases ID que corresponden exclusivamente a la clase `0` del conjunto de datos COCO (Personas). Adicionalmente, se cuenta con un umbral de confianza mínimo (`0.40`).

### 2.2. Rastreo Persistente de Identidades (ByteTrack)
El seguimiento multiobjeto continuo se delega al rastreador de muy alta velocidad **ByteTrack** acoplado como motor detrás del YOLO.
- Preserva invariante la identidad (`ID`) de las personas saltando fotogramas no procesados. Predice el movimiento en áreas ciegas utilizando el modelado cinemático para retener a los individuos.
- De cada persona numerada se consolida en memoria un registro continuo (historial) del centro de masa de su Bounding Box (`cx`, `cy`) calculando el progreso del cuerpo a lo largo de hasta un máximo de los últimos 30 cuadros en movimiento.

## 3. Lógica de Conteo Basado en Zonas (Líneas Virtuales)

Los incrementos en los totalizadores de entradas/salidas se derivan de la aplicación de puras operaciones de geometría lineal evitando el consumo requerido por segmentaciones de caja más pesadas.

### 3.1. Definición y Construcción de la Línea Virtual
- En el frontend, el usuario traza una línea. Esta se almacena relacionalmente con puntos normalizados entre un rango de 0 y 1 (`x1, y1` y `x2, y2`) para asegurar tolerancia multi-resolución de cada origen de video.
- Al cargar el marco de video, estas coordenadas se reproyectan dimensionándolas al ancho y alto absoluto origal en píxeles.
- Posee una dirección lógica asociada (ej. el vector que rige para la flecha `IN`).

### 3.2. Reglas de Transgresión e Intersección Vectorial
Por cada fotograma que llega, el sistema evalúa a las personas indexadas: saca a la persona objetivo del historial de rastreo, extrayendo su punto posicional anterior del centroide $P_{prev}$ y la siguiente/actual posición del centroide $P_{curr}$.

1. **Restricción de Normalidad del Vector:** El sistema valida la magnitud de desplazamiento entre $P_{prev}$ y $P_{curr}$ forzando a que la distancia sea menor al 33% transversal del rango en pantalla para descartar saltos súbitos de error o bucles de VOD locales.
2. **Determinación del Segmento Cortado:** Aplica un algoritmo de comparación rotacional (Counter-Clockwise - `CCW`) de determinantes que valida estrictamente que la trayectoria recta delimitada por $P_{prev}$ y $P_{curr}$ intercepta matemáticamente en medio del segmento transversal dibujado de la línea matriz $A$ y $B$. 
3. **Resolución del Sentido con Producto Cruz:**
   - La red localiza en cué plano euclidiano está apoyado el humano iterando una ecuación en la recta: \
     $\text{Dirección} = (dx \times (P_y - A_y)) - (dy \times (P_x - A_x))$
   - Al calcular el sentido que arroja el paso ($> 0$ o $< 0$) del humano en $P_{prev}$ transicionando hacia el nuevo sentido final en $P_{curr}$, el algoritmo concluye inequívocamente el sentido del cruce en esa barrera.
4. **Agregación Lógica e ID Unicidad:**
   - Si el tránsito topológico se alinea de manera equivalente al sentido asignado como dirección `IN`, sube el conteo primario de **Entradas**. Si es negativo contra la flecha `IN`, sube las **Salidas**.
   - Con cada sumatoria, el `ID` analizado del humano se guarda inherentemente en un conjunto transaccional dinámico llamado "IDs Contabilizados" (`counted_ids`). Este blindaje final se cerciora de proteger los medidores globales garantizando que las personas no puedan alterar los contadores de forma múltiple al situarse indecisos justo sobre la frontera de la línea.
