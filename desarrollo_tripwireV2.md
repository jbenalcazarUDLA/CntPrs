El módulo de **Configuración Espacial y Temporal** es el responsable de dotar de contexto físico y cronológico a las detecciones matemáticas del sistema. 

Como métrica central:
*   Configuración espacial y temporal, se definen zonas virtuales de análisis mediante líneas de cruce (tripwire) con direccionalidad de entrada y salida (IN/OUT), junto con la calendarización de operación que establece días y rangos horarios en los cuales el sistema debe procesar los flujos de video. Estas configuraciones permiten contextualizar tanto el movimiento de las personas como el periodo en el que se realiza el análisis, estableciendo las reglas espaciales y temporales que posteriormente serán utilizadas para el conteo automático.

A continuación, el detalle de su desarrollo integral:

---

## PARTE I: Configuración Espacial (Tripwire)

### 1. Definición y Persistencia de Zonas Virtuales
Desarrollado en `backend/api/tripwire.py` y el modelo de datos. Las reglas espaciales se establecen de manera normalizada (coordenadas relativas de `0.0` a `1.0`) para que la configuración sobreviva independientemente de si la cámara cambia de resolución.

Cada cámara dispone de un único objeto espacial guardado en la Base de Datos que dictamina: los dos puntos de la línea `(X1, Y1)` y `(X2, Y2)`, además del vector de direccionalidad (`direction: 'IN' o 'OUT'`).

### 2. Matemáticas de Intersección de Trayectorias
La evaluación de cruce no utiliza librerías externas pesadas (como Shapely) por cuestiones de rendimiento *Real-Time*. En su lugar, en `backend/services/detection.py`, se implementó un motor matemático puro basado en Geometría Computacional (Counter-Clockwise - CCW).

El sistema mantiene un historial de los centroides de cada persona rastreada. Para cada cuadro, traza un segmento entre la posición de la persona en el `frame N-1` y el `frame N`. Luego, verifica matemáticamente si ese segmento vectorial interseca el segmento estático de la línea de Tripwire de la cámara.

**Código Clave: Lógica Geométrica CCW**
```python
# backend/services/detection.py
# Algoritmo de orientación para 3 puntos en un plano cartesiano 2D
def ccw(A, B, C):
    return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])

# Verifica si dos segmentos de línea (A-B de la trayectoria y C-D del Tripwire) se cruzan
def intersect(A, B, C, D):
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)
```

### 3. Cálculo de Dirección con Producto CruzADO
Saber que una persona cruzó la línea no es suficiente; el sistema debe determinar **en qué dirección lo hizo**. Una vez que el algoritmo de intersección confirma un cruce, se evalúa en qué lado matemático de la línea virtual se encontraba la persona mediante una comprobación de determinantes (Cross Product).

**Código Clave: Reglas de Conteo e Inserción IN/OUT**
```python
if intersect(A, B, P_prev, P_curr):
    # Calcular el lado usando Producto Cruz (Determinante 2D)
    side_prev = dx * (P_prev[1] - ty1) - dy * (P_prev[0] - tx1)
    side_curr = dx * (P_curr[1] - ty1) - dy * (P_curr[0] - tx1)
    
    dir_cfg = getattr(tripwire_data, 'direction', 'IN')
    
    # Cruza desde el lado Positivo hacia el Negativo
    if side_prev > 0 and side_curr <= 0:
        if dir_cfg == 'IN': self.entry_count += 1
        else: self.exit_count += 1
```

---

## PARTE II: Configuración Temporal (Calendarización)

Para que el servidor actúe de manera autónoma sin intervención humana, se integró un robusto motor de calendarización paramétrica que orquesta las inferencias basado en reglas de tiempo estáticas.

### 1. Parametrización de Rangos Horarios REST
Desarrollado en `backend/api/schedule.py`. Exponemos endpoints RESTful mediante los cuales la plataforma Web determina para cada cámara (`source_id`) los días de la semana (Lunes a Domingo) y el lapso horario exacto (`start_time`, `end_time`) en el que la analítica debe estar activa.

```python
# backend/api/schedule.py
@router.put("/{source_id}", response_model=schemas.CameraSchedule)
def update_camera_schedule(source_id: int, schedule: schemas.CameraScheduleCreate, db: Session = Depends(get_db)):
    if source_id != schedule.source_id:
         raise HTTPException(status_code=400, detail="Path ID does not match Body Source ID")
    return crud.create_or_update_camera_schedule(db=db, schedule=schedule)
```

### 2. Motor de Orquestación con APScheduler
En `backend/scheduler.py`, se configuró la biblioteca `BackgroundScheduler` para ejecutar una tarea supervisora (Inyector Cron) cada minuto (`cron, minute='*'`). 

Esta tarea comprueba la hora actual del servidor frente al registro de horarios activos obtenidos desde la base de datos de cada cámara. Si la cámara está en horario programado y no está siendo escaneada, instiga la recolección asíncrona; si la cámara acaba de salir de su horario, interrumpe el bucle analítico y libera los recursos en RAM asociados a ese stream.

**Código Clave: Inyector Cron (`check_schedules`)**
```python
# backend/scheduler.py
def check_schedules():
    """Esta función es llamada cada minuto por APScheduler"""
    now = datetime.datetime.now()
    current_time_str = now.strftime("%H:%M")
    current_day_str = day_mapping[now.weekday()]
    
    # Evalúa la autorización temporal en la Base de Datos
    for source in sources:
        schedule = crud.get_camera_schedule(db, source.id)
        is_active_today = getattr(schedule, current_day_str)
        
        should_run = False
        if is_active_today and (schedule.start_time <= current_time_str < schedule.end_time):
            should_run = True
            
        # Orquestación de Procesos (Encender o Apagar motor Headless)
        if should_run and source.id not in active_tasks:
            # Despliega hilo de consumo analítico asíncrono
            threading.Thread(target=launch_task, args=(source.id, ...)).start()
            
        elif not should_run and source.id in active_tasks:
            # Apaga el stream y limpia pipelines una vez cruzado el umbral temporal
            active_tasks[source.id].stop_event.set()
```

### 3. Despliegue de Analítica Desatendida (`HeadlessStreamTask`)
Cuando la validación temporal determina que el análisis debe iniciar, el sistema levanta internamente el `VideoReaderWrapper` y `MultiprocessYOLO` que procesan los cuadros en segundo plano y suben el conteo oficial a la Base de Datos de manera ininterrumpida sin depender de peticiones del *frontend*, garantizando robustez a la métrica.
