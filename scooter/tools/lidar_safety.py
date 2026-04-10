#!/usr/bin/env python3
"""reads the rplidar and writes /tmp/lidar_stop when something is too close"""

import argparse
import math
import os
import signal
import sys
import time
from collections import deque

EMERGENCY_DIST = 0.30
AVOID_DIST     = 1.50
MIN_VALID      = 0.15

FRONT_CENTER  = 45.0
FRONT_HALF_W  = 60.0

HISTORY_SIZE         = 5
MAJORITY_THRESHOLD   = 2
EMERGENCY_THRESHOLD  = 1

MAX_NUDGE       = 0.7
MIN_NUDGE       = 0.2
GAP_MIN_WIDTH   = 8.0

LIDAR_STOP_FILE  = "/tmp/lidar_stop"
LIDAR_STEER_FILE = "/tmp/lidar_steer"


def write_flag(path, value):
  tmp = path + ".tmp"
  with open(tmp, "w") as f:
    f.write(str(value))
  os.rename(tmp, path)


def angle_diff(a, b):
  d = (a - b) % 360.0
  if d > 180.0:
    d -= 360.0
  return d


def in_front_cone(angle_deg, center, half_w):
  return abs(angle_diff(angle_deg, center)) <= half_w


# filters a single lidar scan down to points inside the front cone
def process_scan(scan, center, half_w, avoid_dist, min_valid):
  min_dist = float('inf')
  hit_angles = []

  for quality, angle_deg, distance_mm in scan:
    if quality < 5:
      continue
    dist_m = distance_mm / 1000.0
    if dist_m < min_valid:
      continue

    if not in_front_cone(angle_deg, center, half_w):
      continue

    if dist_m < min_dist:
      min_dist = dist_m

    if dist_m <= avoid_dist:
      offset = angle_diff(angle_deg, center)
      hit_angles.append((offset, dist_m))

  hit_angles.sort(key=lambda x: x[0])
  return {
    'min_dist': min_dist,
    'hit_angles': hit_angles,
    'total_hits': len(hit_angles),
  }


# finds the widest open angle in front to steer toward
def find_best_gap(hit_angles, half_w, gap_min_width):
  if not hit_angles:
    return None, 0

  occupied = [a for a, d in hit_angles]

  left_edge = -half_w
  right_edge = half_w

  boundaries = [left_edge] + occupied + [right_edge]
  best_gap_center = None
  best_gap_width = 0.0

  for i in range(len(boundaries) - 1):
    gap_start = boundaries[i]
    gap_end = boundaries[i + 1]
    gap_w = gap_end - gap_start

    if gap_w > best_gap_width:
      best_gap_width = gap_w
      best_gap_center = (gap_start + gap_end) / 2.0

  if best_gap_width >= gap_min_width:
    return best_gap_center, best_gap_width
  else:
    return None, best_gap_width


# picks stop, avoid, or clear from the current scan plus recent history
def decide_action(scan_result, history, emergency_dist, avoid_dist):
  min_dist = scan_result['min_dist']
  total_hits = scan_result['total_hits']

  if min_dist <= emergency_dist:
    scan_class = "emergency"
  elif total_hits >= 1:
    scan_class = "avoid"
  else:
    scan_class = "clear"

  history.append(scan_class)

  emergency_count = sum(1 for h in history if h == "emergency")
  avoid_count = sum(1 for h in history if h == "avoid")

  if emergency_count >= EMERGENCY_THRESHOLD:
    gap_center, gap_width = find_best_gap(
      scan_result['hit_angles'], FRONT_HALF_W, GAP_MIN_WIDTH)

    if gap_center is not None and min_dist > emergency_dist * 0.5:
      nudge = _gap_to_nudge(gap_center, min_dist, emergency_dist, avoid_dist)
      return 0, nudge, "emergency_avoid"
    else:
      return 1, 0.0, "EMERGENCY_STOP"

  if (emergency_count + avoid_count) >= MAJORITY_THRESHOLD:
    gap_center, gap_width = find_best_gap(
      scan_result['hit_angles'], FRONT_HALF_W, GAP_MIN_WIDTH)

    if gap_center is not None:
      nudge = _gap_to_nudge(gap_center, min_dist, emergency_dist, avoid_dist)
      direction = "left" if nudge < 0 else "right"
      return 0, nudge, "avoid_" + direction
    else:
      return 1, 0.0, "NO_GAP_STOP"

  return 0, 0.0, "clear"


