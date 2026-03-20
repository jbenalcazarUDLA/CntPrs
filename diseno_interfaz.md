# Diseño de la Interfaz Visual (SCAP)

La interfaz de usuario del sistema está concebida bajo principios de *Business Intelligence* (Inteligencia de Negocios) con un enfoque limpio e intuitivo. Con el fin de facilitar tanto la operatividad técnica como el análisis gerencial de datos, la plataforma se divide en tres módulos principales integrados en un panel de control unificado:

## 1. Módulo de Gestión (Administración e Infraestructura)
Este módulo actúa como el centro de control para la configuración de la red de videovigilancia y los algoritmos de detección.
*   **Gestión de Sedes y Cámaras:** Proporciona vistas mediante tablas y formularios modales que permiten al administrador agregar, modificar o eliminar distintas ubicaciones físicas (sedes). Cada sede dispone de un árbol lógico para organizar, agregar y eliminar las respectivas cámaras IP o NVR vinculadas a ella.
*   **Definición de Zonas Virtuales:** Mediante una interfaz gráfica superpuesta al cuadro de video de cada cámara, el usuario puede arrastrar puntos interactivamente para trazar líneas de cruce virtual (*Tripwires*) y definir el vector direccional para contabilizar de forma precisa dónde está la "Entrada" (IN) y la "Salida" (OUT).

## 2. Submódulo de Ingesta de Video
Orientado a la captura y retroalimentación inmediata, este submódulo consolida el procesamiento del motor de IA.
*   **Motor Híbrido:** Dispone de un reproductor versátil totalmente compatible para cargar y procesar archivos de video locales (como `.mp4` o `.avi`) o conectarse a flujos de datos en red *Near Real-Time* (NRT) vía RTSP.
*   **Monitoreo y HUD:** Sobre el video en reproducción, el visor superpone un *Heads-Up Display* que incluye indicadores alfanuméricos en las esquinas superiores detallando el total de ingresos y salidas en tiempo real, junto con los recuadros delimitadores (Bounding Boxes) y estelas de rastreo de cada persona (Bytetrack) para una auditoría visual del desempeño del modelo.

## 3. Módulo de Visualización Analítica (Dashboard)
Es el componente gerencial del sistema, encargado de transformar los registros de la base de datos en información procesable mediante una disposición de tarjetas (Bento Grid).
*   **Navegación y Filtros:** Cuenta con controles superiores que permiten seleccionar la analítica de una sede de forma particular o, si se prefiere, visualizar datos globales (consolidados). Permite aplicar filtros precisos seleccionando rangos de fechas (inicio-fin), así como ver métricas segmentadas por hora, día, semana o analizar todo el mes.
*   **Métricas Clave (KPIs):** Tarjetas de resumen que presentan a simple vista el total de ingresos y salidas correspondientes al periodo o sede seleccionada, y el volumen promedio de personas calculado por cada franja horaria.
*   **Gráficos Estructurales:**
    *   **Tendencias y Pronósticos:** Gráficos de líneas interactivos que exponen los picos y valles de afluencia para interpretar de manera clara comportamientos de tráfico (ej: por hora a lo largo de un día o por día a lo largo de un mes).
    *   **Comparación y Rendimiento:** Gráficos de barras que facilitan el análisis contrastivo; permitiendo cotejar los flujos entre diversas sedes (Sede A vs Sede B) de forma simultánea, o contrastar comportamientos en diferentes rangos de tiempo (ej: Semana 1 vs Semana 2).
    *   **Análisis Acumulado:** Gráficos y representaciones sumatorias para auditorías mensuales, mostrando las magnitudes globales acumuladas con una representación progresiva a lo largo de periodos extensos.
