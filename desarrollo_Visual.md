El módulo de Visualización y Evaluación es la capa visible de todo el conducto analítico. Su rol es transformar la base de datos de millones de registros transaccionales en inteligencia humana consumible, facilitando decisiones estratégicas y operativas mediante indicadores clave de rendimiento (KPIs) y gráficos comparativos escalables.

A continuación el detalle arquitectónico y de código sobre cómo fue elaborado:

### 1. Interfaz Web de Análisis (Dashboarding)
Ubicada en `backend/static/index.html` y estructurada sobre HTML5 Semántico y CSS Vanilla, obvia el uso de pesados Frameworks Frontend para asegurar máxima agilidad y limpieza de carga.

El *Dashboard* provee una barra de configuración (Filters) que permite cruzar datos multidimensionalmente:
- Filtro por rango de fechas (`start-date`, `end-date`).
- Segmentación por Cámaras Específicas (`filter-cameras`).
- Agrupamiento por Franjas Horarias (Mañana, Tarde, Noche, Madrugada).

**Código Clave: Motor JS de Extracción de Parámetros**
```javascript
// backend/static/js/app.js
function getFilterParams() {
    const startDate = document.getElementById('filter-start-date').value;
    const endDate = document.getElementById('filter-end-date').value;
    const selectedCameras = Array.from(document.getElementById('filter-cameras').selectedOptions).map(opt => opt.value);
    const selectedSlots = Array.from(document.getElementById('filter-timeslots').selectedOptions).map(opt => opt.value);

    return {
        start_date: startDate,
        end_date: endDate,
        cameras: selectedCameras.join(','),
        time_slots: selectedSlots.join(',')
    };
    // ... Parámetros codificados en la URL listos para /api/analytics/dashboard
}
```

### 2. Procesamiento Central de KPIs (Backend to Frontend)
Como se detalló en el módulo de conteo, `backend/api/analytics.py` (FastAPI) procesa los filtros usando DataFrames de **Pandas**, y retorna un JSON fuertemente estructurado en dos nodos `{"kpis": {}, "charts": {}}`.
El frontend recibe esta respuesta y actualiza el DOM de forma asíncrona, inyectando números totales y mostrando tendencias dinámicas verdes/rojas usando clases CSS (`trend-indicator`).

**Código Clave: Integración Asíncrona de Indicadores**
```javascript
// Actualización del DOM Directa (Zero Virtual DOM overhead)
const data = await response.json(); // Data from API

document.getElementById('kpi-total-in').innerText = data.kpis.total_in.toLocaleString();
document.getElementById('kpi-total-out').innerText = data.kpis.total_out.toLocaleString();
document.getElementById('kpi-avg-occupancy').innerText = data.kpis.aforo_promedio;
document.getElementById('kpi-stay-rate').innerText = data.kpis.stay_rate + '%';

// Función Helper para inyectar SVG/estilos dependiendo del crecimiento vs mes pasado
updateTrendIndicator('trend-total-in', data.kpis.trends.total_in);
```

### 3. Representaciones Gráficas de Tendencia (Chart.js)
El corazón de la visualización es `Chart.js`, una librería Open Source basada en HTML5 Canvas que renderiza gráficos acelerados por el navegador web sin saturar los recursos del servidor backend.

El sistema despliega simultáneamente 4 gráficos clave inyectando los arreglos devueltos por la API (`Labels` y `Datasets`) dentro de las instancias persistentes de Chart:

1. **Tendencia de Tráfico General (Line Chart)**: Volumen histórico cruzando fechas vs conteos. Intersecciona múltiples cámaras como líneas independientes (`timeSeriesChart`).
2. **Comparación por Sedes (Horizontal Bar Chart)**: Revela en barras contrapuestas (Ingreso vs Salida) el rendimiento geográfico de los distintos pasillos o locales (`locationsChart`).
3. **Crecimiento vs Periodo Anterior (Vertical Bar Chart)**: Cruce algorítmico entre los días seleccionados en el filtro, frente a la misma cantidad de días exactamente anteriores, dictando el éxito global de tráfico (`periodsChart`).
4. **Análisis Acumulado Semanal (Heatmap Proxy)**: Grafica promedios estrictos agrupados algorítmicamente por los 7 días de la semana, aislando picos naturales estacionales (ej. "los Martes siempre son altos") (`accumulatedChart`).

**Código Clave: Configuración Estética de Chart.js**
```javascript
// Configuración global estandarizada (Modo Oscuro)
Chart.defaults.color = '#64748B';
Chart.defaults.font.family = 'Inter';
Chart.defaults.plugins.tooltip.backgroundColor = '#1E293B';
Chart.defaults.plugins.tooltip.titleColor = '#FFFFFF';

// Inyección y actualización al Vuelo sin recargar la página
timeSeriesChartInstance.data = data.charts.time_series;
timeSeriesChartInstance.update();

locationsChartInstance.data = data.charts.compare_locations;
locationsChartInstance.update();
```

### 4. Capa de Exportación para la Toma de Decisiones
Finalmente, cualquier analítica corporativa requiere portabilidad. Si el usuario desea llevar los datos tabulares mostrados en los gráficos a herramientas analíticas externas (PowerBI, Excel, Tableau), el módulo acopla un disparador de reporte en JS:

```javascript
// Botón "Exportar CSV" ubicado en la barra de filtros
function downloadReport() {
    const params = getFilterParams();
    const query = new URLSearchParams(params).toString();
    // Descarga nativa vía encabezados HTTP Content-Disposition del backend
    window.location.href = `/api/analytics/export?${query}`;
}
```

Todo este engranaje convierte millones de cruces en polígonos imperceptibles en una estructura visual fluida y gerencial para la toma de decisiones inmediata o periódica.