def _gap_to_nudge(gap_center_offset, min_dist, emergency_dist, avoid_dist):
  direction = 1.0 if gap_center_offset >= 0 else -1.0

  dist_range = max(avoid_dist - emergency_dist, 0.01)
  closeness = 1.0 - max(0.0, min(1.0, (min_dist - emergency_dist) / dist_range))

  magnitude = MIN_NUDGE + closeness * (MAX_NUDGE - MIN_NUDGE)

  offset_scale = min(1.0, abs(gap_center_offset) / FRONT_HALF_W)
  magnitude = magnitude * max(0.3, offset_scale)

  return direction * min(magnitude, MAX_NUDGE)


# parses 5 byte rplidar samples and yields one full scan at a time
def raw_scan_generator(ser):
  current_scan = []
  while True:
    raw = ser.read(5)
    if len(raw) != 5:
      continue
    b0, b1, b2, b3, b4 = raw
    new_scan = bool(b0 & 0x01)
    quality = b0 >> 2
    angle = ((b1 >> 1) | (b2 << 7)) / 64.0
    distance = (b3 | (b4 << 8)) / 4.0

    if new_scan and current_scan:
      yield current_scan
      current_scan = []

    if quality > 0 and distance > 0:
      current_scan.append((quality, angle, distance))


# main lidar loop that talks to the device and writes the stop and nudge files
def run_lidar(port, emergency_dist, avoid_dist):
  import serial

  write_flag(LIDAR_STOP_FILE, "0")
  write_flag(LIDAR_STEER_FILE, "0.0")

  history = deque(maxlen=HISTORY_SIZE)

  print("[lidar] Opening " + port + " at 1000000 baud ...")
  ser = serial.Serial(port, 1000000, timeout=2)

  def _lidar_init(ser):
    ser.setDTR(False)
    time.sleep(1)
    ser.setDTR(True)
    time.sleep(1)
    ser.write(b'\xa5\x25')
    time.sleep(0.5)
    ser.write(b'\xa5\x40')
    time.sleep(5)
    n = ser.in_waiting
    if n > 0:
      ser.read(n)
    print("[lidar] Flushed " + str(n) + " bytes")
    ser.write(b'\xa5\x20')
    time.sleep(1)
    desc = ser.read(7)
    return desc

  desc = b''
  for attempt in range(5):
    desc = _lidar_init(ser)
    if len(desc) == 7:
      print("[lidar] Scan descriptor: " + desc.hex())
      break
    print("[lidar] Init attempt " + str(attempt + 1) + " failed (empty descriptor), retrying...")
    time.sleep(2)

  if len(desc) != 7:
    print("[lidar] ERROR: Could not start lidar after 5 attempts")
    ser.close()
    sys.exit(1)

  scan_count = 0

  try:
    print("[lidar] Scanning emergency <" + str(emergency_dist) + "m avoid <" +
          str(avoid_dist) + "m cone +/-" + str(FRONT_HALF_W) + " deg")

    for scan in raw_scan_generator(ser):
      t0 = time.time()

      result = process_scan(scan, FRONT_CENTER, FRONT_HALF_W, avoid_dist, MIN_VALID)
      stop, nudge, status = decide_action(result, history, emergency_dist, avoid_dist)

      write_flag(LIDAR_STOP_FILE, str(stop))
      write_flag(LIDAR_STEER_FILE, str(round(nudge, 3)))

      scan_count += 1
      if scan_count % 10 == 0:
        print("[lidar] #" + str(scan_count) + " " + status +
              " min=" + str(round(result['min_dist'], 2)) + "m" +
              " hits=" + str(result['total_hits']) +
              " stop=" + str(stop) +
              " nudge=" + str(round(nudge, 3)))

      elapsed = time.time() - t0
      if elapsed < 0.1:
        time.sleep(0.1 - elapsed)

  except KeyboardInterrupt:
    pass
  finally:
    _cleanup(ser)


