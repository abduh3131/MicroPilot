#!/bin/bash
# starts lidar openpilot and serial inside tmux sessions

set -e

OP_DIR="/home/jetson/openpilotV3_gokart"
ROS_SETUP="source /opt/ros/noetic/setup.bash && source /home/jetson/catkin_ws/devel/setup.bash"
PY="PYTHONPATH=${OP_DIR} python3"

SERIAL_ARG=""
if [ "$1" == "--serial" ] && [ -n "$2" ]; then
    SERIAL_ARG="--serial $2"
    echo "[launch_all] Serial output to: $2"
fi

tmux kill-server 2>/dev/null || true
sleep 1

rm -f /tmp/lidar_stop /tmp/engage 2>/dev/null
echo "0" > /tmp/lidar_stop
echo "0" > /tmp/engage

# starts the lidar
tmux new-session -d -s lidar "${ROS_SETUP} && cd /home/jetson && bash fix_lidar.sh; sleep 999"
sleep 8

# starts the safety and bridge
tmux new-session -d -s safety "${ROS_SETUP} && cd /home/jetson && python3 scooter_safety_v2.py; sleep 999"
sleep 2
tmux new-session -d -s bridge "${ROS_SETUP} && cd ${OP_DIR} && python3 tools/lidar_bridge.py; sleep 999"
sleep 1

# starts the fake panda
tmux new-session -d -s vpanda "${PY} ${OP_DIR}/tools/virtual_panda.py; sleep 999"
sleep 2
# starts the joystick daemon
tmux new-session -d -s joystick "cd ${OP_DIR} && ${PY} tools/joystick/joystickd.py; sleep 999"
sleep 1
# starts the web ui
tmux new-session -d -s bodyteleop "${PY} ${OP_DIR}/tools/bodyteleop/web.py; sleep 999"
sleep 1

# starts the serial output to arduino
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOGFILE="${OP_DIR}/logs/actuator_log_${TIMESTAMP}.csv"
mkdir -p "${OP_DIR}/logs"
tmux new-session -d -s serial "${PY} ${OP_DIR}/tools/output_serial.py ${SERIAL_ARG} --output ${LOGFILE}; sleep 999"
sleep 2

echo ""
echo "ALL SYSTEMS RUNNING"
echo ""
echo "  Sessions:"
tmux ls
echo ""
echo "  Web UI:     https://$(hostname -I | awk '{print $1}'):5000"
echo "  CSV Log:    ${LOGFILE}"
echo "  Lidar Flag: /tmp/lidar_stop"
echo "  Engage:     echo 1 > /tmp/engage"
echo ""
echo "  Serial format: throttle,steering,estop"
echo "    throttle: 1.0 back to 1.0 forward"
echo "    steering: 1.0 left to 1.0 right"
echo "    estop:    0 normal or 1 brake"
echo ""
echo "  Stop all:   tmux kill-server"
echo "  View logs:  tmux attach -t serial"
