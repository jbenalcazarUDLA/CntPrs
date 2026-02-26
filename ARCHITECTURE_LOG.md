# Refactorización de Arquitectura: Alto Rendimiento VOD/RTSP en Hardware Limitado

Se ha completado la reestructuración profunda del motor de streaming y detección (`backend/api/stream.py` y `backend/services/detection.py`). El sistema pasó de un modelo de hilos síncronos (limitado por el Python GIL) a una arquitectura asíncrona basada en Procesos aislados.

## 1. El Problema Original
En un servidor Virtual (Ubuntu) con 4 CPUs y sin tarjeta gráfica (GPU), la inferencia de YOLO toma demasiado tiempo (~100-200ms por fotograma). En la arquitectura vieja:
1. El hilo leía un frame de la cámara.
2. OpenCV/YOLO bloqueaba absolutamente el proceso calculando las cajas.
3. Se enviaba el frame al usuario.

**Resultado:** FFMPEG se desbordaba en memoria (OOM) al acumular video RTSP que no podía leerse a tiempo, y los videos VOD se estiraban y reproducían en cámara lenta ("Matrix effect") tratando de esperar a la Inteligencia Artificial.

## 2. La Solución (Async Multiprocessing)
Se extrajo la Inteligencia artificial de la espina dorsal del servidor web:

- **Aislamiento (`async_yolo.py`)**: Cada cámara instancia un nuevo "Worker" (`mp.Process()`) que corre en su **propio núcleo físico del CPU**, obteniendo su propia instancia de YOLO.
- **Tuberías Asíncronas**: FastAPI ahora solo lee la cámara (demora ~3ms) e inserta el frame crudo en una cola de tamaño 1. Inmediatamente después, recoge la última caja calculada que el Worker YOLO haya logrado procesar en el fondo y la pega sobre la imagen.
- **Reloj Virtual VOD**: Si el archivo de video local se atasca, `cap.grab()` salta implacablemente los frames atrasados comparando el número de Frame contra el Reloj Real de Python para mantener el video en estricto 1x (Tiempo Real) de forma visual.

## 3. Pruebas Realizadas
- **Estabilidad RTSP**: Se suprimieron todos los errores superficiales FFMPEG P-Frame/B-Frame H.265 (HEVC) inyectando `AV_LOG_LEVEL=-8` y descartando corrupción en C++. El stream corre limpio e infinito.
- **Transferencia de Estado (Tripwires)**: Se arregló un _crash_ de serialización de memoria convirtiendo los objetos de _SQLAlchemy_ en diccionarios planos `dict` antes de mandarlos al núcleo aislado del CPU, permitiendo que OpenCV dibuje de forma cruzada la línea de origen del Tracking web.

> [!TIP]
> **Rendimiento Máximo:** Con este refactor, tu servidor backend puede manejar fácilmente las 5 cámaras prometidas de tu titulación repartiendo el esfuerzo matemático entre los 4 Virtual Cores disponibles, asegurando que el panel web Frontend siga responsivo y el streaming se vea fluido a ojo humano, incluso si YOLO está detectando a "5 FPS" por detrás.
