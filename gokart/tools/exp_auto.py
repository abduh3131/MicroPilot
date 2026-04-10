#!/usr/bin/env python3
"""constant throttle when sidewalk detected, lane keeping, and lidar object avoidance"""

import argparse
import json
import os
import signal
import sys
import time

DEFAULT_SPEED = 0.5
DEFAULT_RATE = 20
MAX_STEER = 0.9

LOOKAHEAD_SHORT = 6.0
LOOKAHEAD_LONG = 18.0
BLEND_SHORT = 0.65
PURE_PURSUIT_GAIN = 8.0

MIN_SPEED_RATIO = 0.3
CURVATURE_BRAKE = 3.0
CONFIDENCE_MIN = 0.08
STALE_TIMEOUT = 1.5
NO_DATA_TIMEOUT = 3.0

EXP_AUTO_FILE = "/tmp/exp_auto"
MODEL_OUTPUT_FILE = "/tmp/model_output.json"
JOYSTICK_FILE = "/tmp/joystick"
ENGAGE_FILE = "/tmp/engage"
LIDAR_STOP_FILE = "/tmp/lidar_stop"


def read_file(path, default="0"):
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except Exception:
        return default


def write_joystick(throttle, steering):
    tmp = "/tmp/joystick_exp.tmp"
    with open(tmp, "w") as f:
        f.write(str(round(throttle, 4)) + "," + str(round(steering, 4)))
    os.rename(tmp, JOYSTICK_FILE)


