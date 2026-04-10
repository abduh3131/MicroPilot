#!/usr/bin/env python3
"""draws lane lines and planned path on top of the camera feed for the web ui"""

import argparse
import json
import os
import signal
import sys
import time

import cv2
import numpy as np

DEFAULT_FPS = 20
OVERLAY_FRAME = "/tmp/overlay_frame.jpg"
CAMERA_FRAME = "/tmp/camera_frame.jpg"
MODEL_OUTPUT = "/tmp/model_output.json"
ENGAGE_FILE = "/tmp/engage"
LANE_FOLLOW_FILE = "/tmp/lane_follow"
EXP_AUTO_FILE = "/tmp/exp_auto"
LIDAR_STOP_FILE = "/tmp/lidar_stop"

X_IDXS = np.array([
    0., 0.1875, 0.75, 1.6875, 3., 4.6875, 6.75, 9.1875, 12.,
    15.1875, 18.75, 22.6875, 27., 31.6875, 36.75, 42.1875, 48.,
    54.1875, 60.75, 67.6875, 75., 82.6875, 90.75, 99.1875, 108.,
    117.1875, 126.75, 136.6875, 147., 157.6875, 168.75, 180.1875, 192.
])

CAM_HEIGHT = 1.22
CAM_FOCAL = 500.0
CAM_HORIZON = 0.38

MAX_DRAW_DIST = 80.0
PATH_HALF_W = 0.9


def read_file(path, default="0"):
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except Exception:
        return default


def read_model_output():
    try:
        if not os.path.exists(MODEL_OUTPUT):
            return None
        age = time.time() - os.path.getmtime(MODEL_OUTPUT)
        if age > 2.0:
            return None
        with open(MODEL_OUTPUT, "r") as f:
            return json.load(f)
    except Exception:
        return None


def road_to_screen(x_fwd, y_lat, img_w, img_h, z=0.0):
    if x_fwd < 0.5:
        return None
    cx = img_w * 0.5
    cy = img_h * CAM_HORIZON
    u = cx - CAM_FOCAL * y_lat / x_fwd
    v = cy + CAM_FOCAL * (CAM_HEIGHT - z) / x_fwd
    return (u, v)


def road_to_pixel(x_fwd, y_lat, img_w, img_h, z=0.0):
    pt = road_to_screen(x_fwd, y_lat, img_w, img_h, z)
    if pt is None:
        return None
    u, v = int(round(pt[0])), int(round(pt[1]))
    if 0 <= u < img_w and 0 <= v < img_h:
        return (u, v)
    return None


