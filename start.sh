#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [[ ! -f "$DIR/.env" ]]; then
    echo "Error: .env file not found."
    echo "Please copy .env.example to .env and configure your Telegram credentials:"
    echo "   cp .env.example .env"
    exit 1
fi

if [[ -f "$DIR/venv/bin/python3" ]]; then
    PYTHON="$DIR/venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    echo "Error: python3 not found."
    exit 1
fi

if pgrep -f "loop_monitor.py" > /dev/null; then
    echo "Upwork Monitor is already running!"
    exit 0
fi

nohup "$PYTHON" "$DIR/loop_monitor.py" > "$DIR/monitor.log" 2>&1 &
echo $! > "$DIR/monitor.pid"
echo "Upwork Monitor started in background (PID: $(cat "$DIR/monitor.pid"))."
echo "To view live logs: tail -f \"$DIR/monitor.log\""