def read_model_output():
    try:
        if not os.path.exists(MODEL_OUTPUT_FILE):
            return None
        age = time.time() - os.path.getmtime(MODEL_OUTPUT_FILE)
        if age > STALE_TIMEOUT:
            return None
        with open(MODEL_OUTPUT_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None


def get_lateral_at_distance(positions, target_dist):
    if not positions or len(positions) < 2:
        return 0.0

    for i in range(len(positions) - 1):
        x0 = positions[i][0]
        x1 = positions[i + 1][0]
        if x0 <= target_dist <= x1:
            if x1 - x0 > 0.01:
                t = (target_dist - x0) / (x1 - x0)
            else:
                t = 0.0
            y0 = positions[i][1]
            y1 = positions[i + 1][1]
            return y0 + t * (y1 - y0)

    if target_dist >= positions[-1][0]:
        return positions[-1][1]
    return positions[0][1]


def compute_path_curvature(positions):
    if not positions or len(positions) < 5:
        return 0.0

    n = min(15, len(positions))
    y_vals = [p[1] for p in positions[:n]]
    x_end = positions[n - 1][0]

    if x_end < 1.0:
        return 0.0

    max_lateral = max(abs(y) for y in y_vals)
    return max_lateral / x_end


# pure pursuit on the planned path blended with lane centering
def compute_steering(positions, data):
    if not positions or len(positions) < 3:
        return 0.0

    y_short = get_lateral_at_distance(positions, LOOKAHEAD_SHORT)
    y_long = get_lateral_at_distance(positions, LOOKAHEAD_LONG)

    steer_short = y_short / LOOKAHEAD_SHORT * PURE_PURSUIT_GAIN
    steer_long = y_long / LOOKAHEAD_LONG * PURE_PURSUIT_GAIN

    steering = BLEND_SHORT * steer_short + (1.0 - BLEND_SHORT) * steer_long

    if data:
        left_prob = data.get("left_near_prob", 0)
        right_prob = data.get("right_near_prob", 0)
        left_y = data.get("left_near_y", 0)
        right_y = data.get("right_near_y", 0)

        if left_prob > 0.4 and right_prob > 0.4:
            lane_center = (left_y + right_y) / 2.0
            lane_steer = lane_center / LOOKAHEAD_SHORT * PURE_PURSUIT_GAIN
            steering = 0.7 * steering + 0.3 * lane_steer

    return max(-MAX_STEER, min(MAX_STEER, steering))


def compute_throttle(base_speed, curvature, confidence, lidar_stop):
    if lidar_stop:
        return 0.0

    if confidence < CONFIDENCE_MIN:
        return 0.0

    curve_factor = max(MIN_SPEED_RATIO, 1.0 - curvature * CURVATURE_BRAKE)
    conf_factor = max(MIN_SPEED_RATIO, min(1.0, confidence * 1.5))

    throttle = base_speed * curve_factor * conf_factor
    return max(0.0, min(1.0, throttle))


# main loop that follows the planned path
def run(speed, rate):
    print("[exp_auto] Starting, pure pursuit path following")
    print("[exp_auto] Speed=" + str(speed) + " Rate=" + str(rate) + "Hz")
    print("[exp_auto] Lookahead: short=" + str(LOOKAHEAD_SHORT) + "m long=" + str(LOOKAHEAD_LONG) + "m")
    print("[exp_auto] Waiting for activation...")

    period = 1.0 / rate
    frame = 0
    was_active = False
    last_data_time = 0.0
    last_steering = 0.0

    while True:
        t0 = time.time()

        exp_on = read_file(EXP_AUTO_FILE) == "1"
        engaged = read_file(ENGAGE_FILE) == "1"
        lidar_stop = read_file(LIDAR_STOP_FILE) == "1"

        if exp_on and engaged:
            if not was_active:
                print("[exp_auto] ACTIVATED, pure pursuit path following")
                was_active = True
                last_data_time = time.time()
                frame = 0

            data = read_model_output()

            if data is not None:
                last_data_time = time.time()
                positions = data.get("plan_positions", [])
                confidence = data.get("confidence", 0.0)
                plan_prob = data.get("plan_prob", 0.0)

                effective_conf = max(confidence, plan_prob)

                if lidar_stop:
                    write_joystick(0.0, 0.0)
                else:
                    steering = compute_steering(positions, data)
                    last_steering = steering

                    curvature = compute_path_curvature(positions)
                    throttle = compute_throttle(speed, curvature, effective_conf, False)

                    write_joystick(throttle, steering)

                frame += 1
                if frame % (rate * 2) == 0:
                    lid = " ESTOP" if lidar_stop else ""
                    curv = compute_path_curvature(positions)
                    thr = compute_throttle(speed, curv, max(confidence, plan_prob), lidar_stop)
                    print("[exp_auto] #" + str(frame) + lid +
                          " steer=" + str(round(last_steering, 3)) +
                          " conf=" + str(round(confidence, 2)) +
                          " plan=" + str(round(plan_prob, 2)) +
                          " curv=" + str(round(curv, 3)) +
                          " T=" + str(round(thr, 3)))

            else:
                elapsed_no_data = time.time() - last_data_time
                if elapsed_no_data > NO_DATA_TIMEOUT:
                    write_joystick(0.0, 0.0)
                    if frame % (rate * 3) == 0:
                        print("[exp_auto] No model data for " +
                              str(round(elapsed_no_data, 1)) + "s, stopped")
                else:
                    write_joystick(speed * 0.2, last_steering * 0.5)

                frame += 1

        else:
            if was_active:
                write_joystick(0.0, 0.0)
                print("[exp_auto] DEACTIVATED, joystick zeroed")
                was_active = False
                frame = 0

        elapsed = time.time() - t0
        if elapsed < period:
            time.sleep(period - elapsed)


def main():
    global LOOKAHEAD_SHORT, LOOKAHEAD_LONG, PURE_PURSUIT_GAIN

    parser = argparse.ArgumentParser(description="EXP AUTO, pure pursuit autonomous controller")
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED,
                        help="Base cruise speed 0.0-1.0 (default: " + str(DEFAULT_SPEED) + ")")
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE,
                        help="Update rate Hz (default: " + str(DEFAULT_RATE) + ")")
    parser.add_argument("--lookahead", type=float, default=LOOKAHEAD_SHORT,
                        help="Short lookahead distance meters (default: " + str(LOOKAHEAD_SHORT) + ")")
    parser.add_argument("--gain", type=float, default=PURE_PURSUIT_GAIN,
                        help="Pure pursuit gain (default: " + str(PURE_PURSUIT_GAIN) + ")")
    args = parser.parse_args()

    LOOKAHEAD_SHORT = args.lookahead
    PURE_PURSUIT_GAIN = args.gain

    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    try:
        with open(EXP_AUTO_FILE, "w") as f:
            f.write("0")
    except Exception:
        pass

    try:
        run(args.speed, args.rate)
    finally:
        try:
            write_joystick(0.0, 0.0)
            with open(EXP_AUTO_FILE, "w") as f:
                f.write("0")
        except Exception:
            pass
        print("[exp_auto] Stopped.")


if __name__ == "__main__":
    main()
