# SCAP - Sistema de Conteo y Análisis de Personas

Este repositorio contiene el sistema de procesamiento de video y backend para el conteo de personas mediante visión artificial.

## Gestión del Entorno Virtual (venv)

Para ejecutar el sistema correctamente, es necesario configurar el entorno virtual utilizando el archivo `requirements.txt`. El script de servicio requiere que el entorno se llame `venv` y esté ubicado en la raíz del proyecto.

1. **Crear el entorno virtual:**
   ```bash
   python3 -m venv venv
   ```

2. **Activar el entorno virtual:**
   ```bash
   source venv/bin/activate
   ```

3. **Instalar las dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Corrección de pip corrupto (Opcional):**
   Si al intentar instalar dependencias o usar pip obtienes errores indicando que el módulo `pip` no se encuentra o está corrupto, puedes forzar la reinstalación de pip dentro del entorno virtual:
   ```bash
   python3 -m ensurepip --upgrade
   python3 -m pip install --upgrade pip
   ```

## Gestión del Sistema (Subir y Bajar)

El sistema cuenta con el script de control `service.sh` diseñado para facilitar la administración del servidor en segundo plano. Este script maneja la activación automática del entorno virtual, el registro de logs de ejecución y la limpieza de procesos huérfanos.

Antes de ejecutarlo, asegúrate de que tiene permisos de ejecución:
```bash
chmod +x service.sh
```

### Comandos Disponibles

- **Subir el sistema (Iniciarlo):**
  Lanza el servidor FastAPI en segundo plano. Los registros de actividad (logs) se escribirán en el archivo `server.log`.
  ```bash
  ./service.sh start
  ```

- **Bajar el sistema (Detenerlo):**
  Detiene el proceso del servidor y ejecuta una limpieza profunda, eliminando procesos huérfanos de IA (YOLO), trabajadores en memoria y conexiones atascadas de FFMPEG.
  ```bash
  ./service.sh stop
  ```

- **Reiniciar el sistema:**
  Detiene completamente el sistema y lo vuelve a iniciar de manera segura.
  ```bash
  ./service.sh restart
  ```

- **Ver el estado del sistema:**
  Muestra si el servicio se encuentra actualmente en ejecución y lista los PIDs asociados.
  ```bash
  ./service.sh status
  ```

## Reseteo de Eventos en Base de Datos

Si necesitas limpiar la base de datos (por ejemplo, para borrar todos los eventos de entrada y salida registrados o reiniciar el sistema desde cero), puedes hacerlo de las siguientes maneras:

### 1. Borrar la base de datos por completo (Recomendado)
El sistema utiliza SQLite. La forma más sencilla de resetear todo es simplemente eliminando el archivo de la base de datos y dejando que el sistema lo vuelva a crear al iniciar.
*Nota*: Esto borrará también las configuraciones de cámaras y zonas de cruce (tripwires).

```bash
# Asegúrate de detener el sistema primero
./service.sh stop
# Elimina los archivos de la base de datos
rm people_counter.db people_counter.db-shm people_counter.db-wal
# Vuelve a iniciar el sistema
./service.sh start
```

### 2. Borrar solo el historial de conteos (Solo SQLite)
Si deseas conservar la configuración de tus cámaras y de los tripwires, pero quieres borrar los eventos de conteo (`HistoricoConteo`), puedes ejecutar el siguiente comando SQL:

```bash
sqlite3 people_counter.db "DELETE FROM historico_conteo;"
sqlite3 people_counter.db "VACUUM;"
```

## Modo de Desarrollo (Opcional)

Si deseas levantar el servidor de forma manual para ver los logs en tiempo real o en modo de recarga activa (development mode):

```bash
source venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
