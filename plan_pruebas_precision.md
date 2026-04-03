# Metodología de Evaluación del Prototipo (8.X)

Esta sección define la metodología modular y jerárquica para analizar las capas funcionales del sistema: detección, rastreo y conteo.

## 1. Diseño General de Evaluación
Llevar a cabo una evaluación estructurada bajo los siguientes principios:
- **Separación por capas**: Cada componente se evalúa de forma independiente.
- **Uso de Ground Truth**: Anotaciones manuales sobre videos seleccionados.
- **Reproducibilidad**: Mismos videos y parámetros en todas las pruebas.
- **Escenarios controlados**: Baja afluencia de personas.

## 2. Dataset de Evaluación
Conjunto de prueba compuesto por:
- **Videos por sede**: Hasta 3 sedes seleccionadas.
- **Duración**: 10–15 minutos por video.
- **Escenarios**: Tránsito individual, en pares, cruces simultáneos, permanencia cerca de la línea, cambios de iluminación.

## 3. Evaluación por Capas

### 3.1 Capa de Visión (Detección - YOLO)
**Objetivo**: Evaluar la detección de personas (sin tracking ni conteo).
**Métricas**: Precision, Recall, F1 Score (IoU ≥ 0.5).
**Acción**: Usar `backend/evaluate_vision.py`.

### 3.2 Capa de Memoria (Rastreo - ByteTrack)
**Objetivo**: Mantener la identidad de cada persona.
**Métricas**: MOTA, ID Switches.
**Acción**: Evaluar continuidad de IDs en secuencia de frames.

### 3.3 Capa de Decisión (Conteo - Tripwire)
**Objetivo**: Evaluar precisión de eventos IN/OUT.
**Métricas**: Counting Precision, Counting Recall, Conteos Fantasmas (FP), Error de Direccionalidad.

## 4. Evaluación Integrada
- **MAE** (Error Absoluto de Conteo)
- **Error porcentual**
- **Consistencia temporal**

## 5. Diagnóstico de Fallos
- **Bajo recall en detección** → Problema en YOLO.
- **Alto ID Switch** → Problema en ByteTrack.
- **Tracking correcto pero conteo incorrecto** → Problema en Tripwire.

## 6. Criterios de Aceptación
- **F1 Score** ≥ 0.80
- **MOTA** ≥ 0.75
- **Error de conteo** ≤ 10%
- **Error de direccionalidad** ≤ 5%

---

## 7. Herramientas de Ejecución

### Evaluación de Visión (Aislar YOLO)
```bash
python backend/evaluate_vision.py --video path/to/video.mp4 --gt path/to/gt.txt --show
```

### Evaluación Completa (Modular)
```bash
python backend/evaluate.py --video path/to/video.mp4 --gt path/to/gt.txt --gt-counts path/to/events.txt
```
