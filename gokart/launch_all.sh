#!/bin/bash
set -e

echo "=== Installing all missing Python packages ==="
pip3 install --break-system-packages \
  pyserial crcmod xattr smbus2 websocket-client pympler 2>&1 | tail -3

echo ""
echo "=== Killing old sessions ==="
pkill -f manager.py 2>/dev/null || true
pkill -f build.py 2>/dev/null || true
pkill -f actuator_logger 2>/dev/null || true
tmux kill-session -t openpilot 2>/dev/null || true
tmux kill-session -t web_terminal 2>/dev/null || true
tmux kill-session -t actuator_log 2>/dev/null || true
sleep 1

echo ""
echo "=== Launching openpilot ==="
cd /data/openpilot
tmux new -d -s openpilot './launch_openpilot.sh'

echo "=== Starting actuator logger ==="
tmux new -d -s actuator_log 'cd /data/openpilot && python3 tools/actuator_logger.py'

echo "=== Starting web terminal ==="
sleep 1
tmux new -d -s web_terminal '/data/ttyd -p 8080 tmux attach -t openpilot'

echo ""
echo "=== Active sessions ==="
tmux ls
echo ""
echo "=== ALL DONE ==="
