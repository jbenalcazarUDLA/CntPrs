# Definición del Módulo de Almacenamiento

El módulo de almacenamiento del sistema está basado en una base de datos relacional (gestionada a través de SQLAlchemy y SQLite en `people_counter.db`). Está diseñado para gestionar la información de las fuentes de video, su configuración de procesamiento (líneas de cruce y horarios) y, fundamentalmente, el registro de métricas y eventos (conteos de entradas y salidas) a lo largo del tiempo.

A continuación, se detalla la estructura principal de la base de datos:

## Entidades y Tablas

### 1. Fuentes de Video (`video_sources`)
Almacena la configuración de las cámaras o archivos de video que el sistema procesará.
- **Campos principales:**
  - `id`: Identificador único.
  - `name`: Nombre descriptivo de la fuente.
  - `type`: Tipo de fuente (`'file'` para archivos de video locales, `'rtsp'` para flujos en vivo).
  - `path_url`: Ruta del archivo local o URL RTSP de la cámara.
  - `created_at`: Fecha y hora de registro.

### 2. Líneas de Cruce (`tripwires`)
Define la coordenada y configuración de la línea virtual (tripwire) utilizada para el conteo de objetos/personas en una fuente de video específica.
- **Relación:** 1 a 1 con `video_sources` (`source_id` único).
- **Campos principales:**
  - `id`: Identificador único.
  - `source_id`: Referencia a la fuente de video.
  - `x1, y1, x2, y2`: Coordenadas de los extremos de la línea virtual en el video.
  - `direction`: Dirección principal de la línea (`'IN'` o `'OUT'`) que define el sentido de cruce.
  - `updated_at`: Fecha y hora de la última modificación.

### 3. Horarios de Cámara (`camera_schedules`)
Establece los horarios y días operativos en los cuales una fuente de tipo RTSP debe ser procesada y sus métricas registradas.
- **Relación:** 1 a 1 con `video_sources` (`source_id` único).
- **Campos principales:**
  - `id`: Identificador único.
  - `source_id`: Referencia a la fuente de video.
  - `monday` a `sunday`: Banderas booleanas (verdadero/falso) que indican si la cámara debe grabar/capturar en esos días de la semana.
  - `start_time` / `end_time`: Rango horario diario establecido para la captura de eventos (ej: `08:00` a `18:00`).
  - `is_active`: Estado general del horario (activado/desactivado).

### 4. Histórico de Conteo (`historico_conteo`)
Tabla núcleo para el módulo de almacenamiento de métricas y registro de eventos (in/out). Almacena de manera acumulativa y estructurada el total de entradas y salidas capturadas por una fuente de video en una ventana de tiempo o sesión ("apertura" y "cierre").
- **Relación:** Muchos a 1 con `video_sources` (`source_id` no único, una fuente tiene múltiples registros históricos).
- **Campos principales:**
  - `id`: Identificador único del registro.
  - `source_id`: Referencia a la fuente de video que generó la métrica.
  - `fecha_registro`: Fecha en la que tuvo lugar la captura (ej: "2026-03-18").
  - `hora_apertura`: Hora de inicio del período de conteo.
  - `hora_cierre`: Hora de finalización del período de conteo (corte del scheduler o término del procesamiento).
  - `total_in`: Contador total de entradas detectadas (eventos tipo 'in').
  - `total_out`: Contador total de salidas detectadas (eventos tipo 'out').

## Método de Almacenamiento de Datos

El sistema implementa un enfoque de sincronización continua que asegura tener siempre el dato más reciente, evitando la pérdida de información ante cortes o cierres inesperados:

1. **Sincronización en Tiempo Real (Por Modificación):** Durante el procesamiento, el sistema actualiza de forma inmediata la base de datos (en la tabla `historico_conteo`) **cada vez que el modelo detecta y contabiliza un cambio** (una nueva entrada o salida). La `hora_cierre` de ese registro asienta la hora exacta de esta última modificación en tiempo real.
2. **Cierre del Histórico (Fin de Jornada o Ciclo):** De presentarse la hora definida para apagarse del `camera_schedules.end_time`, o si se interrumpe manualmente el video/sistema, se ejecuta también una liquidación final. Esta operación asegura que los contadores definitivos del día / sesión queden asentados al terminar la transmisión, complementando el mecanismo de tiempo real.

## Descripción del Modelo Entidad-Relación (ER)

El esquema de la base de datos se articula en torno a la entidad central `video_sources`, que representa a la cámara o flujo de video, a la cual se le asocian configuraciones y de la cual derivan los registros de conteo. Sus relaciones se detallan a continuación:

*   **R1: `video_sources` ↔ `tripwires` (Relación 1 a 1)**
    *   **Lógica:** Una fuente de video (*Source*) cuenta con exactamente una configuración de cruce virtual (*Tripwire*). A su vez, dicha línea de cruce solo le pertenece a una fuente. En la tabla se fuerza esta relación mediante un Foreign Key `source_id` declarado como único (`unique=True`).
*   **R2: `video_sources` ↔ `camera_schedules` (Relación 1 a 1)**
    *   **Lógica:** De manera idéntica a la configuración del tripwire, cada cámara o flujo tiene reservado un único itinerario de horarios de encendido/apagado (*Schedule*) que gestiona qué días y horas está activo el registro de su video.
*   **R3: `video_sources` ↔ `historico_conteo` (Relación 1 a N / Uno a Muchos)**
    *   **Lógica:** Por cada cámara del sistema (`video_sources`), se generan en el tiempo **múltiples registros históricos** (`historico_conteo`). Al final de cada jornada o sesión planificada en la que estuvo operando una cámara, se genera o actualiza una nueva fila que engloba permanentemente cuántas entradas y salidas hubo en ese rango documentado (`hora_apertura` a `hora_cierre`).

---

El diagrama ER de esta base de datos se ha generado y guardado en formato genérico de Mermaid en el archivo `diagrama_bd.mmd`.
