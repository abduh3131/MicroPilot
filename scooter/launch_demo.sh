#!/bin/bash
export PYTHONPATH=/data/openpilot:/data/openpilot/opendbc_repo

# Kill any existing processes
pkill -f camerad
pkill -f ui.py

# Start camerad in background
/data/openpilot/system/camerad/camerad &

# Start UI
python3 /data/openpilot/selfdrive/ui/ui.py
