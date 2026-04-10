#!/usr/bin/env python3
"""constant throttle when its on for testing lidar avoidance"""

import argparse
import os
import signal
import sys
import time

DEFAULT_SPEED = 0.6
DEFAULT_RATE  = 10
STEERING_CENTER = 0.0

AUTOPILOT_FILE   = "/tmp/autopilot"
JOYSTICK_FILE    = "/tmp/joystick"
ENGAGE_FILE      = "/tmp/engage"
LIDAR_STOP_FILE  = "/tmp/lidar_stop"


def read_file(path, default="0"):
  try:
    with open(path, "r") as f:
      return f.read().strip()
  except Exception:
    return default


def write_joystick(throttle, steering):
  tmp = JOYSTICK_FILE + ".tmp"
  with open(tmp, "w") as f:
    f.write(str(round(throttle, 4)) + "," + str(round(steering, 4)))
  os.rename(tmp, JOYSTICK_FILE)


# main loop that pushes a steady throttle when autopilot is engaged
def run(speed, rate):
  print("[autopilot] Starting speed=" + str(speed) + " rate=" + str(rate) + "Hz")
  print("[autopilot] Waiting for autopilot activation...")

  period = 1.0 / rate
  frame = 0
  was_active = False

  while True:
    t0 = time.time()

    autopilot_on = read_file(AUTOPILOT_FILE) == "1"
    engaged = read_file(ENGAGE_FILE) == "1"
    lidar_stop = read_file(LIDAR_STOP_FILE) == "1"

    if autopilot_on and engaged:
      if not was_active:
        print("[autopilot] ACTIVATED driving at " + str(speed))
        was_active = True

      if lidar_stop:
        # lidar says something is too close so hold zero throttle
        write_joystick(0.0, STEERING_CENTER)
      else:
        write_joystick(speed, STEERING_CENTER)

      frame += 1
      if frame % (rate * 2) == 0:
        lid_str = " ESTOP" if lidar_stop else ""
        print("[autopilot] #" + str(frame) + " active" + lid_str +
              " T=" + str(speed if not lidar_stop else 0.0))

    else:
      if was_active:
        write_joystick(0.0, 0.0)
        print("[autopilot] DEACTIVATED joystick zeroed")
        was_active = False
        frame = 0

    elapsed = time.time() - t0
    if elapsed < period:
      time.sleep(period - elapsed)


def main():
  parser = argparse.ArgumentParser(description="Autopilot")
  parser.add_argument("--speed", type=float, default=DEFAULT_SPEED,
                      help="Forward throttle 0.0-1.0 (default: " + str(DEFAULT_SPEED) + ")")
  parser.add_argument("--rate", type=float, default=DEFAULT_RATE,
                      help="Update rate Hz (default: " + str(DEFAULT_RATE) + ")")
  args = parser.parse_args()

  signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
  signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

  try:
    with open(AUTOPILOT_FILE, "w") as f:
      f.write("0")
  except Exception:
    pass

  try:
    run(args.speed, args.rate)
  finally:
    try:
      write_joystick(0.0, 0.0)
      with open(AUTOPILOT_FILE, "w") as f:
        f.write("0")
    except Exception:
      pass
    print("[autopilot] Stopped.")


if __name__ == "__main__":
  main()