# fake lidar for testing without hardware
def run_simulation(emergency_dist, avoid_dist):
  import random

  write_flag(LIDAR_STOP_FILE, "0")
  write_flag(LIDAR_STEER_FILE, "0.0")

  history = deque(maxlen=HISTORY_SIZE)

  scenarios = [
    ("clear path", 4, []),
    ("obstacle right", 5, [(10, 0.9), (12, 0.85), (15, 0.95), (8, 1.0), (18, 1.1)]),
    ("obstacle left", 5, [(-10, 0.9), (-12, 0.85), (-15, 0.95), (-8, 1.0), (-18, 1.1)]),
    ("obstacle center-right", 4, [(2, 0.7), (5, 0.75), (8, 0.8), (10, 0.9), (-2, 0.75)]),
    ("wide wall", 4, [(-20, 0.6), (-10, 0.55), (0, 0.5), (10, 0.55), (20, 0.6)]),
    ("EMERGENCY close", 3, [(-5, 0.3), (0, 0.25), (5, 0.3), (3, 0.35)]),
    ("narrow gap right", 4, [(-25, 0.8), (-15, 0.75), (-5, 0.7), (0, 0.8), (5, 0.85)]),
    ("clearing", 4, []),
  ]

  scan_count = 0

  try:
    while True:
      for name, duration, obstacle_points in scenarios:
        print("\n[lidar] SIM: " + name)
        end_time = time.time() + duration

        while time.time() < end_time:
          noise_points = []
          for angle_off, dist in obstacle_points:
            a = angle_off + random.uniform(-1.5, 1.5)
            d = dist + random.uniform(-0.03, 0.03)
            noise_points.append((a, max(0.1, d)))

          result = {
            'min_dist': min((d for _, d in noise_points), default=float('inf')),
            'hit_angles': sorted(noise_points, key=lambda x: x[0]),
            'total_hits': len(noise_points),
          }

          stop, nudge, status = decide_action(result, history, emergency_dist, avoid_dist)

          write_flag(LIDAR_STOP_FILE, str(stop))
          write_flag(LIDAR_STEER_FILE, str(round(nudge, 3)))

          scan_count += 1
          print("  [" + str(scan_count) + "] " + status.ljust(18) +
                " min=" + str(round(result['min_dist'], 2)).ljust(5) + "m" +
                " hits=" + str(result['total_hits']) +
                " stop=" + str(stop) +
                " nudge=" + (("+" if nudge >= 0 else "") + str(round(nudge, 3))))

          time.sleep(0.1)

  except KeyboardInterrupt:
    pass
  finally:
    write_flag(LIDAR_STOP_FILE, "0")
    write_flag(LIDAR_STEER_FILE, "0.0")
    print("\n[lidar] Simulation stopped. Flags cleared.")


def _cleanup(ser=None):
  write_flag(LIDAR_STOP_FILE, "0")
  write_flag(LIDAR_STEER_FILE, "0.0")
  if ser:
    try:
      ser.write(b'\xa5\x25')
      ser.close()
    except Exception:
      pass
  print("[lidar] Stopped. Flags cleared.")


def main():
  global FRONT_CENTER, FRONT_HALF_W

  parser = argparse.ArgumentParser(description="Lidar safety")
  parser.add_argument("--port", type=str, default="/dev/ttyUSB0")
  parser.add_argument("--simulate", action="store_true", help="Run without lidar hardware")
  parser.add_argument("--front-center", type=float, default=FRONT_CENTER)
  parser.add_argument("--front-width", type=float, default=FRONT_HALF_W)
  parser.add_argument("--emergency-dist", type=float, default=EMERGENCY_DIST)
  parser.add_argument("--avoid-dist", type=float, default=AVOID_DIST)
  args = parser.parse_args()

  FRONT_CENTER = args.front_center
  FRONT_HALF_W = args.front_width

  signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
  signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

  if args.simulate:
    print("[lidar] SIMULATION MODE no hardware")
    run_simulation(args.emergency_dist, args.avoid_dist)
  else:
    run_lidar(args.port, args.emergency_dist, args.avoid_dist)


if __name__ == "__main__":
  main()
