#!/bin/bash

# Define variables
PROJECT_DIR="/home/jbenalcazar/CntPrs"
VENV_DIR="$PROJECT_DIR/venv"
PID_FILE="$PROJECT_DIR/service.pid"
LOG_FILE="$PROJECT_DIR/server.log"

cd "$PROJECT_DIR" || exit 1

function start_service() {
    # Check if process is already running via PID file
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Service is already running (PID: $PID)."
            return
        else
            echo "Removing stale PID file."
            rm "$PID_FILE"
        fi
    fi

    # Also check via pgrep in case PID file was deleted
    PIDS=$(pgrep -f "uvicorn backend.main:app")
    if [ -n "$PIDS" ]; then
        echo "Service is already running without PID file (PIDs: $PIDS)."
        # Extract first PID
        PID=$(echo "$PIDS" | head -n 1)
        echo "$PID" > "$PID_FILE"
        return
    fi

    echo "Starting service..."
    source "$VENV_DIR/bin/activate"
    
    # Run uvicorn in the background using nohup
    nohup uvicorn backend.main:app --host 0.0.0.0 --port 8000 >> "$LOG_FILE" 2>&1 &
    
    PID=$!
    echo "$PID" > "$PID_FILE"
    echo "Service started (PID: $PID). Logs are being written to $LOG_FILE"
}

function stop_service() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Stopping service (PID: $PID)..."
            kill "$PID"
            
            # Wait for process to exit
            for i in {1..7}; do
                if ps -p "$PID" > /dev/null 2>&1; then
                    sleep 1
                else
                    echo "Service stopped successfully."
                    rm "$PID_FILE"
                    return
                fi
            done
            
            # Force kill if still running
            if ps -p "$PID" > /dev/null 2>&1; then
                echo "Force killing service..."
                kill -9 "$PID"
                echo "Service forcefully stopped."
            fi
        else
            echo "Service is not running, but PID file exists. Cleaning up."
        fi
        rm -f "$PID_FILE"
    else
        echo "No PID file found. Checking for running uvicorn instances..."
        PIDS=$(pgrep -f "uvicorn backend.main:app")
        if [ -n "$PIDS" ]; then
            echo "Killing found uvicorn processes: $(echo "$PIDS" | tr '\n' ' ')"
            kill $PIDS
            sleep 2
            # Check if any survived
            if pgrep -f "uvicorn backend.main:app" > /dev/null; then
                kill -9 $(pgrep -f "uvicorn backend.main:app")
            fi
            echo "Processes stopped."
        else
            echo "Service is not running."
        fi
    fi
}

function status_service() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Service is RUNNING (PID: $PID)."
        else
            echo "Service is NOT RUNNING (PID file exists but process is dead)."
        fi
    else
        PIDS=$(pgrep -f "uvicorn backend.main:app")
        if [ -n "$PIDS" ]; then
            PIDS_FMT=$(echo "$PIDS" | tr '\n' ' ')
            echo "Service is RUNNING (PIDs: $PIDS_FMT), but no PID file found."
        else
            echo "Service is NOT RUNNING."
        fi
    fi
}

case "$1" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        stop_service
        sleep 2
        start_service
        ;;
    status)
        status_service
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
esac
