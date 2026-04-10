#!/bin/bash
# full scooter pipeline launcher using nohup

set -e

OP_DIR="/home/jetson/openpilotV3"
PY="PYTHONPATH=${OP_DIR} python3"

SERIAL_ARG=""
NO_LIDAR=0
NO_MODEL=0
NO_GPS=0
SPEED="0.45"

while [[ $# -gt 0 ]]; do
  case $1 in
    --serial)     SERIAL_ARG="--serial $2"; shift 2 ;;
    --no-lidar)   NO_LIDAR=1; shift ;;
    --no-model)   NO_MODEL=1; shift ;;
    --no-gps)     NO_GPS=1; shift ;;
    --speed)      SPEED="$2"; shift 2 ;;
    *)            echo "[StartAllAb] Unknown: $1"; shift ;;
  esac
done

echo "STARTALL-AB SCOOTER PIPELINE"
echo "  Lidar:   $([ $NO_LIDAR -eq 1 ] && echo OFF || echo 'ON (v2 ROS)')"
echo "  GPS:     $([ $NO_GPS -eq 1 ] && echo OFF || echo ON)"
echo "  Model:   $([ $NO_MODEL -eq 1 ] && echo OFF || echo sidewalk)"
echo "  Serial:  ${SERIAL_ARG:-none}"
echo "  Speed:   ${SPEED}"

echo "[StartAllAb] Killing old processes..."
pkill -f output_serial 2>/dev/null || true
pkill -f "web.py" 2>/dev/null || true
pkill -f scooter_safety 2>/dev/null || true
pkill -f autopilot 2>/dev/null || true
pkill -f exp_auto 2>/dev/null || true
pkill -f virtual_panda 2>/dev/null || true
pkill -f joystickd 2>/dev/null || true
pkill -f lane_follow 2>/dev/null || true
pkill -f overlay_stream 2>/dev/null || true
pkill -f webcam_capture 2>/dev/null || true
pkill -f gps_bridge 2>/dev/null || true
pkill -f nmea_serial_driver 2>/dev/null || true
killall -9 roscore rosmaster rplidarNode 2>/dev/null || true
sleep 2

echo "[StartAllAb] Clearing IPC..."
echo "0.0,0.0" > /tmp/joystick
echo "0" > /tmp/engage
echo "0" > /tmp/autopilot
echo "0" > /tmp/exp_auto
echo "0" > /tmp/lane_follow
echo "0" > /tmp/lidar_stop
echo "0.0" > /tmp/lidar_steer

if [ $NO_LIDAR -eq 0 ]; then
  echo "[StartAllAb] Starting lidar (ROS)..."
  source /opt/ros/noetic/setup.bash
  source /home/jetson/catkin_ws/devel/setup.bash 2>/dev/null || true
  rosclean purge -y 2>/dev/null || true

  LIDAR_PATH=$(ls /dev/serial/by-id/usb-Silicon_Labs* 2>/dev/null | head -1)
  if [ -z "$LIDAR_PATH" ]; then
    echo "[StartAllAb] WARNING: Lidar not found, skipping"
    NO_LIDAR=1
    echo "0" > /tmp/lidar_stop
    echo "0.0" > /tmp/lidar_steer
  else
    echo "[StartAllAb] Lidar at: $LIDAR_PATH"
    nohup roscore > /tmp/log_roscore.txt 2>&1 &
    sleep 5
    nohup rosrun rplidar_ros rplidarNode _serial_port:=$LIDAR_PATH _serial_baudrate:=1000000 _frame_id:=laser_link > /tmp/log_rplidar.txt 2>&1 &
    sleep 4
    echo "[StartAllAb] Starting scooter_safety_v2..."
    nohup python3 /home/jetson/scooter_safety_v2.py > /tmp/log_lidar_safety.txt 2>&1 &
    sleep 2
    echo "[StartAllAb] Lidar v2 running"
  fi
else
  echo "[StartAllAb] Lidar OFF"
  echo "0" > /tmp/lidar_stop
  echo "0.0" > /tmp/lidar_steer
fi

