#!/usr/bin/env python3
"""feeds a recorded video through the sidewalk model and renders the overlay to an output video"""
import sys
import os
import time
sys.path.insert(0, "/home/jetson/openpilotV3/tools")

import cv2
import numpy as np
from adapters.sidewalk_adapter import SidewalkAdapter
from overlay_stream import draw_path_corridor, draw_lane_lines, draw_hud, draw_green_border

INPUT_VIDEO = "/home/jetson/testingvideo2.mp4"
OUTPUT_VIDEO = "/home/jetson/model_demo_output.mp4"
STEERING_GAIN = 2.0
CROP = 0.4  # dashcam wide FOV crop

def main():
    # Load model
    print("[demo] Loading sidewalk model...")
    adapter = SidewalkAdapter(steering_gain=STEERING_GAIN)
    adapter.load_model()
    print("[demo] Model loaded!")

    cap = cv2.VideoCapture(INPUT_VIDEO)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Crop center portion (dashcam wide FOV)
    crop_top = int(h * CROP)
    crop_h = h - crop_top
    out_w, out_h = w, crop_h

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(OUTPUT_VIDEO, fourcc, fps, (out_w, out_h))

    print(f"[demo] Input: {INPUT_VIDEO} ({w}x{h} @ {fps}fps, {total} frames)")
    print(f"[demo] Crop top {CROP*100:.0f}% -> output {out_w}x{out_h}")
    print(f"[demo] Output: {OUTPUT_VIDEO}")

    frame_num = 0
    t_start = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Crop top portion (sky/ceiling)
        cropped = frame[crop_top:, :, :]

        # Run model
        try:
            steering, confidence, lane_info, plan_info = adapter.run(cropped)
        except Exception as e:
            print(f"[demo] Frame {frame_num} error: {e}")
            steering, confidence = 0.0, 0.0
            lane_info = {"left_near_y": 0, "right_near_y": 0, "left_near_prob": 0, "right_near_prob": 0, "_full": []}
            plan_info = {"positions": [], "prob": 0.0, "path_y": [0.0]}

        # Draw overlay
        overlay = cropped.copy()

        # Draw path corridor
        positions = plan_info.get("positions", [])
        if positions and len(positions) > 2:
            draw_path_corridor(overlay, positions, active=confidence > 0.1)

        # Draw lane lines
        full_lanes = lane_info.get("_full", [])
        if full_lanes:
            draw_lane_lines(overlay, full_lanes)

        # Draw HUD
        data = {
            "steering": steering,
            "confidence": confidence,
            "left_near_y": lane_info.get("left_near_y", 0),
            "right_near_y": lane_info.get("right_near_y", 0),
            "left_near_prob": lane_info.get("left_near_prob", 0),
            "right_near_prob": lane_info.get("right_near_prob", 0),
            "plan_prob": plan_info.get("prob", 0),
        }
        draw_hud(overlay, data, "SIDEWALK", False, fps)

        # Green border when confident
        if confidence > 0.3:
            draw_green_border(overlay)

        out.write(overlay)
        frame_num += 1

        if frame_num % 30 == 0:
            elapsed = time.time() - t_start
            rate = frame_num / elapsed
            print(f"[demo] Frame {frame_num}/{total} ({rate:.1f} fps) "
                  f"steer={steering:+.3f} conf={confidence:.2f}")

    cap.release()
    out.release()
    elapsed = time.time() - t_start
    print(f"[demo] Done! {frame_num} frames in {elapsed:.1f}s ({frame_num/elapsed:.1f} fps)")
    print(f"[demo] Output saved: {OUTPUT_VIDEO}")

if __name__ == "__main__":
    main()
