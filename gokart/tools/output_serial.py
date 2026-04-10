#!/usr/bin/env python3
"""reads /tmp/joystick and sends throttle and steering to the arduino over a 6 value csv"""

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
SPEED_SETTING_FILE = "/tmp/speed_setting"


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


# reads all ipc files and builds the 6 values the arduino expects
def compute_values():
  engaged = read_file(ENGAGE_FILE) == "1"
  lidar_stop = read_file(LIDAR_STOP_FILE) == "1"

  try:
    lidar_nudge = float(read_file(LIDAR_STEER_FILE, "0.0"))
  except ValueError:
    lidar_nudge = 0.0

  try:
    speed_setting = int(read_file(SPEED_SETTING_FILE, "3"))
    speed_setting = max(0, min(5, speed_setting))
  except ValueError:
    speed_setting = 3

  joy_raw = read_file(JOYSTICK_FILE, "0.0,0.0")
  try:
    parts = joy_raw.split(",")
    joy_x = float(parts[0])
    joy_y = float(parts[1])
  except Exception:
    joy_x = 0.0
    joy_y = 0.0

  arm = 1 if engaged else 0
  brake = 1.0 if lidar_stop else 0.0
  # only flip direction when there is actual throttle input so the relay doesnt click
  if joy_x < -0.05:
    direction = 0
    joy_x = abs(joy_x)
  elif joy_x > 0.05:
    direction = 1
  else:
    direction = 1
    joy_x = 0.0
  # scales throttle to match the speed setting
  multiplier = (speed_setting + 1) / 6.0

  if not engaged:
    steer = 0.0
    throttle = 0.0
    brake = 0.0
  elif lidar_stop:
    # lidar estop kills throttle but keeps steering alive
    steer = max(-1.0, min(1.0, joy_y + lidar_nudge))
    throttle = 0.0
  else:
    steer = max(-1.0, min(1.0, joy_y + lidar_nudge))
    throttle = max(0.0, min(1.0, joy_x)) * multiplier

  if steer == 0.0:
    steer = 0.0
  if throttle == 0.0:
    throttle = 0.0

  return steer, brake, arm, throttle, direction, speed_setting, lidar_nudge


# opens the serial port and sends the 6 value csv to the arduino at a fixed rate
def serial_thread_func(port, baud, rate):
  import serial

  try:
    ser = serial.Serial(port, baud, timeout=0.1, write_timeout=0.5)
    print("[serial] opened " + port + " @ " + str(baud))
  except Exception as e:
    print("[serial] cant open: " + str(e))
    return

  time.sleep(10)

  try:
    startup = ser.read(1024)
    if startup:
      print("[arduino] " + startup.decode(errors='replace').strip())
  except Exception:
    pass

  print("[serial] sending 6 vals @ " + str(rate) + "hz")

  period = 1.0 / rate
  count = 0
  errors = 0

  while True:
    t0 = time.time()

    steer, brake, arm, throttle, direction, ss, nudge = compute_values()

    line = (str(round(steer, 2)) + ","
            + str(round(brake, 2)) + ","
            + str(arm) + ","
            + str(round(throttle, 2)) + ","
            + str(direction) + ","
            + str(ss) + "\n")

    try:
      ser.write(line.encode())
      errors = 0
    except Exception as ex:
      errors += 1
      if errors <= 3 or errors % 20 == 0:
        print("[serial] write error #" + str(errors) + ": write failed: " + str(ex))
      if errors >= 10:
        print("[serial] Too many errors, reconnecting...")
        try:
          ser.close()
        except Exception:
          pass
        time.sleep(2)
        try:
          ser = serial.Serial(port, baud, timeout=0.1, write_timeout=0.5)
          print("[serial] Reconnected to " + port)
          time.sleep(10)
          try:
            ser.read(1024)
          except Exception:
            pass
          errors = 0
          print("[serial] Reconnect successful, resuming")
        except Exception as re_ex:
          print("[serial] Reconnect failed: " + str(re_ex))
          errors = 0
          time.sleep(5)

    try:
      if ser.in_waiting:
        resp = ser.readline().decode(errors='replace').strip()
        if resp:
          print("[arduino] " + resp)
    except Exception:
      pass

    count += 1
    if count % (int(rate) * 2) == 0:
      st = "ARM" if arm else "OFF"
      lid = " ESTOP" if brake >= 0.5 else ""
      if abs(nudge) > 0.01:
        lid += " AVOID(" + str(round(nudge, 2)) + ")"
      print("#" + str(count) + " " + st + lid
            + " S=" + str(round(steer, 2))
            + " T=" + str(round(throttle, 2))
            + " SS=" + str(ss)
            + " > " + line.strip())

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

  print("[gokart] log: " + args.output + " rate: " + str(args.rate) + "hz")

  if args.serial:
    st = threading.Thread(target=serial_thread_func, args=(args.serial, args.baud, args.rate), daemon=True)
    st.start()
  else:
    print("[gokart] no serial port, log only")

  log_dir = os.path.dirname(args.output)
  if log_dir and not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)
  fh = open(args.output, "w", newline="")
  writer = csv.writer(fh)
  writer.writerow(["ts", "steer", "brake", "arm", "throttle", "dir", "ss", "nudge"])
  fh.flush()

  for path, val in [(JOYSTICK_FILE, "0.0,0.0"), (SPEED_SETTING_FILE, "3")]:
    try:
      if not os.path.exists(path):
        with open(path, "w") as f:
          f.write(val)
    except Exception:
      pass

  period = 1.0 / args.rate
  n = 0

  while True:
    t0 = time.time()

    steer, brake, arm, throttle, direction, ss, nudge = compute_values()

    ts = int(time.time() * 1e9)
    writer.writerow([ts, round(steer, 2), round(brake, 2), arm, round(throttle, 2), direction, ss, round(nudge, 3)])

    n += 1
    if n % 4 == 0:
      fh.flush()
      st = "ARM" if arm else "OFF"
      lid = " ESTOP" if brake >= 0.5 else ""
      print("#" + str(n) + " " + st + lid
            + " S=" + str(round(steer, 2))
            + " T=" + str(round(throttle, 2))
            + " SS=" + str(ss))

    elapsed = time.time() - t0
    if elapsed < period:
      time.sleep(period - elapsed)


if __name__ == "__main__":
  main()
