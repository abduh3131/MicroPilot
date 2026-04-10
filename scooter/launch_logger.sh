#!/bin/bash
export PYTHONPATH=/data/openpilot

echo "Restarting comma service..."
sudo systemctl restart comma

echo "Stopping old logger..."
pkill -f actuator_logger.py
tmux kill-session -t actuator_logger 2>/dev/null

echo "Removing old log..."
rm -f /data/actuators.csv

echo "Starting new logger..."
tmux new-session -d -s actuator_logger 'python3 -u /data/openpilot/tools/actuator_logger.py'

echo "Done!"
