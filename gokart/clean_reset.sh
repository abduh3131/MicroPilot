#!/bin/bash
set -e
echo "=== KILLING EVERYTHING ==="
pkill -9 -f manager.py 2>/dev/null || true
pkill -9 -f build.py 2>/dev/null || true
pkill -9 -f launch 2>/dev/null || true
pkill -9 ttyd 2>/dev/null || true
for s in openpilot web_terminal actuator_log comma; do
  tmux kill-session -t "$s" 2>/dev/null || true
done
sleep 2

echo "=== WIPING AND RESTORING ==="
rm -rf /data/openpilot
cp -a /data/openpilot_bak /data/openpilot
echo "Restore done"

echo "=== INSTALLING MISSING PYTHON PACKAGES ==="
pip3 install --break-system-packages --no-cache-dir \
  pyserial crcmod xattr smbus2 libusb1 psutil crcmod-plus \
  kaitaistruct sounddevice future-fstrings mapbox-earcut json-rpc \
  websocket-client pympler inputs 2>&1 | tail -3

echo "=== LAUNCHING ==="
cd /data/openpilot
tmux new -d -s openpilot './launch_openpilot.sh 2>&1 | tee /tmp/op_log.txt; while true; do sleep 1; done'
sleep 2
/data/ttyd -p 8080 tmux attach -t openpilot &
disown
sleep 1
echo "=== SESSIONS ==="
tmux ls
echo "=== WAITING FOR OUTPUT ==="
sleep 15
tail -20 /tmp/op_log.txt 2>/dev/null
echo "=== DONE ==="
