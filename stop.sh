#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

pkill -f "loop_monitor.py" 2>/dev/null
pkill -f "monitor.py" 2>/dev/null
rm -f "$DIR/monitor.pid" "$DIR/monitor.lock"

echo "Upwork Monitor has been stopped."
