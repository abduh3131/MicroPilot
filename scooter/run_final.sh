#!/bin/bash
export PATH=/data/bin:$PATH
export PYTHONPATH=/data/openpilot
export DISPLAY=:0

# Cleanup
pkill -f manager.py
tmux kill-session -t openpilot 2>/dev/null
tmux kill-session -t actuator_log 2>/dev/null
pkill ttyd

cd /data/openpilot

# Launch sessions
tmux new -d -s openpilot 'exec ./launch_openpilot.sh'
tmux new -d -s actuator_log 'export PYTHONPATH=/data/openpilot; python3 tools/actuator_logger.py'

# Web terminal
nohup /data/ttyd -W -p 8080 tmux attach -t openpilot > /dev/null 2>&1 &

echo "Sessions:"
tmux ls
