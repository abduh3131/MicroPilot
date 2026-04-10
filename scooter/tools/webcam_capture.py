#!/usr/bin/env python3
"""grabs frames from the usb webcam and writes them to /tmp/camera_frame.jpg"""

import argparse
import os
import sys
import time

import cv2

FRAME_FILE = "/tmp/camera_frame.jpg"
TMP_FILE = "/tmp/_camera_tmp.jpg"


# main capture loop that opens the v4l2 device and writes jpegs
def run(device, fps, width, height):
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"[webcam] ERROR: Cannot open /dev/video{device}")
        sys.exit(1)

    if width > 0 and height > 0:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    cap.set(cv2.CAP_PROP_FPS, fps)
    # mjpeg so the usb bus doesnt choke
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)

    print(f"[webcam] Camera: /dev/video{device}")
    print(f"[webcam] Resolution: {actual_w}x{actual_h} @ {actual_fps:.0f}fps")
    print(f"[webcam] Target FPS: {fps}")
    print(f"[webcam] Output: {FRAME_FILE}")

    period = 1.0 / fps
    frame_num = 0
    t_start = time.time()
    errors = 0

    while True:
        t0 = time.time()
        ret, frame = cap.read()

        if not ret:
            errors += 1
            if errors > 50:
                print("[webcam] Too many read errors, exiting")
                break
            time.sleep(0.01)
            continue

        errors = 0

        cv2.imwrite(TMP_FILE, frame)
        os.rename(TMP_FILE, FRAME_FILE)

        frame_num += 1
        if frame_num % (fps * 5) == 0:
            elapsed = time.time() - t_start
            actual = frame_num / elapsed if elapsed > 0 else 0
            print(f"[webcam] Frame {frame_num} ({actual:.1f} fps actual)")

        dt = time.time() - t0
        if dt < period:
            time.sleep(period - dt)

    cap.release()
    print("[webcam] Stopped.")


def main():
    parser = argparse.ArgumentParser(description="Webcam Capture")
    parser.add_argument("--device", type=int, default=0, help="Camera device index (default: 0)")
    parser.add_argument("--fps", type=int, default=20, help="Target FPS (default: 20)")
    parser.add_argument("--width", type=int, default=640, help="Width (default: 640)")
    parser.add_argument("--height", type=int, default=480, help="Height (default: 480)")
    args = parser.parse_args()

    run(args.device, args.fps, args.width, args.height)


if __name__ == "__main__":
    main()
