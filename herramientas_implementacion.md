# Herramientas Tecnológicas para la Implementación del Sistema

La selección del *stack* tecnológico y las herramientas de desarrollo del sistema (SCAP) se ha fundamentado en tres pilares esenciales: **compatibilidad** (operación multiplataforma y soporte de hardware variado), **integración** (comunicación fluida entre módulos de IA, backend y visualización) y **facilidad de implementación** (despliegues rápidos con dependencias mínimas).

A continuación, se detalla el ecosistema tecnológico que hace posible la plataforma:

## 1. Antigravity (Agente Cognitivo de Desarrollo Artificial)
El núcleo del ciclo de desarrollo está respaldado por **Antigravity**, un poderoso asistente de codificación de Inteligencia Artificial (impulsado por Google DeepMind). 
*   **Facilidad de Implementación:** Antigravity actúa como un ingeniero de software en la sombra (*Pair-Programming*), estructurando la arquitectura del proyecto, autogestionando refactorizaciones profundas, y documentando activamente el sistema. Esto reduce drásticamente el "Time-to-Market" y la curva de desarrollo humano.
*   **Integración:** Posee la capacidad de orquestar y orquestar las conexiones entre el hardware (cámaras RTSP), los modelos heurísticos de Machine Learning y el despliegue del Dashboard, solucionando cuellos de botella mediante depuración concurrente y generación de código optimizado de extremo a extremo.

## 2. Python y FastAPI (Desarrollo del Backend)
*   **Compatibilidad:** Python es el estándar de la industria para aplicaciones analíticas y de Machine Learning. Es agnóstico al sistema operativo subyacente (Linux, Windows).
*   **Integración:** FastAPI permite exponer microservicios y protocolos de comunicación en tiempo real de forma asíncrona, conectando sin latencia el procesamiento de video exhaustivo con las peticiones del panel de control web.
*   **Facilidad de Implementación:** Genera automáticamente la documentación de los endpoints (Swagger UI), agilizando las pruebas y la validación para desarrolladores frontend.

## 3. YOLO, ByteTrack y OpenCV (Motor de Visión Artificial)
*   **Compatibilidad:** Se emplea *OpenCV* para el preprocesamiento y captura de los *frames* (ya sean archivos `.mp4` o flujos en vivo mediante hardware decodificador RTSP). 
*   **Integración:** El detector de objetos (YOLO) se acopla nativamente al algoritmo de rastreo por asociación de datos (*ByteTrack*), logrando seguir individuos a través de líneas virtuales bajo una carga computacional óptima.
*   **Facilidad de Implementación:** Al no requerir infraestructura masiva de servidores dedicados de inferencia para operaciones básicas, los modelos pre-entrenados garantizan una puesta en marcha eficaz desde el día uno (implementación local o "Edge AI").

## 4. SQLite y SQLAlchemy (Módulo de Almacenamiento)
*   **Compatibilidad:** SQLite es un motor de base de datos integrado (Serverless) completamente transaccional, sin requerir una arquitectura cliente-servidor externa pesada (como PostgreSQL o MySQL).
*   **Integración:** Mediante el ORM (Mapeo Objeto-Relacional) de *SQLAlchemy*, el backend de Python mapea de manera declarativa los eventos detectados por las cámaras directamente a las estructuras relacionales, asegurando que los conteos se guarden fluidamente en tiempo real sin bloquear el flujo de video.
*   **Facilidad de Implementación:** Permite una gestión de bases de datos embebida, donde el archivo `people_counter.db` se inicializa y gestiona sin configuración de credenciales complejas o mantenimiento del lado del servidor, ideal para sistemas autónomos y escalables en diversas sedes.

## 5. Ecosistema Web Vanilla (HTML/CSS/JS) (Frontend)
*   **Compatibilidad:** Empleando estándares nativos se garantiza que el *Dashboard* y la interfaz administrativa sean responsivos y accesibles en cualquier navegador moderno sin instalaciones de plugins.
*   **Facilidad de Implementación e Integración:** Evitar frameworks pesados reduce la complejidad de compilación, haciendo que la entrega del panel visual para la administración de módulos de videovigilancia sea directa, ligera y veloz, comunicándose dinámicamente con la API de FastAPI a través de llamadas asíncronas convencionales.
