El desarrollo de este módulo del pipeline se ha estructurado para aislar de forma segura todo lo relacionado con la recepción y configuración de la fuente de video _antes_ de enviarla a cualquier análisis de Inteligencia Artificial (procesamiento asíncrono pesado). 

A continuación el detalle de cómo se materializó:

### 1. Ingesta Inicial y Validación de Disponibilidad (RTSP / Archivos)
Desarrollado en `backend/api/ingestion.py`. Para los archivos estáticos (MP4, AVI) (`/upload`), el flujo simplemente almacena el activo binario en memoria secundaria local (disco) y lo registra.

La clave está en cómo se operan las **Cámaras IP vía RTSP**. Para garantizar el paradigma _Near Real-Time (NRT)_, se pre-configura OpenCV y FFMPEG a nivel de variables de entorno para que descarten buffers internos, utilicen TCP estable y obvien métricas corruptas. Seguidamente, se valida que esté **activo y transmitiendo frames útiles** para integrarlo como posible candidato en la base de datos (baseline):

```python
# backend/api/ingestion.py
@router.post("/rtsp", response_model=schemas.VideoSource)
def register_rtsp(source: schemas.VideoSourceCreate, db: Session = Depends(get_db)):
    import os, cv2
    
    # [NRT] Configuración FFMPEG forzada para evitar buffering o latencias
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|fflags;discardcorrupt|flags;low_delay"
    
    cap = cv2.VideoCapture(source.path_url)
    if not cap.isOpened():
        raise HTTPException(status_code=400, detail="Could not connect to the RTSP stream")
        
    # Validar integridad: se lee iterativamente hasta cerciorarse de captar el primer cuadro sin fallos
    success = False
    for _ in range(10):
        cap.grab()
        success, frame = cap.read()
        if success: break
            
    cap.release()
    if not success:
        raise HTTPException(status_code=400, detail="Connected but failed to read a frame.")
        
    return crud.create_video_source(db=db, source=source)
```

### 2. Adquisición NRT Ininterrumpida (Threaded Reading)
Cuando el usuario enciende el Stream sobre una de estas fuentes, se activa el sistema de ingesta constante desarrollado en `backend/services/video_reader.py`. 

Debido a que una cámara IP produce de a 15 a 30 FPS en tiempo real, procesar cada cuadro en un modelo Yolo inevitablemente genera cuellos de botella resultando en *lag* o buffers sobrecargados. A nivel de ingesta, esto se soluciona ejecutando un hilo secundario (daemon) que continuamente "drena" los cuadros entrantes a la máxima velocidad posible, y sobrescribe la cola de lectura para almacenar **única y exclusivamente el frame más reciente** (descartando los viejos). De esta manera la capa de la IA (consumidor) recibe siempre el cuadro actual.

```python
# backend/services/video_reader.py
class VideoReaderWrapper:
    def __init__(self, cap, is_rtsp=False):
        self.cap = cap
        self.is_rtsp = is_rtsp
        # Lista temporal tipo FIFO que acepta únicamente 1 ítem 
        self.q = collections.deque(maxlen=1)
        self.cond = threading.Condition()
        
        if self.is_rtsp and self.cap.isOpened():
            self.running = True
            # Iniciamos hilo asíncrono de consumo bruto
            self.thread = threading.Thread(target=self._reader, daemon=True)
            self.thread.start()
            
    def _reader(self):
        # Este ciclo consume exhaustivamente el RTSP evadiendo el buffer residual
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.cond:
                    self.q.append(frame) # Actualiza y desecha lo más viejo
                    self.cond.notify()
```

### 3. Establecimiento del `Baseline` (Repositorio Base)
Previo a cualquier análisis inteligente, la fuente (el _endpoint_ y formato verificado) se asienta en PostgreSQL/SQLite a través del modelo SQLAlchemy provisto en `backend/models.py`. Actúa exclusivamente como la piedra angular del sistema donde el _dashboard_ acude para reconocer a qué orígenes de datos tiene derecho a monitorizar.

```python
# backend/models.py
class VideoSource(Base):
    __tablename__ = "video_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    type = Column(String)  # Categorización primordial: 'file' or 'rtsp'
    path_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relaciones que demuestran que es el "baseline", del cual todo lo demás depende
    tripwire = relationship("Tripwire", back_populates="source", uselist=False)
    schedule = relationship("CameraSchedule", back_populates="source", uselist=False)
```

En síntesis, este "módulo" funge como guardabarreras y estabilizador paramétrico (TCP y Threads Deque) que impide fallos costosos en las etapas de inteligencia artificial subsiguientes, asegurando conectividad constante con la máxima actualidad de los cuadros de imagen a analizar.
