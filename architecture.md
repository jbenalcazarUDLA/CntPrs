# Arquitectura del Sistema - TITA People Counter

Este documento describe la arquitectura técnica del sistema, el flujo de datos desde la captura de video hasta el usuario final, y detalla todos los módulos y submódulos utilizados.

## 1. Diagrama de Bloques (Flujo de Datos)

El siguiente diagrama en formato Mermaid ilustra cómo fluyen los datos a través del sistema, separando las responsabilidades de captura, procesamiento asíncrono, almacenamiento y la interfaz de usuario.

```mermaid
graph TD
    %% Estilos
    classDef frontend fill:#3b82f6,stroke:#1d4ed8,stroke-width:2px,color:#fff;
    classDef backend fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff;
    classDef async fill:#f59e0b,stroke:#b45309,stroke-width:2px,color:#fff;
    classDef data fill:#8b5cf6,stroke:#5b21b6,stroke-width:2px,color:#fff;
    classDef source fill:#64748b,stroke:#334155,stroke-width:2px,color:#fff;

    %% Fuentes
    subgraph Fuentes de Video
        C1[Cámara RTSP]:::source
        C2[Video Local VOD]:::source
    end

    %% Procesamiento Asíncrono (Machine Learning)
    subgraph Procesamiento Inteligente Asíncrono
        AY[Async YOLO Worker<br/>Multiprocessing Manager]:::async
        DET[Módulo Detection<br/>YOLOv11 + ByteTrack]:::async
        TR[Módulo Tripwire<br/>Lógica de Cruce y Conteo]:::async
    end

    %% Backend Servidor
    subgraph Backend FastAPI
        VR[Video Reader<br/>Captura de Frames OpenCV]:::backend
        API_S[Stream API<br/>Distribución de Video en Vivo]:::backend
        API_A[Analytics API<br/>Consulta de Métricas]:::backend
        API_I[Ingestion & Config API<br/>Gestión de Cámaras y Tareas]:::backend
        SCH[APScheduler<br/>Procesos en Segundo Plano]:::backend
    end

    %% Capa de Datos
    subgraph Almacenamiento Persistente
        CRUD[Capa CRUD / SQLAlchemy<br/>Modelos Lógicos]:::data
        DB[(Base de Datos SQLite<br/>people_counter.db)]:::data
    end

    %% Frontend
    subgraph Cliente Final
        UI[Dashboard Interactivo<br/>Web Browser]:::frontend
    end

    %% Relaciones / Flujo de Datos
    C1 -->|RTSP Stream| VR
    C2 -->|Archivo Local| VR

    VR -->|Envío Frame Crudo (Cola HTTP)| AY
    AY -->|Inferencia y Tracking| DET
    DET -->|Coordenadas Bounding Boxes| TR
    TR -->|Datos de Detección| AY
    AY -->|Devuelve Frame Anotado| VR

    VR -->|Transmisión HTTP Chunked| API_S
    API_S -->|Visualización de Video| UI

    TR -.->|Eventos en Memoria| SCH
    SCH -->|Guardado Periódico| CRUD
    CRUD <-->|Lectura / Escritura| DB

    API_A <-->|Consulta ORM| CRUD
    API_I <-->|Modificación ORM| CRUD

    UI <-->|Peticiones REST (JSON)| API_A
    UI <-->|Peticiones REST (JSON)| API_I
```

---

## 2. Descripción de Componentes y Módulos

El sistema está dividido en varias capas independientes para garantizar un alto rendimiento, especialmente en hardware limitado (CPU sin GPU dedicada).

### 2.1. Fuentes de Video (`Fuentes`)
- **Cámara RTSP / Video VOD:** El sistema es capaz de ingerir video en tiempo real desde cámaras IP de seguridad (protocolo RTSP) o procesar archivos de video locales (VOD).

### 2.2. Backend (FastAPI Core)
El backend actúa como el núcleo orquestador, recibiendo peticiones del usuario y administrando los flujos de video.
- **Video Reader (`services/video_reader.py`):** Encargado de capturar y decodificar los fotogramas (frames) de los videos mediante OpenCV/FFmpeg. Extrae la información visual a la máxima velocidad posible sin bloquearse.
- **Stream API (`api/stream.py`):** Genera la respuesta HTTP Chunked (Multipart) que envía constantemente fragmentos de imágenes JPEG al navegador web para crear el efecto de streaming en vivo sin latencia perceptible.
- **Analytics API (`api/analytics.py`):** Expone endpoints (Rutas REST) para que el Dashboard consulte estadísticas de conteo (ingresos, salidas) filtradas por fecha o cámara.
- **Ingestion & Config API (`api/ingestion.py` / `api/schedule.py` / `api/tripwire.py`):** Gestionan la configuración del sistema: dar de alta nuevas cámaras, definir horarios de funcionamiento, y establecer puntos (líneas) de cruce virtual.
- **APScheduler (`scheduler.py`):** Un programador de tareas en segundo plano que consolida los conteos en memoria y los empuja a la base de datos periódicamente, previniendo cuellos de botella de escritura constante.

### 2.3. Procesamiento Asíncrono (Capa de Inteligencia Artificial)
Para evitar que la interfaz y el video se queden "congelados" esperando a la IA, toda la carga matemática se aisló en núcleos separados.
- **Async YOLO Worker (`services/async_yolo.py`):** Administrador de multiprocesamiento. Arranca procesos de Python totalmente independientes que habitan en su propio hilo de CPU. Recibe frames y devuelve coordenadas sin bloquear la lectura de video.
- **Módulo Detection (`services/detection.py`):** Contiene la lógica pesada de Visión Computacional. Utiliza el modelo ultraligero **YOLOv11** para detectar personas y el algoritmo **ByteTrack** para mantener la identidad de las personas de frame a frame.
- **Módulo Tripwire (`api/tripwire.py` / Lógica interna):** Toma las cajas de detección dibujadas por ByteTrack y analiza la intersección matemática con una o varias líneas virtuales para dictaminar si una persona ha "Entrado" o "Salido".

### 2.4. Almacenamiento (`Database`)
- **CRUD & SQLAlchemy (`crud.py`, `models.py`, `schemas.py`):** Capa de traducción entre la lógica del programa y la base de datos.
- **SQLite Database (`people_counter.db`):** Base de datos ligera y portátil que almacena las configuraciones históricas de cámaras, los horarios programados y las series de tiempo del conteo de personas.

### 2.5. Frontend (`Cliente Final`)
- **Dashboard Interactivo (`static/index.html` + JS/CSS):** Interfaz Web (SPA) altamente optimizada de aspecto SaaS y Business Intelligence. Permite al usuario final agregar cámaras, trazar las líneas de conteo sobre la imagen, visualizar el stream asíncrono y revisar paneles de control y métricas sin instalación previa de software.
