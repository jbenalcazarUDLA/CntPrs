El módulo de Almacenamiento y Trazabilidad se diseñó con el objetivo de garantizar la persistencia confiable de los datos de tráfico recopilados en tiempo real, al tiempo que salvaguarda un entorno analítico para medir el rendimiento de la Inteligencia Artificial (métricas de precisión y sesgo).

A continuación se detalla su implementación y arquitectura:

### 1. Motor de Base de Datos y Sistema de Concurrencia (WAL)
Tener una cámara procesando a 15 cuadros por segundo e insertando datos, de manera simultánea a un gerente realizando búsquedas web de reportes mensuales, generaría un colapso de bloqueo de base de datos (`Database Locked`) en configuraciones convencionales. 

Para resolverlo, en `backend/database.py`, la persistencia se apoya en SQLite motorizado localmente (ideal para Edge Computing o despliegues _on-premise_), pero inyectando comandos SQLite/C explícitos a nivel de motor (`event.listens_for(Engine, "connect")`) para alterar el comportamiento binario del almacenamiento:

**Código Clave: Habilitación de WAL**
```python
# backend/database.py
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    # Write-Ahead Logging: Permite N lectores concurrentes simultáneos a 1 Escritor. No bloquea la DB.
    cursor.execute("PRAGMA journal_mode=WAL") 
    cursor.execute("PRAGMA synchronous=NORMAL") # Mejora I/O de disco drásticamente
    cursor.execute("PRAGMA temp_store=MEMORY")  # Mueve transacciones temporales de disco a RAM
    cursor.close()
```

### 2. Estructura y Registro Asíncrono de Eventos Operativos
No se guardan "detecciones individuales", sino métricas sumariadas en ventanas de tiempo preconfiguradas administradas por el orquestador maestro (`scheduler.py`). 
El programador de tareas automáticas (`APScheduler`) lanza hilos que interrogan los algoritmos de YOLO de forma desatendida, procediendo a asentar la sumatoria dentro del Modelo `HistoricoConteo`.

Los atributos almacenados estructuran la dimensión temporal y física de cad evento comercial:
*   `source_id`: Identificación foránea de la sede o cámara de captura.
*   `fecha_registro`: Fecha estricta estructurada YYYY-MM-DD.
*   `hora_apertura` / `hora_cierre`: Ventana temporal del informe (Ej: desde 08:00:00 hasta 08:15:30).
*   `total_in` / `total_out`: Transacciones comerciales (personas) ejecutadas.

**Código Clave: Asentador en Tiempo Real**
```python
# backend/scheduler.py
if curr_in != last_saved_in or curr_out != last_saved_out:
    # Se detecta nueva actividad mercantil, guardado instanciado en el Historial
    crud.update_historico_conteo_realtime(
        db=db,
        source_id=self.source_id,
        fecha_registro=self.start_time_record.strftime("%Y-%m-%d"),
        hora_apertura=self.start_time_record.strftime("%H:%M:%S"),
        hora_cierre=datetime.datetime.now().strftime("%H:%M:%S"),
        total_in=curr_in,
        total_out=curr_out
    )
```

### 3. Trazabilidad de Rendimiento de IA (System Metrics)
Más allá de guardar datos logísticos comerciales, en el desarrollo ingenieril es exigido contar con una capa de control cruzado. Desarrollado en `backend/services/metrics.py`, el sistema cuenta con integraciones matemáticas orientadas exclusivamente a auditar la Inteligencia Artificial a través del dataset de validación.

Mediante el algoritmo "Húngaro" (Asignación Lineal mediante `scipy.optimize.linear_sum_assignment`), el módulo diagnostica la calidad de detección y rastreo cruzando cajas anotadas manualmente (_Ground Truth_) contra cajas calculadas por YOLO:

1. **Eficiencia Espacial (Intersection over Union - IoU)**:
   Evalúa geográficamente cuánto coincide el recuadro que ve la IA con la persona real.
2. **Precision & Recall Dinámico**:
   Calcula Verdaderos Positivos (`tp`), Falsos Positivos (`fp` - Sombras o espejos contados por accidente) y Falsos Negativos (`fn` - Personas que YOLO obvió).
3. **Métricas de Rendimiento de Rastreo (MOTA tracking eval)**:
   Si a una persona se le pierde el Tracking y se le asigna un Nuevo ID artificialmente, el algoritmo lo atrapa devolviendo `fps` (identidades falsas inventadas predichas) y `misses` (rastreados perdidos en las transiciones).

**Código Clave: Motor de Trazabilidad y Error de IA**
```python
# backend/services/metrics.py
def evaluate_tracking_frame(gt_tracks, pred_tracks, distance_threshold=0.5):
    # Genera la matriz cruzada de costo matemático usando Cobertura 1-IoU
    cost_matrix = np.ones((len(gt_ids), len(pred_ids)))
    
    for i, g_id in enumerate(gt_ids):
        for j, p_id in enumerate(pred_ids):
            iou = calculate_iou(gt_tracks[g_id], pred_tracks[p_id])
            if iou >= distance_threshold:
                cost_matrix[i, j] = 1 - iou
                
    # Resolución Algoritmo Húngaro (Mínimo coste Global)
    g_idx, p_idx = linear_sum_assignment(cost_matrix)
    
    # ... Se deducen matches, misses(perdidos) y Falsos Positivos(fps) para trazar errores
```

Esta arquitectura de almacenamiento blinda tanto el registro puramente comercial para el cliente (Sedes, Fechas, Conteo) con un subsistema SQLite In-Memory Concurrente WAL, así como la trazabilidad algorítmica técnica para auditoría científica posterior de la exactitud de los Modelos (Evaluador Húngaro IoU).
