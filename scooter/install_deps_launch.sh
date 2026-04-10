#!/bin/bash
set -e

echo "=== Parsing pyproject.toml and installing all deps ==="
cd /data/openpilot

# Extract all dependencies from pyproject.toml and install them
python3 -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    d = tomllib.load(f)
deps = d.get('project', {}).get('dependencies', [])
# Clean version specifiers for pip
for dep in deps:
    print(dep)
" > /tmp/deps.txt

echo "Found dependencies:"
cat /tmp/deps.txt

pip3 install --break-system-packages -r /tmp/deps.txt 2>&1 | tail -10

echo ""
echo "=== Relaunching openpilot ==="
pkill -f manager.py 2>/dev/null || true
pkill -f build.py 2>/dev/null || true
tmux kill-session -t openpilot 2>/dev/null || true
tmux kill-session -t web_terminal 2>/dev/null || true
tmux kill-session -t actuator_log 2>/dev/null || true
sleep 1

tmux new -d -s openpilot 'cd /data/openpilot && ./launch_openpilot.sh'
tmux new -d -s actuator_log 'cd /data/openpilot && python3 tools/actuator_logger.py'
sleep 1
tmux new -d -s web_terminal '/data/ttyd -p 8080 tmux attach -t openpilot'

echo ""
tmux ls
echo "=== DONE ==="
