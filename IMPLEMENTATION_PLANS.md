# Arquitectura de Solución IA (Procesamiento de Video en Tiempo Real)

Dado el contexto del proyecto de titulación (Máximo 10 streams simultáneos, concurrencia de usuarios mínima), la estrategia arquitectónica **NO** debe enfocarse en la elasticidad web horizontal (Docker/Kubernetes no mejorará el rendimiento FPS del modelo, solo añadirá latencia de red y sobrecarga de virtualización RAM a nivel local).

Como Arquitecto de Soluciones de IA, mi diagnóstico es que el "cuello de botella" es el **procesamiento (Inferencia YOLO + Tracking pesado)** y el **Lock Global de Python (GIL)**. Para soportar 10 cámaras simultáneas a buenos FPS en un solo servidor de inferencia sin que "la funcionalidad falle" (lag, frame-drops severos, congelamiento), necesitamos aislar los cálculos matemáticos del servidor web.

## 1. El Problema Actual (Monolito Sincrono)
Actualmente: `Web Request` -> `cap.read()` -> `YOLO` -> `Web Response`.
Esto obliga a FastAPI/Uvicorn a esperar que el modelo (que usa 100% de 1 core de CPU/GPU por stream) termine, lo que destruye el rendimiento y genera saltos en el video.

## 2. Nueva Arquitectura Propuesta (High-Performance Inference Pipeline)

Mantendremos tu excelente interfaz actual. El refactoring ocurrirá *debajo del capó*:

### Capa 1: Ingestión (Hilos Ligeros)
- Las cámaras se leerán en hilos (`threading`) dedicados **solo a ingestar frames** y depositarlos en una cola (Queue) con tamaño máximo de 1 (para siempre tener el frame más nuevo y tirar los viejos si hay retraso).

### Capa 2: Motor de Inferencia (Multiprocessing en vez de Docker)
- **Aislamiento por Procesos**: En lugar de Docker, usaremos el módulo `multiprocessing` de Python. Crearemos `Workers` independientes para YOLO+Tracking.
- Cada cámara enviará su frame nuevo a un `Worker` que corre en **su propio núcleo de CPU (Core)**. Al saltarnos el "Global Interpreter Lock" (GIL) de Python real, podemos exprimir el hardware al 100% para las 5-10 cámaras.

### Capa 3: Tracking de Alta Eficiencia (DeepSORT / ByteTrack)
- El tracking no tolerará caídas de frames. Añadiremos un tracker ligero y poderoso (ByteTrack o un módulo SORT optimizado) acoplado directamente a la inferencia de YOLO en el Worker aislado.

### Capa 4: Servidor de Streaming (FastAPI / Asíncrono)
- El servidor web solo tomará las cajas delimitadoras resultantes y el frame más fresco, y los despachará por MJPEG al Frontend instantáneamente, separando el FPS del video del FPS de la inferencia.

> [!TIP]
> **Beneficio clave:** El video en el frontend fluirá natural (ej. 30 FPS constantes), mientras la "IA" calcula por detrás (ej. analizando 5-10 veces por segundo de forma imperceptible).
>
> **Rechazo a Docker:** Para este caso de 1 solo servidor y 10 cámaras, Docker reduciría tu rendimiento general un ~10% por la capa de red del proxy y no acelerará en absoluto a YOLO.
> 
> **Decisión:** Enfocar el "refactoring" en la creación de un motor Multi-Proceso de Python para el Backend y dejar la UI y el entorno tal como están.

---

# Análisis de Modelos de Tracking para Sprint 5 (Conteo Bidireccional por Tripwire)

Para implementar la funcionalidad principal del sistema SCAP (Conteo de Personas que Entran y Salen cruzando una línea virtual plana), la elección del algoritmo de Tracking (Seguimiento temporal) es la decisión de diseño más crítica, ya que definirá si el sistema sobrevive en nuestro entorno de hardware limitado (VM con 4 Core CPUs, 0 GPUs).

## 1. Evaluación de Candidatos

