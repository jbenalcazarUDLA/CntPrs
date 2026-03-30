El módulo de Conteo recibe el resultado analítico bruto de la etapa de Inferencia y Tripwire (donde se cruzan polígonos) y lo transforma en registros estructurados, métricas de retención, y KPIs transaccionales consultables.

Es el corazón del Business Intelligence del proyecto, diseñado para operar tanto en tiempo real (sobre memoria) como de manera histórica agrupada.

A continuación el detalle de su desarrollo e implementación:

### 1. Extracción de Contadores en Tiempo Real (Memory-Safe)
Debido a que YOLO y ByteTrack monopolizan el procesamiento, el conteo en tiempo real no puede bloquear el servidor web (FastAPI). Por lo tanto, en `backend/services/async_yolo.py`, el recuento se maneja de forma segura entre núcleos de CPU utilizando `multiprocessing.Value`.

El proceso "Worker" actualiza las direcciones (Entrada `total_in` y Salida `total_out`) atómicamente, permitiendo que la interfaz gráfica obtenga los números actualizados instantáneamente sin requerir consultas constantes a la base de datos física.

**Código Clave: Comunicación Atómica Inter-Procesos**
```python
# backend/services/async_yolo.py
class MultiprocessYOLO:
    def __init__(self, source_id, initial_in=0, initial_out=0):
        # ... colas de frames ...
        
        # Variables atómicas compartidas entre el Worker de IA y la API de red
        self.entry_counter = mp.Value('i', initial_in)
        self.exit_counter = mp.Value('i', initial_out)
        
    def get_counts(self):
        # Lectura instantánea Thread-Safe para el consumo de la Interfaz Web (HUD)
        return self.entry_counter.value, self.exit_counter.value

def yolo_worker(..., entry_counter, exit_counter):
    # Dentro del bucle infinito de procesamiento de cuadros
    res = detector.process_frame(frame, source_id, tw_obj)
    
    # Actualización del recuento numérico extraído de la etapa Tripwire
    if entry_counter is not None and exit_counter is not None:
        entry_counter.value = detector.entry_count
        exit_counter.value = detector.exit_count
```

### 2. Agregación y Generación de KPIs (Business Intelligence)
Los conteos brutos se registran temporalmente en la base de datos bajo la tabla `historico_conteo`, separándolos por ventana de tiempo (`hora_apertura` a `hora_cierre`).

Para convertir esta tabulación simple en métricas útiles de negocio, se desarrolló el motor estadístico en `backend/api/analytics.py` apoyado fuertemente en **Pandas DataFrames** para suplir las carencias matemáticas relacionales nativas de SQLite/PostgreSQL frente a requerimientos analíticos temporales complejos.

El sistema recibe un rango de fechas y calcula 5 KPIs fundamentales operativos:
1. `total_in`: Volumen total de clientes/personas detectados.
2. `total_out`: Egresos totales.
3. `aforo_promedio`: La densidad media de tráfico a lo largo de los distintos horarios operacionales.
4. `peak_day`: Cruce de tablas para hallar el día de máximo movimiento comercial.
5. `stay_rate` (Tasa de Permanencia): Índice porcentual que mapea el nivel de retención de personas (entradas vs salidas remanentes).

**Código Clave: Procesamiento Matemático en Memoria (Pandas)**
```python
# backend/api/analytics.py
results = query.all()

# Volcado masivo a un DataFrame de Pandas para agregación vertiginosa
df = pd.DataFrame([r._asdict() for r in results])

# Conversión y agrupación de fechas estructuradas
df['date_obj'] = pd.to_datetime(df['fecha_registro'])
df['day_of_week'] = df['date_obj'].dt.day_name()

# Cálculo del Día Pico (Aglomeración Máxima)
daily_totals = df.groupby('fecha_registro')[['total_in', 'total_out']].sum()
daily_totals['total_flow'] = daily_totals['total_in'] + daily_totals['total_out']
peak_day = daily_totals['total_flow'].idxmax()

# Tasa de Permanencia (Fórmula de retención)
stay_rate = 0
if total_in > 0:
    stay_rate = round(((total_in - total_out) / total_in) * 100, 2)
    stay_rate = max(0, stay_rate) # Bloquear tasas negativas forzadas
```

### 3. Exposición Analítica (Datasets para Gráficos y Exportación)
Además de los KPIs, el módulo formatea dinámicamente estructuraciones en matrices multidimensionales (Labels, Datasets) listas para ser interpretadas directamente por librerías gráficas Frontend (e.g. Chart.js) para pintar matrices comparativas entre Múltiples Cámaras, Periodos Anteriores y Mapas de Calor acumulados por Día de la Semana.

Complementario al análisis de pantalla, se proveyó un `StreamingResponse` que itera generadores de texto para ensamblar en tiempo real un archivo `.CSV` a disposición de las gerencias.

```python
# Exportación CSV Directa
stream = io.StringIO()
df.to_csv(stream, index=False) # Conversión de la matriz Pandas a formato universal plano

response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
response.headers["Content-Disposition"] = f"attachment; filename=reporte_trafico.csv"
return response
```

En síntesis, este módulo toma el trabajo algebraico de los polígonos virtuales pre-existentes y lo destila en un almacén de datos (Data Warehouse) transitorio que provee respuestas gerenciales cuantificables mediante técnicas robustas de Data Science.
