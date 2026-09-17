#!/bin/bash
# Install systemd timers for Upwork Monitor.
# Usage: sudo bash setup_timers.sh
#
# Automatically reads the number of search URLs from settings.py
# and creates one timer per URL, staggered evenly across 60 minutes.
# Effective check interval = 60 / N minutes.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(which python3)"
USER="${SUDO_USER:-$(whoami)}"

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo bash setup_timers.sh"
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
  echo "Warning: .env not found. Copy .env.example to .env and fill in your values."
fi

# Count search URLs from settings.py
URL_COUNT=$("$PYTHON" -c "from settings import SEARCH_URLS; print(len(SEARCH_URLS))" 2>/dev/null)
if [[ -z "$URL_COUNT" || "$URL_COUNT" -lt 1 ]]; then
  echo "Error: could not read SEARCH_URLS from settings.py"
  exit 1
fi

# Stagger offset (minutes) between timers
OFFSET_STEP=$(( 60 / URL_COUNT ))
[[ "$OFFSET_STEP" -lt 1 ]] && OFFSET_STEP=1

echo "Found $URL_COUNT search URLs — stagger interval: ${OFFSET_STEP}min"

# Remove all existing timers (0-19)
for i in $(seq 0 19); do
  systemctl disable --now "upwork-monitor-${i}.timer" 2>/dev/null || true
  rm -f "/etc/systemd/system/upwork-monitor-${i}.timer"
  rm -f "/etc/systemd/system/upwork-monitor-${i}.service"
done

# Create new timers
for i in $(seq 0 $(( URL_COUNT - 1 ))); do
  OFFSET=$(( i * OFFSET_STEP ))

  cat > "/etc/systemd/system/upwork-monitor-${i}.service" << EOF
[Unit]
Description=Upwork Monitor — search URL ${i}

[Service]
Type=oneshot
User=${USER}
Environment=DISPLAY=:0
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${PYTHON} ${SCRIPT_DIR}/monitor.py ${i}
StandardOutput=append:/tmp/upwork-monitor.log
StandardError=append:/tmp/upwork-monitor.log
TimeoutStartSec=300
EOF

  cat > "/etc/systemd/system/upwork-monitor-${i}.timer" << EOF
[Unit]
Description=Upwork Monitor — URL ${i} (every 60min, offset ${OFFSET}min)

[Timer]
OnBootSec=${OFFSET}min
OnUnitActiveSec=60min
Persistent=true
Unit=upwork-monitor-${i}.service

[Install]
WantedBy=timers.target
EOF

done

systemctl daemon-reload

for i in $(seq 0 $(( URL_COUNT - 1 ))); do
  systemctl enable --now "upwork-monitor-${i}.timer"
done

echo ""
echo "Done! Installed ${URL_COUNT} timers (check interval: ~${OFFSET_STEP}min)."
echo ""
systemctl list-timers "upwork-monitor-*" --no-pager
