El módulo de Configuración Espacial ("Tripwire") es el responsable de dotar de contexto físico a las detecciones matemáticas, permitiendo que el sistema no solo "vea" personas, sino que entienda su flujo dinámico en una escena. 

Este módulo permite definir líneas virtuales de cruce, direccionalidad (IN/OUT) y establece las reglas algebraicas irrefutables para el conteo automático.

A continuación, el detalle de su desarrollo:

### 1. Definición y Persistencia de Zonas Virtuales 
Desarrollado en `backend/api/tripwire.py` y el modelo de datos. Las reglas espaciales se establecen de manera normalizada (coordenadas relativas de 0.0 a 1.0) para que la configuración sobreviva independientemente de si la cámara cambia de resolución.

Cada cámara (`source_id`) dispone de un único objeto espacial guardado en la Base de Datos que dictamina: los dos puntos de la línea `(X1, Y1)` y `(X2, Y2)`, además del vector de direccionalidad (`direction: 'IN' o 'OUT'`).

### 2. Matemáticas de Intersección de Trayectorias
La evaluación de cruce no utiliza librerías externas pesadas (como Shapely) por cuestiones de rendimiento _Real-Time_. En su lugar, en `backend/services/detection.py`, se implementó un motor matemático puro basado en Geometría Computacional (Counter-Clockwise - CCW).

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

### 3. Cálculo de Dirección con Producto CruzADO (Cross Product)
Saber que una persona cruzó la línea no es suficiente; el sistema debe determinar **en qué dirección lo hizo**.
Una vez que el algoritmo `intersect` confirma un cruce, se evalúa en qué lado matemático de la línea virtual se encontraba la persona en el frame anterior, y en qué lado terminó en el frame actual mediante una comprobación de determinantes (Cross Product).

**Código Clave: Reglas de Conteo e Inserción IN/OUT**
```python
# Evaluado durante el procesamiento de Tracking (Bytetrack)
P_prev = history[-2] # Posición Anterior (Frame N-1)
P_curr = history[-1] # Posición Actual (Frame N)

if intersect(A, B, P_prev, P_curr):
    # Calcular el lado usando Producto Cruz (Determinante 2D)
    side_prev = dx * (P_prev[1] - ty1) - dy * (P_prev[0] - tx1)
    side_curr = dx * (P_curr[1] - ty1) - dy * (P_curr[0] - tx1)
    
    dir_cfg = getattr(tripwire_data, 'direction', 'IN')
    
    # Cruza desde el lado Positivo hacia el Negativo
    if side_prev > 0 and side_curr <= 0:
        if dir_cfg == 'IN':
            self.entry_count += 1
        else:
            self.exit_count += 1
        self.counted_ids.add(track_id)
        
    # Cruza desde el lado Negativo hacia el Positivo
    elif side_prev < 0 and side_curr >= 0:
        if dir_cfg == 'IN':
            self.exit_count += 1
        else:
            self.entry_count += 1
        self.counted_ids.add(track_id)
```

### 4. Mitigación de Falsos Positivos y Anti-Teletransporte
Para robustecer las métricas en producción, el módulo implementa dos capas de auditoría espacial críticas antes de oficializar un cruce:

1. **Memoria de Identidad (`counted_ids`)**: Una memoria tipo `set()` almacena el ID asignado por el Tracker (ej. Persona #45). Si esta persona merodea en la misma zona o pisa la línea repetidas veces en un solo flujo continuo, no se vuelve a sumar a las estadísticas generales de ingresos o egresos.
2. **Filtro de Salto Vectorial Absurdo**: Cuando las secuencias son alteradas (parpadeos de red, reseteo del bucle del video MP4), IDs falsos podrían "saltar" de una esquina a otra, cruzando accidentalmente la línea virtual. El sistema audita la distancia geométrica recorrida por el centroide:
   ```python
   dist = np.sqrt((P_curr[0] - P_prev[0])**2 + (P_curr[1] - P_prev[1])**2)
   # Si recorre más del 33% de toda la pantalla en una fracción de segundo, se descarta por imposible
   if dist < original_w / 3.0: 
       # Procede a evaluar intersect(...)
   ```

Estas técnicas garantizan que el dashboard analítico cuente estrictamente flujos naturales sin sobredimensionar los eventos o corromperse por fluctuaciones de red.
