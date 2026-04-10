#!/usr/bin/env python3
"""reads /tmp/joystick and sends throttle and steering to the arduino"""

import csv
import os
import argparse
import signal
import time
import threading


JOYSTICK_FILE = "/tmp/joystick"
ENGAGE_FILE = "/tmp/engage"
LIDAR_STOP_FILE = "/tmp/lidar_stop"
LIDAR_STEER_FILE = "/tmp/lidar_steer"


def signal_handler(sig, frame):
  print("\nStopped.")
  os._exit(0)

signal.signal(signal.SIGINT, signal_handler)


def read_file(path, default="0"):
  try:
    with open(path, "r") as f:
      return f.read().strip()
  except Exception:
    return default


# mashes the IPC files into the 3 numbers the arduino expects
def compute_values():
  engaged = read_file(ENGAGE_FILE) == "1"
  lidar_stop = read_file(LIDAR_STOP_FILE) == "1"
  lidar = 1.0 if lidar_stop else 0.0

  try:
    lidar_nudge = float(read_file(LIDAR_STEER_FILE, "0.0"))
  except ValueError:
    lidar_nudge = 0.0

  joy_raw = read_file(JOYSTICK_FILE, "0.0,0.0")
  try:
    parts = joy_raw.split(",")
    joy_x = float(parts[0])
    joy_y = float(parts[1])
  except Exception:
    joy_x = 0.0
    joy_y = 0.0

  if lidar_stop:
    throttle = 0.0
    steering = 0.0
  elif engaged:
    throttle = max(0.0, min(0.25, joy_x))
    user_steer = joy_y
    steering = max(-1.0, min(1.0, user_steer + lidar_nudge))
  else:
    throttle = 0.0
    steering = 0.0

  if throttle == 0.0:
    throttle = 0.0
  if steering == 0.0:
    steering = 0.0

  return throttle, steering, lidar, engaged, lidar_nudge


# background thread that sends serial commands to the arduino at fixed rate
def serial_thread_func(port, baud, rate):
  import serial

  try:
    ser = serial.Serial(port, baud, timeout=0.1, write_timeout=2.0)
    print("[serial] Opened " + port + " at " + str(baud) + " baud")
  except Exception as e:
    print("[serial] OPEN ERROR: " + str(e))
    return

  # the arduino resets as soon as serial opens so wait it out
  time.sleep(10)

  try:
    startup = ser.read(1024)
    if startup:
      print("[serial] Arduino says: " + startup.decode(errors='replace').strip())
  except Exception:
    pass

  print("[serial] Sending at " + str(rate) + " Hz")

  period = 1.0 / rate
  count = 0
  consecutive_errors = 0

  while True:
    t0 = time.time()

    throttle, steering, lidar, engaged, lidar_nudge = compute_values()


    line = "%s,%s,%s" % (round(throttle, 4), round(steering, 4), round(lidar, 1)) + chr(10)
    try:
      ser.write(line.encode())
      consecutive_errors = 0
    except serial.SerialTimeoutException:
      consecutive_errors += 1
      if consecutive_errors <= 3 or consecutive_errors % 20 == 0:
        print("[serial] write timeout #" + str(consecutive_errors))
      if consecutive_errors >= 10:
        print("[serial] Too many timeouts, reconnecting...")
        try:
          ser.close()
        except Exception:
          pass
        time.sleep(3)
        try:
          ser = serial.Serial(port, baud, timeout=0.1, write_timeout=2.0)
          print("[serial] Reconnected to " + port)
          time.sleep(10)
          try:
            startup = ser.read(1024)
            if startup:
              print("[serial] Arduino says: " + startup.decode(errors="replace").strip())
          except Exception:
            pass
          consecutive_errors = 0
        except Exception as e:
          print("[serial] Reconnect failed: " + str(e))
    except Exception as ex:
      consecutive_errors += 1
      if consecutive_errors <= 3 or consecutive_errors % 20 == 0:
        print("[serial] write error #" + str(consecutive_errors) + ": " + str(ex))
      if consecutive_errors >= 10:
        print("[serial] Too many errors, reconnecting...")
        try:
          ser.close()
        except Exception:
          pass
        time.sleep(3)
        try:
          ser = serial.Serial(port, baud, timeout=0.1, write_timeout=2.0)
          print("[serial] Reconnected to " + port)
          time.sleep(10)
          consecutive_errors = 0
        except Exception as e:
          print("[serial] Reconnect failed: " + str(e))

    try:
      if ser.in_waiting:
        resp = ser.readline().decode(errors='replace').strip()
        if resp:
          print("[arduino] " + resp)
    except Exception:
      pass

    count += 1
    if count % (rate * 2) == 0:
      st_str = "ENGAGED" if engaged else "disengaged"
      lid = " | ESTOP" if lidar >= 0.5 else ""
      if abs(lidar_nudge) > 0.01:
        lid += " | AVOID(" + str(round(lidar_nudge, 2)) + ")"
      print("[serial] #" + str(count) + " " + st_str + lid +
            " T=" + str(round(throttle, 4)) + " S=" + str(round(steering, 4)) +
            " sent=" + line.strip())

    elapsed = time.time() - t0
    if elapsed < period:
      time.sleep(period - elapsed)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--serial", type=str, default=None)
  parser.add_argument("--baud", type=int, default=115200)
  parser.add_argument("--output", type=str, default="actuator_log.csv")
  parser.add_argument("--rate", type=float, default=4.0)
  args = parser.parse_args()

  print("[main] Starting log: " + args.output + " rate: " + str(args.rate) + " Hz")
  print("[main] Arduino protocol: throttle(0-1),steering(-1 to 1),lidar(0/1)")

  if args.serial:
    st = threading.Thread(target=serial_thread_func, args=(args.serial, args.baud, args.rate), daemon=True)
    st.start()
  else:
    print("[main] No serial port, logging only.")

  log_dir = os.path.dirname(args.output)
  if log_dir and not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)
  fh = open(args.output, "w", newline="")
  writer = csv.writer(fh)
  writer.writerow(["timestamp_ns", "throttle", "steering", "lidar", "lidar_nudge", "engaged"])
  fh.flush()

  try:
    with open(JOYSTICK_FILE, "w") as f:
      f.write("0.0,0.0")
  except Exception:
    pass

  print("[main] Entering CSV loop at " + str(args.rate) + " Hz")

  period = 1.0 / args.rate
  frame_count = 0

  while True:
    t0 = time.time()

    throttle, steering, lidar, engaged, lidar_nudge = compute_values()

    timestamp = int(time.time() * 1e9)
    writer.writerow([timestamp, round(throttle, 4), round(steering, 4), round(lidar, 1), round(lidar_nudge, 3), int(engaged)])

    frame_count += 1
    if frame_count % 4 == 0:
      fh.flush()
      st_str = "ENGAGED" if engaged else "disengaged"
      lid = " | ESTOP" if lidar >= 0.5 else ""
      if abs(lidar_nudge) > 0.01:
        lid += " | AVOID(" + str(round(lidar_nudge, 2)) + ")"
      print("[main] #" + str(frame_count) + " " + st_str + lid +
            " T=" + str(round(throttle, 4)) + " S=" + str(round(steering, 4)))

    elapsed = time.time() - t0
    if elapsed < period:
      time.sleep(period - elapsed)


if __name__ == "__main__":
  main()
