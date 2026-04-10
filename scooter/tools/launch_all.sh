#!/bin/bash
# starts the full scooter pipeline in tmux sessions

set -e

OP_DIR="/home/jetson/openpilotV3"
ROS_SETUP="source /opt/ros/noetic/setup.bash && source /home/jetson/catkin_ws/devel/setup.bash"
PY="PYTHONPATH=${OP_DIR} python3"

SERIAL_ARG=""
NO_LIDAR=0
NO_MODEL=0
SPEED="0.45"
LIDAR_PORT="/dev/ttyUSB0"
MODEL="sidewalk"

while [[ $# -gt 0 ]]; do
  case $1 in
    --serial)     SERIAL_ARG="--serial $2"; shift 2 ;;
    --no-lidar)   NO_LIDAR=1; shift ;;
    --no-model)   NO_MODEL=1; shift ;;
    --speed)      SPEED="$2"; shift 2 ;;
    --lidar-port) LIDAR_PORT="$2"; shift 2 ;;
    --model)      MODEL="$2"; shift 2 ;;
    *)            echo "[launch_all] Unknown arg: $1"; shift ;;
  esac
done

echo "OPENPILOT V3 FULL PIPELINE LAUNCHER"
echo "  Serial:     ${SERIAL_ARG:-none (log only)}"
echo "  Lidar:      $([ $NO_LIDAR -eq 1 ] && echo DISABLED || echo ENABLED)"
echo "  Model:      $([ $NO_MODEL -eq 1 ] && echo DISABLED || echo ${MODEL})"
echo "  Speed:      ${SPEED}"

echo "[launch_all] Stopping old sessions..."
tmux kill-server 2>/dev/null || true
sleep 1

for f in /tmp/lidar_stop /tmp/lidar_steer /tmp/engage /tmp/autopilot /tmp/lane_follow /tmp/exp_auto /tmp/joystick; do
  echo "0" > "$f" 2>/dev/null || true
done
echo "0.0" > /tmp/lidar_steer 2>/dev/null || true
echo "0.0,0.0" > /tmp/joystick 2>/dev/null || true

if [ $NO_LIDAR -eq 0 ]; then
  echo "[launch_all] Starting lidar (roscore + rplidarNode)..."

  LIDAR_DEV=$(ls /dev/serial/by-id/usb-Silicon_Labs* 2>/dev/null | head -1)
  if [ -z "$LIDAR_DEV" ]; then
    LIDAR_DEV="$LIDAR_PORT"
    echo "[launch_all] WARNING: Could not auto-detect lidar, using ${LIDAR_DEV}"
  else
    echo "[launch_all] Found lidar at: ${LIDAR_DEV}"
  fi

  tmux new-session -d -s lidar "
    ${ROS_SETUP}
    killall -9 roscore rosmaster rplidarNode 2>/dev/null
    rosclean purge -y 2>/dev/null
    roscore &
    sleep 5
    rosrun rplidar_ros rplidarNode _serial_port:=${LIDAR_DEV} _serial_baudrate:=1000000 _frame_id:=laser_link
    sleep 999
  "
  sleep 8

  echo "[launch_all] Starting scooter_safety_v4..."
  tmux new-session -d -s safety "
    ${ROS_SETUP}
    cd /home/jetson
    python3 scooter_safety_v2.py
    sleep 999
  "
  sleep 2
else
  echo "[launch_all] Lidar DISABLED, writing safe defaults"
fi


echo "[launch_all] Starting GPS driver + bridge..."
tmux new-session -d -s gps "
  ${ROS_SETUP}
  if [ -e /dev/ttyTHS0 ]; then
    GPS_PORT=/dev/ttyTHS0
  elif [ -e /dev/ttyACM0 ]; then
    GPS_PORT=/dev/ttyACM0
  else
    echo 'WARNING: No GPS port found'
    sleep 999
    exit 1
  fi
  rosrun nmea_navsat_driver nmea_serial_driver _port:=\$GPS_PORT _baud:=9600 &
  sleep 3
  python3 /home/jetson/gps_bridge.py
  sleep 999
"
sleep 3

echo "[launch_all] Starting webcam capture..."
tmux new-session -d -s webcam "${PY} ${OP_DIR}/tools/webcam_capture.py --device 0 --fps 30 --width 1280 --height 720; sleep 999"
sleep 2

echo "[launch_all] Starting openpilot core..."
tmux new-session -d -s vpanda "${PY} ${OP_DIR}/tools/virtual_panda.py; sleep 999"
sleep 2
sleep 1
tmux new-session -d -s bodyteleop "${PY} ${OP_DIR}/tools/bodyteleop/web.py; sleep 999"
sleep 1

echo "[launch_all] Starting serial output..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOGFILE="${OP_DIR}/logs/actuator_log_${TIMESTAMP}.csv"
mkdir -p "${OP_DIR}/logs"
tmux new-session -d -s serial "${PY} ${OP_DIR}/tools/output_serial.py ${SERIAL_ARG} --output ${LOGFILE}; sleep 999"
sleep 1

if [ $NO_MODEL -eq 0 ]; then
  echo "[launch_all] Starting lane_follow (model: ${MODEL})..."
  tmux new-session -d -s lanefollow "${PY} ${OP_DIR}/tools/lane_follow.py --model ${MODEL} --speed ${SPEED} --rate 20; sleep 999"
  sleep 3

  echo "[launch_all] Starting overlay renderer..."
  tmux new-session -d -s overlay "${PY} ${OP_DIR}/tools/overlay_stream.py --fps 15; sleep 999"
  sleep 1

  echo "[launch_all] Starting exp_auto controller..."
  tmux new-session -d -s expauto "${PY} ${OP_DIR}/tools/exp_auto.py --speed ${SPEED}; sleep 999"
  sleep 1
else
  echo "[launch_all] Model/overlay/expauto DISABLED"
fi

echo "[launch_all] Starting autopilot (simple cruise)..."
tmux new-session -d -s autopilot "${PY} ${OP_DIR}/tools/autopilot.py --speed ${SPEED}; sleep 999"
sleep 1

echo ""
echo "ALL SYSTEMS RUNNING"
echo ""
echo "  Sessions:"
tmux ls
echo ""
IP=$(hostname -I | awk '{print $1}')
echo "  Web UI:      https://${IP}:5000"
echo "  Video Feed:  https://${IP}:5000/video_feed"
echo "  CSV Log:     ${LOGFILE}"
echo ""
echo "  Engage:      echo 1 > /tmp/engage"
echo "  Autopilot:   echo 1 > /tmp/autopilot"
echo "  Lane Follow: echo 1 > /tmp/lane_follow"
echo "  Exp Auto:    echo 1 > /tmp/exp_auto"
echo ""
echo "  Stop all:    tmux kill-server"
echo "  View logs:   tmux attach -t <session>"