# draws the green path corridor with a chevron at the base
def draw_path_corridor(img, positions, active=True):
    h, w = img.shape[:2]
    left_pts = []
    right_pts = []

    for pos in positions:
        x_fwd = pos[0]
        y_lat = pos[1]
        z_up = pos[2] if len(pos) > 2 else 0.0
        if x_fwd < 0.5 or x_fwd > MAX_DRAW_DIST:
            continue
        pl = road_to_screen(x_fwd, y_lat + PATH_HALF_W, w, h, z_up)
        pr = road_to_screen(x_fwd, y_lat - PATH_HALF_W, w, h, z_up)
        if pl and pr:
            left_pts.append([int(round(pl[0])), int(round(pl[1]))])
            right_pts.append([int(round(pr[0])), int(round(pr[1]))])

    if len(left_pts) < 3:
        return

    polygon = np.array(left_pts + right_pts[::-1], dtype=np.int32)

    overlay = img.copy()
    color = (0, 220, 0) if active else (120, 120, 120)
    cv2.fillPoly(overlay, [polygon], color)
    alpha = 0.28 if active else 0.12
    cv2.addWeighted(overlay, alpha, img, 1.0 - alpha, 0, img)

    if left_pts and right_pts:
        bl, br = left_pts[0], right_pts[0]
        base_x = (bl[0] + br[0]) // 2
        base_y = max(bl[1], br[1])
        if base_y > h * 0.4:
            cw = min(25, abs(bl[0] - br[0]) // 4)
            ch = min(35, int(cw * 1.3))
            if cw > 3 and base_x > 0 and base_x < w:
                chev = np.array([[base_x - cw, base_y],
                                 [base_x, base_y - ch],
                                 [base_x + cw, base_y]], dtype=np.int32)
                ov2 = img.copy()
                cv2.fillPoly(ov2, [chev], (0, 200, 255))
                cv2.addWeighted(ov2, 0.5, img, 0.5, 0, img)


# draws the four white lane line curves
def draw_lane_lines(img, lane_lines):
    h, w = img.shape[:2]
    if len(lane_lines) != 4:
        return

    for i, line in enumerate(lane_lines):
        prob = line["prob"]
        if prob < 0.15:
            continue

        y_vals = line["y"]
        points = []
        n_pts = min(len(y_vals), len(X_IDXS))
        for j in range(n_pts):
            x_fwd = X_IDXS[j]
            if x_fwd < 1.0 or x_fwd > MAX_DRAW_DIST:
                continue
            pt = road_to_pixel(x_fwd, y_vals[j], w, h, 0.0)
            if pt:
                points.append(pt)

        if len(points) < 2:
            continue

        pts = np.array(points, dtype=np.int32)

        if i in (1, 2):
            color = (255, 255, 255)
            thickness = max(2, int(4 * prob))
        else:
            color = (180, 180, 180)
            thickness = max(1, int(3 * prob))

        ov = img.copy()
        cv2.polylines(ov, [pts], False, color, thickness, cv2.LINE_AA)
        a = min(0.8, prob * 1.4)
        cv2.addWeighted(ov, a, img, 1.0 - a, 0, img)


def draw_green_border(img, thickness=4):
    h, w = img.shape[:2]
    cv2.rectangle(img, (1, 1), (w - 2, h - 2), (0, 200, 0), thickness)


# draws the on screen heads up display
def draw_hud(img, data, mode_name, lidar_stop, fps):
    h, w = img.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX

    steering = data.get("steering", 0.0)
    confidence = data.get("confidence", 0.0)
    left_prob = data.get("left_near_prob", 0.0)
    right_prob = data.get("right_near_prob", 0.0)

    if mode_name:
        mc = (0, 255, 0)
    else:
        mode_name = "MANUAL"
        mc = (150, 150, 150)
    tw = cv2.getTextSize(mode_name, font, 0.7, 2)[0][0]
    ov = img.copy()
    cv2.rectangle(ov, (10, 10), (tw + 30, 45), (0, 0, 0), -1)
    cv2.addWeighted(ov, 0.6, img, 0.4, 0, img)
    cv2.putText(img, mode_name, (18, 36), font, 0.7, mc, 2, cv2.LINE_AA)

    if data:
        ct = str(int(confidence * 100)) + "%"
        ts = cv2.getTextSize(ct, font, 1.2, 2)[0]
        cx = (w - ts[0]) // 2
        ov2 = img.copy()
        cv2.rectangle(ov2, (cx - 10, 8), (cx + ts[0] + 10, 50), (0, 0, 0), -1)
        cv2.addWeighted(ov2, 0.5, img, 0.5, 0, img)
        cc = (0, 255, 0) if confidence > 0.4 else (0, 255, 255) if confidence > 0.2 else (100, 100, 255)
        cv2.putText(img, ct, (cx, 42), font, 1.2, cc, 2, cv2.LINE_AA)

    if data:
        st = "STEER %.2f" % steering
        ts = cv2.getTextSize(st, font, 0.5, 1)[0]
        sx = (w - ts[0]) // 2
        sy = h - 8
        ov3 = img.copy()
        cv2.rectangle(ov3, (sx - 8, sy - 18), (sx + ts[0] + 8, sy + 5), (0, 0, 0), -1)
        cv2.addWeighted(ov3, 0.6, img, 0.4, 0, img)
        cv2.putText(img, st, (sx, sy), font, 0.5, (200, 200, 200), 1, cv2.LINE_AA)

    if lidar_stop:
        ov4 = img.copy()
        cv2.rectangle(ov4, (w - 130, 10), (w - 10, 45), (0, 0, 200), -1)
        cv2.addWeighted(ov4, 0.7, img, 0.3, 0, img)
        cv2.putText(img, "LIDAR STOP", (w - 125, 36), font, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    if data:
        iy = h - 50
        ov5 = img.copy()
        cv2.rectangle(ov5, (8, iy - 5), (180, h - 5), (0, 0, 0), -1)
        cv2.addWeighted(ov5, 0.5, img, 0.5, 0, img)
        cv2.putText(img, "L:" + str(int(left_prob * 100)) + "%", (14, iy + 14),
                    font, 0.4, (0, 255, 100), 1, cv2.LINE_AA)
        cv2.putText(img, "R:" + str(int(right_prob * 100)) + "%", (80, iy + 14),
                    font, 0.4, (255, 160, 0), 1, cv2.LINE_AA)
        cv2.putText(img, str(int(fps)) + "fps", (14, iy + 32),
                    font, 0.35, (120, 120, 120), 1, cv2.LINE_AA)


def draw_no_signal(img):
    h, w = img.shape[:2]
    cv2.putText(img, "NO CAMERA", (w // 2 - 100, h // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2, cv2.LINE_AA)

def draw_horizon_line(img):
    h, w = img.shape[:2]
    y = int(h * CAM_HORIZON)
    dash_len = 20
    gap_len = 10
    x = 0
    while x < w:
        x2 = min(x + dash_len, w)
        cv2.line(img, (x, y), (x2, y), (255, 255, 0), 1, cv2.LINE_AA)
        x = x2 + gap_len
    font = cv2.FONT_HERSHEY_SIMPLEX
    label = "HORIZON " + str(int(CAM_HORIZON * 100)) + "%"
    cv2.putText(img, label, (w - 150, y - 6), font, 0.4, (255, 255, 0), 1, cv2.LINE_AA)


# main render loop that builds the overlay frame
def run(fps):
    print("[overlay] Starting at " + str(fps) + " fps")
    print("[overlay] Camera: height=" + str(CAM_HEIGHT) + "m focal=" +
          str(CAM_FOCAL) + " horizon=" + str(CAM_HORIZON))
    period = 1.0 / fps
    frame_count = 0
    fps_actual = 0.0
    t_start = time.time()

    while True:
        t0 = time.time()

        engaged = read_file(ENGAGE_FILE) == "1"
        lane_follow = read_file(LANE_FOLLOW_FILE) == "1"
        exp_auto = read_file(EXP_AUTO_FILE) == "1"
        lidar_stop = read_file(LIDAR_STOP_FILE) == "1"

        active = engaged and (lane_follow or exp_auto)
        if lane_follow:
            mode_name = "LANE FOLLOW"
        elif exp_auto:
            mode_name = "EXP AUTO"
        else:
            mode_name = None

        frame = None
        try:
            if os.path.exists(CAMERA_FRAME):
                age = time.time() - os.path.getmtime(CAMERA_FRAME)
                if age < 3.0:
                    frame = cv2.imread(CAMERA_FRAME)
        except Exception:
            pass

        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            draw_no_signal(frame)
        else:
            frame = cv2.resize(frame, (640, 480))

        data = read_model_output()

        if data and len(data.get("plan_positions", [])) > 0:
            draw_path_corridor(frame, data["plan_positions"], active)
            if "lane_lines" in data and len(data["lane_lines"]) == 4:
                draw_lane_lines(frame, data["lane_lines"])

        if active:
            draw_green_border(frame)

        draw_hud(frame, data or {}, mode_name, lidar_stop, fps_actual)

        draw_horizon_line(frame)

        try:
            tmp = OVERLAY_FRAME.replace(".jpg", "_tmp.jpg")
            cv2.imwrite(tmp, frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            os.rename(tmp, OVERLAY_FRAME)
        except Exception as e:
            if frame_count % 100 == 0:
                print("[overlay] Write error: " + str(e))

        frame_count += 1
        elapsed_total = time.time() - t_start
        if elapsed_total > 0:
            fps_actual = frame_count / elapsed_total

        if frame_count % max(1, int(fps * 5)) == 0:
            dt_frame = time.time() - t0
            print("[overlay] #" + str(frame_count) + " " +
                  str(round(fps_actual, 1)) + "fps" +
                  " (" + str(int(dt_frame * 1000)) + "ms/f)" +
                  (" model" if data else " no_model") +
                  (" " + mode_name if mode_name else ""))

        dt = time.time() - t0
        if dt < period:
            time.sleep(period - dt)


def main():
    global CAM_HEIGHT, CAM_FOCAL, CAM_HORIZON

    parser = argparse.ArgumentParser(description="Overlay Stream, openpilot display renderer")
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS)
    parser.add_argument("--cam-height", type=float, default=CAM_HEIGHT)
    parser.add_argument("--cam-focal", type=float, default=CAM_FOCAL)
    parser.add_argument("--cam-horizon", type=float, default=CAM_HORIZON)
    args = parser.parse_args()

    CAM_HEIGHT = args.cam_height
    CAM_FOCAL = args.cam_focal
    CAM_HORIZON = args.cam_horizon

    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    try:
        run(args.fps)
    finally:
        try:
            os.remove(OVERLAY_FRAME)
        except Exception:
            pass
        print("[overlay] Stopped.")


if __name__ == "__main__":
    main()
