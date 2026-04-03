#!/bin/bash

# ==========================================
# Script: normalize_video.sh
# Uso: ./normalize_video.sh input.mp4 output.mp4
# ==========================================

# Validar número de parámetros
if [ "$#" -ne 2 ]; then
    echo "Uso: $0 <archivo_entrada.mp4> <archivo_salida.mp4>"
    exit 1
fi

INPUT="$1"
OUTPUT="$2"

# Verificar si el archivo de entrada existe
if [ ! -f "$INPUT" ]; then
    echo "Error: El archivo de entrada no existe."
    exit 1
fi

echo "Procesando video..."
echo "Entrada: $INPUT"
echo "Salida: $OUTPUT"

# Ejecutar FFmpeg
ffmpeg -i "$INPUT" \
-vf "scale=640:480,fps=30" \
-c:v libx264 -preset medium -crf 23 \
-pix_fmt yuv420p \
-vsync cfr \
-c:a aac -b:a 128k \
-movflags +faststart \
"$OUTPUT"

# Verificar resultado
if [ $? -eq 0 ]; then
    echo "✅ Video procesado correctamente."
else
    echo "❌ Error al procesar el video."
fi
