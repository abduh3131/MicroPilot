#!/bin/bash
cd /data/openpilot
sed -i "s/'yuv', 'pthread', 'zstd'/'yuv', 'pthread', 'zstd', 'OpenCL'/" system/loggerd/SConscript
echo "Patched SConscript:"
grep OpenCL system/loggerd/SConscript

echo ""
echo "=== Running scons build ==="
cd /data/openpilot
scons -j$(nproc) 2>&1 | tail -20

echo ""
echo "=== Build done, relaunching ==="
pkill -f manager.py 2>/dev/null || true
tmux kill-session -t openpilot 2>/dev/null || true
sleep 1
cd /data/openpilot
tmux new -d -s openpilot './launch_openpilot.sh'
sleep 2
pkill ttyd 2>/dev/null || true
nohup /data/ttyd -W -p 8080 tmux attach -t openpilot > /dev/null 2>&1 &
tmux ls
echo "=== ALL DONE ==="
