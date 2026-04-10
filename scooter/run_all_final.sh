#!/bin/bash
export PATH=/data/bin:$PATH
export PYTHONPATH=/data/openpilot
export DISPLAY=:0

# Stop any existing
pkill -f manager.py
tmux kill-session -t openpilot 2>/dev/null
tmux kill-session -t actuator_log 2>/dev/null
pkill ttyd

cd /data/openpilot

# Launch Openpilot
tmux new -d -s openpilot 'exec ./launch_openpilot.sh'

# Launch Actuator Logger
tmux new -d -s actuator_log 'export PYTHONPATH=/data/openpilot; python3 tools/actuator_logger.py'

# Launch Web Terminal
nohup /data/ttyd -W -p 8080 tmux attach -t openpilot > /dev/null 2>&1 &

echo "Sessions started:"
tmux ls
