#!/usr/bin/env python3
"""runs the model on camera frames and steers the gokart"""

import argparse
import json
import os
import signal
import sys
import time

import cv2
import numpy as np

DEFAULT_SPEED = 0.45
DEFAULT_RATE = 20
DEFAULT_MODEL = "supercombo"
STEERING_GAIN = 2.0
MAX_STEER = 0.8
NO_LANE_TIMEOUT = 2.0

LANE_FOLLOW_FILE = "/tmp/lane_follow"
EXP_AUTO_FILE = "/tmp/exp_auto"
JOYSTICK_FILE = "/tmp/joystick"
ENGAGE_FILE = "/tmp/engage"
LIDAR_STOP_FILE = "/tmp/lidar_stop"
CAMERA_FRAME = "/tmp/camera_frame.jpg"
MODEL_OUTPUT_FILE = "/tmp/model_output.json"


def read_file(path, default="0"):
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except Exception:
        return default


def write_joystick(throttle, steering):
    tmp = JOYSTICK_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write(f"{round(throttle, 4)},{round(steering, 4)}")
    os.rename(tmp, JOYSTICK_FILE)


def write_model_output(steering, confidence, lane_info, plan_info, frame_num):
    try:
        data = {
            "steering": round(steering, 4),
            "confidence": round(confidence, 4),
            "lane_lines": lane_info.get("_full", []),
            "plan_positions": plan_info.get("positions", []),
            "plan_prob": round(plan_info["prob"], 4),
            "left_near_y": round(lane_info["left_near_y"], 3),
            "right_near_y": round(lane_info["right_near_y"], 3),
            "left_near_prob": round(lane_info["left_near_prob"], 3),
            "right_near_prob": round(lane_info["right_near_prob"], 3),
            "frame": frame_num,
            "ts": time.time(),
        }
        tmp = MODEL_OUTPUT_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.rename(tmp, MODEL_OUTPUT_FILE)
    except Exception:
        pass


def load_frame():
    try:
        if not os.path.exists(CAMERA_FRAME):
            return None
        age = time.time() - os.path.getmtime(CAMERA_FRAME)
        if age > 2.0:
            return None
        return cv2.imread(CAMERA_FRAME)
    except Exception:
        return None


# picks the model adapter based on the cli flag
def create_adapter(model_name, steering_gain):
    if model_name == "supercombo":
        from adapters.supercombo_adapter import SupercomboAdapter
        return SupercomboAdapter(steering_gain=steering_gain)

    elif model_name == "sidewalk":
        from adapters.sidewalk_adapter import SidewalkAdapter
        return SidewalkAdapter(steering_gain=steering_gain)

    elif model_name == "sidewalk+road":
        from adapters.sidewalk_adapter import SidewalkAdapter
        return SidewalkAdapter(steering_gain=steering_gain, include_road=True)

    else:
        print(f"[lane_follow] ERROR: Unknown model '{model_name}'")
        print(f"[lane_follow] Available models: supercombo, sidewalk, sidewalk+road")
        sys.exit(1)


# main loop that runs the model and writes joystick output
def run(speed, rate, adapter):
    model_name = adapter.get_name()
    print(f"[lane_follow] Ready, model={model_name} speed={speed} rate={rate}Hz")
    print("[lane_follow] Waiting for activation...")

    period = 1.0 / rate
    frame_num = 0
    was_active = False
    last_lane_time = 0

    while True:
        t0 = time.time()

        lane_on = read_file(LANE_FOLLOW_FILE) == "1"
        exp_auto_on = read_file(EXP_AUTO_FILE) == "1"
        engaged = read_file(ENGAGE_FILE) == "1"
        lidar_stop = read_file(LIDAR_STOP_FILE) == "1"

        model_needed = (lane_on or exp_auto_on) and engaged

        if model_needed:
            if not was_active:
                mode = "LANE_FOLLOW" if lane_on else "EXP_AUTO"
                print(f"[lane_follow] ACTIVATED (model for {mode})")
                was_active = True
                last_lane_time = time.time()

            # stop hard if lidar says theres an obstacle
            if lidar_stop and lane_on:
                write_joystick(0.0, 0.0)
            else:
                frame = load_frame()
                if frame is None:
                    if lane_on:
                        if time.time() - last_lane_time < NO_LANE_TIMEOUT:
                            write_joystick(speed * 0.3, 0.0)
                        else:
                            write_joystick(0.0, 0.0)
                else:
                    try:
                        steering, confidence, lane_info, plan_info = adapter.run(frame)

                        write_model_output(steering, confidence, lane_info, plan_info, frame_num)

                        if lane_on:
                            if confidence > 0.1:
                                last_lane_time = time.time()
                                throttle = speed * (0.5 + 0.5 * min(confidence, 1.0))
                                write_joystick(throttle, steering)
                            else:
                                elapsed = time.time() - last_lane_time
                                if elapsed < NO_LANE_TIMEOUT:
                                    write_joystick(speed * 0.3, 0.0)
                                else:
                                    write_joystick(0.0, 0.0)

                    except Exception as e:
                        if frame_num % 20 == 0:
                            print(f"[lane_follow] Model error: {e}")
                        if lane_on:
                            write_joystick(0.0, 0.0)

            frame_num += 1

            if frame_num % rate == 0:
                lid = " ESTOP" if lidar_stop else ""
                mode = "LF" if lane_on else "EXP"
                try:
                    print(f"[lane_follow] #{frame_num} [{mode}]{lid} steer={steering:+.3f} conf={confidence:.2f} "
                          f"lanes L={lane_info['left_near_y']:+.1f}({lane_info['left_near_prob']:.2f}) "
                          f"R={lane_info['right_near_y']:+.1f}({lane_info['right_near_prob']:.2f}) "
                          f"path_y={float(np.mean(plan_info['path_y'][:5])):+.2f}")
                except Exception:
                    print(f"[lane_follow] #{frame_num} [{mode}]{lid}")

        else:
            if was_active:
                if lane_on or (not exp_auto_on):
                    write_joystick(0.0, 0.0)
                try:
                    os.remove(MODEL_OUTPUT_FILE)
                except Exception:
                    pass
                print("[lane_follow] DEACTIVATED")
                was_active = False
                frame_num = 0

        elapsed = time.time() - t0
        if elapsed < period:
            time.sleep(period - elapsed)


# parses args and starts the main loop
def main():
    parser = argparse.ArgumentParser(description="Lane Follow")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        choices=["supercombo", "sidewalk", "sidewalk+road"],
                        help="Which model to use (default: supercombo)")
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED,
                        help="Base cruise speed 0.0-1.0 (default: 0.45)")
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE,
                        help="Model inference rate in Hz (default: 20)")
    parser.add_argument("--steering-gain", type=float, default=STEERING_GAIN,
                        help="Steering sensitivity (default: 2.0)")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    try:
        with open(LANE_FOLLOW_FILE, "w") as f:
            f.write("0")
    except Exception:
        pass

    print(f"[lane_follow] Model: {args.model}")
    adapter = create_adapter(args.model, args.steering_gain)
    adapter.load_model()

    try:
        run(args.speed, args.rate, adapter)
    finally:
        try:
            write_joystick(0.0, 0.0)
            with open(LANE_FOLLOW_FILE, "w") as f:
                f.write("0")
        except Exception:
            pass
        print("[lane_follow] Stopped.")


if __name__ == "__main__":
    main()