### Candidato A: DeepSORT (Simple Online and Realtime Tracking with a Deep Association Metric)
Es el estándar de la industria tradicional. Utiliza el Filtro de Kalman para predecir trayectorias (Matemática pura) **PERO** añade un segundo modelo de Inteligencia Artificial ("Re-ID" - Reidentificación) que extrae las características visuales (ropa, colores) de cada persona recortada para asociarlas.
*   **Pro:** Extremadamente resistente a oclusiones (si alguien cruza frente a otra persona y la tapa, la recuerda por su "ropa" cuando reaparece).
*   **Contra (Crítico para este proyecto):** Requiere ejecutar una segunda Red Neuronal por *cada persona detectada* en *cada cuadro*. En un entorno 100% CPU, la sobrecarga computacional destruirá los FPS que ganamos en el Sprint anterior.

### Candidato B: ByteTrack (Multi-Object Tracking by Associating Every Detection Box)
Algoritmo de nueva generación (SOTA). Utiliza pura matemática predictiva (Kalman Filter + Intersección sobre Unión - IoU). La verdadera innovación es que recicla las "detecciones de baja confianza" de YOLO que normalmente se descartan, usándolas para mantener viva la trayectoria de alguien que se está ocultando, *sin usar un segundo modelo de IA pesada*.
*   **Pro (Crítico para este proyecto):** Rendimiento absurdamente eficiente y veloz. Puesto que no usa reconocimiento de píxeles (Re-ID), su coste computacional es casi cero, consistente en operaciones de álgebra lineal que los procesadores modernos resuelven instantáneamente. Es el rey indiscutible para despliegues Edge / CPU.
*   **Contra:** En multitudes aglomeradas donde todos visten igual y caminan muy pegados cruzando sus cuerpos de frente por periodos largos, puede sufrir cambios de ID ("ID Switches"). Sin embargo, para cámaras de ingreso general (picada / vista superior angular), esto casi nunca es un problema crítico.

### Candidato C: Tracker Interno de Ultralytics YOLO (`persist=True`)
Ultralytics V8/V11 trae wrappers incorporados tanto para BOT-SORT (muy pesado) como para ByteTrack de manera nativa.
*   **Pro:** Cero desarrollo de integración. Basta con ejecutar `model.track(..., persist=True, tracker="bytetrack.yaml")`.
*   **Contra:** Oculta gran parte del control matemático que podríamos necesitar para depurar fallos en el triplwire puro.

## 2. Veredicto y Propuesta Arquitectónica

> [!IMPORTANT]
> **Veredicto:** El único candidato lógica y algorítmicamente viable para un servidor de **4 núcleos lógicos sin GPU** que pretende correr múltiples cámaras es **ByteTrack**. 

Lanzar modelos Re-ID secundarios (DeepSORT) ahogará la CPU e inducirá un "efecto botella". ByteTrack entregará métricas precisas a un costo de CPU milimétrico.

### Estrategia de Tripline (Conteo Direccional)
Para el evento de "Entrar/Salir":
1. YOLO asigna un `ID` único usando ByteTrack.
2. Cada proceso guardará el historial geométrico de la persona `[ (x_ayer, y_ayer), (x_hoy, y_hoy) ]`.
3. Utilizaremos el **Producto Cruz (Cross Product)** de vectores algebraicos para determinar con exactitud quirúrgica si la línea histórica del individuo cruzó (intersectó) la línea virtual paramétrica del Tripwire (x1, y1 a x2, y2).
4. El signo del Producto Cruz nos dictará automáticamente la **Direccionalidad** (Adelante = Entrada, Atrás = Salida).

## 3. Plan de Implementación (Sprint 5)
1. Reemplazar la llamada estéril `model(frame)` en `backend/services/detection.py` por el motor de tracking oficial `model.track(..., tracker="bytetrack.yaml")`.
2. Crear clase utilitaria/matemática para guardar las trayectorias de los últimos N frames por ID de persona y evaluar la intersección de líneas.
3. Actualizar la base de datos de eventos (Ingresos/Salidas).
