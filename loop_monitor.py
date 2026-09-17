import asyncio
import time
import subprocess
import sys
from pathlib import Path

import os
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Fallback to system python if venv is missing
VENV_PYTHON = Path(__file__).parent / "venv" / "bin" / "python3"
PYTHON = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
MONITOR_SCRIPT = Path(__file__).parent / "monitor.py"
INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "180"))

print(f"Upwork Job Monitor Daemon started. Checking every {INTERVAL_SECONDS} seconds...")

while True:
    try:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting search cycle...")
        res = subprocess.run([str(PYTHON), str(MONITOR_SCRIPT)], capture_output=False)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Cycle complete (exit code {res.returncode}). Sleeping {INTERVAL_SECONDS}s...")
    except Exception as e:
        print(f"Error during cycle: {e}")
    
    time.sleep(INTERVAL_SECONDS)
