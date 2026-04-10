#!/bin/bash
# gokart launcher that starts everything
# uses ros melodic not noetic

set -e

OP_DIR="/home/jetson/openpilotV3_gokart"
ROS_SETUP="source /opt/ros/melodic/setup.bash"
PY="PYTHONPATH=${OP_DIR} python3"

SERIAL_ARG=""
NO_LIDAR=0
NO_MODEL=0
NO_GPS=0
SPEED="0.45"
LIDAR_PORT="/dev/ttyUSB0"

while [ $# -gt 0 ]; do
  case $1 in
    --serial)     SERIAL_ARG="--serial $2"; shift 2 ;;
    --no-lidar)   NO_LIDAR=1; shift ;;
    --no-model)   NO_MODEL=1; shift ;;
    --no-gps)     NO_GPS=1; shift ;;
    --speed)      SPEED="$2"; shift 2 ;;
    --lidar-port) LIDAR_PORT="$2"; shift 2 ;;
    *)            echo "unknown: $1"; shift ;;
  esac
done

echo "GOKART LAUNCHER"

echo "killing old procs"
pkill -f python3 2>/dev/null || true
killall roscore rosmaster rplidarNode 2>/dev/null || true
sleep 2

for f in /tmp/lidar_stop /tmp/lidar_steer /tmp/engage /tmp/autopilot /tmp/lane_follow /tmp/exp_auto /tmp/joystick /tmp/speed_setting; do
  echo "0" > "$f" 2>/dev/null || true
done
echo "0.0,0.0" > /tmp/joystick 2>/dev/null || true
echo "0.0" > /tmp/lidar_steer 2>/dev/null || true
echo "3" > /tmp/speed_setting 2>/dev/null || true

echo "finding webcam"
CAM_DEV=""
for dev in /dev/video0 /dev/video1 /dev/video2 /dev/video3; do
  if [ -e "$dev" ]; then
    if v4l2-ctl --device=$dev --info 2>/dev/null | grep -qi "usb\|uvc\|webcam\|pc camera"; then
      CAM_DEV="$dev"
      break
    fi
  fi
done
if [ -z "$CAM_DEV" ]; then
  CAM_DEV=$(ls /dev/video* 2>/dev/null | head -1)
fi
CAM_IDX=$(echo $CAM_DEV | grep -o '[0-9]*$')
echo "webcam: $CAM_DEV (idx $CAM_IDX)"

if [ $NO_LIDAR -eq 0 ]; then
  echo "starting roscore"
  nohup bash -c "$ROS_SETUP && roscore" > /tmp/log_roscore.txt 2>&1 &
  sleep 6

  LIDAR_DEV=$(ls /dev/serial/by-id/usb-Silicon_Labs* 2>/dev/null | head -1)
  if [ -z "$LIDAR_DEV" ]; then
    LIDAR_DEV="$LIDAR_PORT"
  fi
  echo "lidar: $LIDAR_DEV"

  nohup bash -c "$ROS_SETUP && rosrun rplidar_ros rplidarNode _serial_port:=$LIDAR_DEV _serial_baudrate:=1000000" > /tmp/log_lidar.txt 2>&1 &
  sleep 3

  nohup bash -c "$ROS_SETUP && python3 /home/jetson/scooter_safety_v2.py" > /tmp/log_lidar_safety.txt 2>&1 &
  sleep 1
else
  echo "lidar OFF"
  echo "0" > /tmp/lidar_stop
  echo "0.0" > /tmp/lidar_steer
fi

echo "starting webcam"
nohup python3 -u ${OP_DIR}/tools/webcam_capture.py --device $CAM_IDX --fps 20 --width 640 --height 480 > /tmp/log_webcam.txt 2>&1 &
sleep 2

echo "starting web ui"
nohup bash -c "cd ${OP_DIR} && ${PY} tools/bodyteleop/web.py" > /tmp/log_web.txt 2>&1 &
sleep 2

echo "starting serial output"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p ${OP_DIR}/logs
nohup bash -c "cd ${OP_DIR} && ${PY} tools/output_serial.py ${SERIAL_ARG} --output ${OP_DIR}/logs/gokart_log_${TIMESTAMP}.csv" > /tmp/log_serial.txt 2>&1 &
sleep 1

if [ $NO_MODEL -eq 0 ]; then
  echo "starting model sidewalk road"
  nohup bash -c "cd ${OP_DIR} && ${PY} tools/lane_follow.py --model sidewalk+road --speed ${SPEED} --rate 20" > /tmp/log_lanefollow.txt 2>&1 &
  sleep 5

  echo "starting overlay"
  nohup bash -c "cd ${OP_DIR} && ${PY} tools/overlay_stream.py --fps 15" > /tmp/log_overlay.txt 2>&1 &
  sleep 1

  echo "starting exp_auto"
  nohup bash -c "cd ${OP_DIR} && ${PY} tools/exp_auto.py --speed ${SPEED}" > /tmp/log_expauto.txt 2>&1 &
  sleep 1
fi

echo "starting autopilot"
nohup bash -c "cd ${OP_DIR} && ${PY} tools/autopilot.py --speed ${SPEED}" > /tmp/log_autopilot.txt 2>&1 &

echo ""
echo "GOKART RUNNING"
echo ""
ps aux | grep python3 | grep -v grep | awk '{print $NF}'
echo ""
IP=$(hostname -I | awk '{print $1}')
echo "web: https://${IP}:5000"
echo "log: ${OP_DIR}/logs/gokart_log_${TIMESTAMP}.csv"
echo ""
echo "stop: pkill -f python3; killall roscore rosmaster rplidarNode"