if [ $NO_GPS -eq 0 ]; then
  echo "[StartAllAb] Starting GPS..."
  source /opt/ros/noetic/setup.bash
  source /home/jetson/catkin_ws/devel/setup.bash 2>/dev/null || true

  GPS_PORT=""
  if [ -e /dev/ttyTHS0 ]; then
    GPS_PORT="/dev/ttyTHS0"
  elif [ -e /dev/ttyACM1 ]; then
    GPS_PORT="/dev/ttyACM1"
  elif [ -e /dev/ttyACM0 ]; then
    GPS_PORT="/dev/ttyACM0"
  fi

  if [ -n "$GPS_PORT" ]; then
    echo "[StartAllAb] GPS on $GPS_PORT"
    nohup rosrun nmea_navsat_driver nmea_serial_driver _port:=$GPS_PORT _baud:=9600 > /tmp/log_gps.txt 2>&1 &
    sleep 3
    nohup python3 /home/jetson/gps_bridge.py > /tmp/log_gps_bridge.txt 2>&1 &
    echo "[StartAllAb] GPS running"
  else
    echo "[StartAllAb] WARNING: No GPS port found"
  fi
else
  echo "[StartAllAb] GPS OFF"
fi

echo "[StartAllAb] Starting webcam..."
nohup bash -c "PYTHONPATH=${OP_DIR} python3 ${OP_DIR}/tools/webcam_capture.py --device 0 --fps 20 --width 640 --height 480" > /tmp/log_webcam.txt 2>&1 &
sleep 2

echo "[StartAllAb] Starting virtual panda..."
nohup bash -c "PYTHONPATH=${OP_DIR} python3 ${OP_DIR}/tools/virtual_panda.py" > /tmp/log_vpanda.txt 2>&1 &
sleep 2

echo "[StartAllAb] Starting joystick..."
nohup bash -c "cd ${OP_DIR} && PYTHONPATH=${OP_DIR} python3 tools/joystick/joystickd.py" > /tmp/log_joystick.txt 2>&1 &
sleep 1

echo "[StartAllAb] Starting web UI..."
nohup bash -c "PYTHONPATH=${OP_DIR} python3 ${OP_DIR}/tools/bodyteleop/web.py" > /tmp/log_web.txt 2>&1 &
sleep 1

echo "[StartAllAb] Starting serial output..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOGFILE="${OP_DIR}/logs/actuator_log_${TIMESTAMP}.csv"
mkdir -p "${OP_DIR}/logs"
nohup bash -c "PYTHONPATH=${OP_DIR} python3 ${OP_DIR}/tools/output_serial.py ${SERIAL_ARG} --output ${LOGFILE}" > /tmp/log_serial.txt 2>&1 &
sleep 1

if [ $NO_MODEL -eq 0 ]; then
  echo "[StartAllAb] Starting lane_follow (sidewalk)..."
  nohup bash -c "PYTHONPATH=${OP_DIR} python3 ${OP_DIR}/tools/lane_follow.py --model sidewalk --speed ${SPEED} --rate 20" > /tmp/log_lanefollow.txt 2>&1 &
  sleep 5

  echo "[StartAllAb] Starting overlay..."
  nohup bash -c "PYTHONPATH=${OP_DIR} python3 ${OP_DIR}/tools/overlay_stream.py --fps 15" > /tmp/log_overlay.txt 2>&1 &
  sleep 1

  echo "[StartAllAb] Starting exp_auto..."
  nohup bash -c "PYTHONPATH=${OP_DIR} python3 ${OP_DIR}/tools/exp_auto.py --speed ${SPEED}" > /tmp/log_expauto.txt 2>&1 &
  sleep 1
else
  echo "[StartAllAb] Model/overlay/expauto OFF"
fi

echo "[StartAllAb] Starting autopilot..."
nohup bash -c "PYTHONPATH=${OP_DIR} python3 ${OP_DIR}/tools/autopilot.py --speed ${SPEED}" > /tmp/log_autopilot.txt 2>&1 &
sleep 1

echo ""
echo "ALL SYSTEMS LAUNCHED"
echo ""
echo "  Processes:"
ps aux | grep -E "webcam|vpanda|joystick|web.py|serial|lane_follow|overlay|exp_auto|autopilot|safety|rplidar|roscore|gps" | grep -v grep | awk '{printf "    %-8s %s %s %s\n", $1, $11, $12, $13}' || true
echo ""
IP=$(hostname -I | awk '{print $1}')
echo "  Web UI:  https://${IP}:5000"
echo "  Log:     ${LOGFILE}"
echo ""
echo "  Controls:"
echo "    echo 1 > /tmp/engage"
echo "    echo 1 > /tmp/exp_auto"
echo "    echo 1 > /tmp/lane_follow"
echo "    echo 1 > /tmp/autopilot"
echo ""
echo "  Logs:    tail -f /tmp/log_*.txt"
echo "  Stop:    pkill -f python3; killall roscore rosmaster rplidarNode"
