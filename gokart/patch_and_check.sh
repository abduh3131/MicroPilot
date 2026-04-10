#!/bin/bash
# Patch launch script to skip build
sed -i 's|\./build.py|#./build.py|g' /data/openpilot/launch_chffrplus.sh
grep build.py /data/openpilot/launch_chffrplus.sh

echo "--- CHECKING IMPORT ---"
export PYTHONPATH=/data/openpilot
python3 -c "import sys; print(sys.path); import cereal.messaging; print(cereal.messaging)"
