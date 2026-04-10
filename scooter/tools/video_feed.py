#!/usr/bin/env python3
"""plays video file into /tmp/camera_frame for testing videos without cam"""

import argparse
import os
import sys
import time

import cv2

FRAME_FILE = "/tmp/camera_frame.jpg"


def run(video_path, fps, loop, flip):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("[video_feed] ERROR: Cannot open " + video_path)
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print("[video_feed] Playing: " + video_path)
    print("[video_feed] Video: " + str(width) + "x" + str(height) +
          " @ " + str(round(video_fps, 1)) + "fps, " + str(total_frames) + " frames")
    print("[video_feed] Output FPS: " + str(fps) +
          ", Loop: " + str(loop) + ", Flip: " + str(flip))

    period = 1.0 / fps
    frame_num = 0

    while True:
        t0 = time.time()
        ret, frame = cap.read()

        if not ret:
            if loop:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                print("[video_feed] Looping back to start...")
                continue
            else:
                print("[video_feed] Video ended after " + str(frame_num) + " frames")
                break

        if flip:
            frame = cv2.flip(frame, 1)

        # writes the current frame so lane_follow can pick it up
        cv2.imwrite(FRAME_FILE, frame)

        frame_num += 1
        if frame_num % max(1, int(fps * 5)) == 0:
            print("[video_feed] Frame " + str(frame_num) + "/" + str(total_frames))

        elapsed = time.time() - t0
        if elapsed < period:
            time.sleep(period - elapsed)

    cap.release()
    print("[video_feed] Done.")


def main():
    parser = argparse.ArgumentParser(description="Video Feed")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--fps", type=float, default=10, help="Output FPS (default: 10)")
    parser.add_argument("--loop", action="store_true", help="Loop the video")
    parser.add_argument("--flip", action="store_true", help="Flip horizontally (mirror)")
    args = parser.parse_args()

    run(args.video, args.fps, args.loop, args.flip)


if __name__ == "__main__":
    main()
