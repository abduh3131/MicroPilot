#!/usr/bin/env python3
"""offline tool that runs supercombo on a video file and renders lanes on top"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

TRT_AVAILABLE = False
ORT_AVAILABLE = False
try:
    import tensorrt as trt
    import pycuda.driver as cuda
    import pycuda.autoinit
    TRT_AVAILABLE = True
except ImportError:
    pass

if not TRT_AVAILABLE:
    try:
        import onnxruntime as ort
        ORT_AVAILABLE = True
    except ImportError:
        pass

if not TRT_AVAILABLE and not ORT_AVAILABLE:
    print("[lane_viz] ERROR: Neither TensorRT nor onnxruntime available")
    sys.exit(1)

ENGINE_PATH = "/home/jetson/openpilotV3/selfdrive/modeld/models/supercombo.engine"
MODEL_PATH = "/home/jetson/openpilotV3/selfdrive/modeld/models/supercombo.onnx"
TRAJECTORY_SIZE = 33
PLAN_MHP_N = 5
FEATURE_LEN = 128
HISTORY_BUFFER_LEN = 99
DESIRE_LEN = 8
STEERING_GAIN = 2.0
MAX_STEER = 0.8

PLAN_OFFSET = 0
PLAN_SIZE = 4955
LANE_LINES_OFFSET = PLAN_SIZE
LANE_LINES_MEAN_SIZE = 4 * TRAJECTORY_SIZE * 2
LANE_LINES_STD_SIZE = 4 * TRAJECTORY_SIZE * 2
LANE_LINES_PROB_SIZE = 4 * 2

X_IDXS = np.array([
    0., 0.1875, 0.75, 1.6875, 3., 4.6875, 6.75, 9.1875, 12.,
    15.1875, 18.75, 22.6875, 27., 31.6875, 36.75, 42.1875, 48.,
    54.1875, 60.75, 67.6875, 75., 82.6875, 90.75, 99.1875, 108.,
    117.1875, 126.75, 136.6875, 147., 157.6875, 168.75, 180.1875, 192.
])

CAMERA_HEIGHT = 1.22


# preprocesses a bgr frame into the 12 plane yuv tensor the model wants
def preprocess_frame(bgr_img):
    img = cv2.resize(bgr_img, (512, 256))
    yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV_I420)
    h, w = 256, 512
    y_plane = yuv[:h, :].astype(np.float32)
    u_plane = yuv[h:h + h // 4, :].reshape(h // 2, w // 2).astype(np.float32)
    v_plane = yuv[h + h // 4:, :].reshape(h // 2, w // 2).astype(np.float32)
    y_tl = y_plane[:128, :256]
    y_tr = y_plane[:128, 256:]
    y_bl = y_plane[128:, :256]
    y_br = y_plane[128:, 256:]
    frame_planes = np.stack([y_tl, y_tr, y_bl, y_br, u_plane, v_plane], axis=0)
    frame_planes = frame_planes / 255.0
    input_imgs = np.concatenate([frame_planes, frame_planes], axis=0)
    return input_imgs.astype(np.float16)


# pulls all 33 lane line points and their probabilities out of the model output
def parse_lane_lines_full(output):
    off = LANE_LINES_OFFSET
    mean_flat = output[off:off + LANE_LINES_MEAN_SIZE]
    mean = mean_flat.reshape(4, TRAJECTORY_SIZE, 2)

    prob_off = off + LANE_LINES_MEAN_SIZE + LANE_LINES_STD_SIZE
    prob_flat = output[prob_off:prob_off + LANE_LINES_PROB_SIZE]
    prob = prob_flat.reshape(4, 2)

    lines = []
    for i in range(4):
        lines.append({
            "y": mean[i, :, 0].copy(),
            "z": mean[i, :, 1].copy(),
            "prob": float(1.0 / (1.0 + np.exp(-prob[i, 1]))),
        })

    close_range = slice(0, 5)
    info = {
        "left_near_y": float(np.mean(mean[1, close_range, 0])),
        "right_near_y": float(np.mean(mean[2, close_range, 0])),
        "left_near_prob": float(1.0 / (1.0 + np.exp(-prob[1, 1]))),
        "right_near_prob": float(1.0 / (1.0 + np.exp(-prob[2, 1]))),
        "left_far_y": float(np.mean(mean[0, close_range, 0])),
        "right_far_y": float(np.mean(mean[3, close_range, 0])),
        "left_far_prob": float(1.0 / (1.0 + np.exp(-prob[0, 1]))),
        "right_far_prob": float(1.0 / (1.0 + np.exp(-prob[3, 1]))),
    }
    return lines, info


# picks the best of the 5 plan hypotheses and returns its xyz points
def parse_plan_full(output):
    pred_size = TRAJECTORY_SIZE * 15 * 2 + 1

    best_idx = 0
    best_prob = -999.0
    for i in range(PLAN_MHP_N):
        prob_offset = PLAN_OFFSET + i * pred_size + pred_size - 1
        p = float(output[prob_offset])
        if p > best_prob:
            best_prob = p
            best_idx = i

    plan_off = PLAN_OFFSET + best_idx * pred_size
    mean_flat = output[plan_off:plan_off + TRAJECTORY_SIZE * 15]
    mean = mean_flat.reshape(TRAJECTORY_SIZE, 15)

    return {
        "positions": mean[:, :3].copy(),
        "path_y": mean[:, 1].copy(),
        "prob": float(1.0 / (1.0 + np.exp(-best_prob))),
    }


def compute_steering(lane_info, plan_info):
    left_prob = max(lane_info["left_near_prob"], lane_info["left_far_prob"])
    right_prob = max(lane_info["right_near_prob"], lane_info["right_far_prob"])
    steering = 0.0
    confidence = 0.0

    if left_prob > 0.3 and right_prob > 0.3:
        left_y = lane_info["left_near_y"] if lane_info["left_near_prob"] > 0.3 else lane_info["left_far_y"]
        right_y = lane_info["right_near_y"] if lane_info["right_near_prob"] > 0.3 else lane_info["right_far_y"]
        lane_center = (left_y + right_y) / 2.0
        steering = float(np.clip(lane_center * STEERING_GAIN, -MAX_STEER, MAX_STEER))
        confidence = min(left_prob, right_prob)
    elif left_prob > 0.3 or right_prob > 0.3:
        if left_prob > right_prob:
            steering = float(np.clip((lane_info["left_near_y"] - 1.5) * STEERING_GAIN, -MAX_STEER, MAX_STEER))
        else:
            steering = float(np.clip((lane_info["right_near_y"] + 1.5) * STEERING_GAIN, -MAX_STEER, MAX_STEER))
        confidence = max(left_prob, right_prob) * 0.6
    elif plan_info["prob"] > 0.3:
        avg_y = float(np.mean(plan_info["path_y"][:5]))
        steering = float(np.clip(avg_y * STEERING_GAIN * 0.5, -MAX_STEER, MAX_STEER))
        confidence = plan_info["prob"] * 0.4

    return steering, confidence


def road_to_pixel(x_fwd, y_lat, img_w, img_h, z=0.0):
    if x_fwd < 2.0:
        return None
    fx = img_w * 1.1
    fy = fx
    cx = img_w / 2.0
    cy = img_h * 0.38
    u = int(cx - fx * y_lat / x_fwd)
    v = int(cy + fy * (CAMERA_HEIGHT - z) / x_fwd)
    if 0 <= u < img_w and 0 <= v < img_h:
        return (u, v)
    return None


def draw_lane_line(img, y_vals, z_vals, color, thickness=3, max_pts=20):
    h, w = img.shape[:2]
    points = []
    for i in range(min(max_pts, len(y_vals))):
        pt = road_to_pixel(X_IDXS[i], y_vals[i], w, h, z_vals[i])
        if pt:
            points.append(pt)
    if len(points) > 1:
        pts = np.array(points, dtype=np.int32)
        cv2.polylines(img, [pts], False, color, thickness, cv2.LINE_AA)


# draws the planned path corridor on the frame
def draw_path_corridor(img, positions, color=(0, 140, 255), alpha=0.25):
    h, w = img.shape[:2]
    left_pts = []
    right_pts = []
    half_w = 0.9

    for i in range(positions.shape[0]):
        x_fwd = positions[i, 0]
        y_lat = positions[i, 1]
        z_up = positions[i, 2]
        if x_fwd < 3.0:
            continue
        pl = road_to_pixel(x_fwd, y_lat + half_w, w, h, z_up)
        pr = road_to_pixel(x_fwd, y_lat - half_w, w, h, z_up)
        pc = road_to_pixel(x_fwd, y_lat, w, h, z_up)
        if pl:
            left_pts.append(pl)
        if pr:
            right_pts.append(pr)

    if len(left_pts) > 2 and len(right_pts) > 2:
        corridor = np.array(left_pts + right_pts[::-1], dtype=np.int32)
        overlay = img.copy()
        cv2.fillPoly(overlay, [corridor], color)
        cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)

    center_pts = []
    for i in range(positions.shape[0]):
        x_fwd = positions[i, 0]
        y_lat = positions[i, 1]
        z_up = positions[i, 2]
        if x_fwd < 3.0:
            continue
        pt = road_to_pixel(x_fwd, y_lat, w, h, z_up)
        if pt:
            center_pts.append(pt)
    if len(center_pts) > 1:
        cv2.polylines(img, [np.array(center_pts, np.int32)], False, color, 2, cv2.LINE_AA)


def draw_steering_arrow(img, steering, confidence):
    h, w = img.shape[:2]
    cx = w // 2
    cy = h - 50

    overlay = img.copy()
    cv2.rectangle(overlay, (cx - 120, cy - 25), (cx + 120, cy + 25), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)
    cv2.rectangle(img, (cx - 120, cy - 25), (cx + 120, cy + 25), (200, 200, 200), 1)

    cv2.line(img, (cx, cy - 15), (cx, cy + 15), (100, 100, 100), 1)

    arrow_len = int(min(abs(steering), 1.0) * 100)
    if arrow_len > 3:
        color = (0, 255, 0) if confidence > 0.3 else (0, 255, 255)
        if steering > 0:
            cv2.arrowedLine(img, (cx, cy), (cx + arrow_len, cy), color, 3, tipLength=0.3)
        else:
            cv2.arrowedLine(img, (cx, cy), (cx - arrow_len, cy), color, 3, tipLength=0.3)
    else:
        cv2.circle(img, (cx, cy), 5, (0, 200, 0), -1)

    cv2.putText(img, f"STEER {steering:+.2f}", (cx - 50, cy + 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)


def draw_confidence_bar(img, x, y, w_bar, h_bar, value, label, color):
    cv2.rectangle(img, (x, y), (x + w_bar, y + h_bar), (60, 60, 60), -1)
    fill_w = int(w_bar * min(value, 1.0))
    if fill_w > 0:
        cv2.rectangle(img, (x, y), (x + fill_w, y + h_bar), color, -1)
    cv2.rectangle(img, (x, y), (x + w_bar, y + h_bar), (150, 150, 150), 1)
    cv2.putText(img, f"{label} {value:.0%}", (x, y - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)


# draws the info box with steering, confidence, lane probs and fps
def draw_hud(img, steering, confidence, lane_info, plan_info, frame_num, fps_actual):
    h, w = img.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX

    overlay = img.copy()
    cv2.rectangle(overlay, (8, 8), (310, 195), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.65, img, 0.35, 0, img)
    cv2.rectangle(img, (8, 8), (310, 195), (0, 200, 200), 1)

    y = 28
    gap = 22

    cv2.putText(img, "OPENPILOT SUPERCOMBO", (16, y), font, 0.55, (0, 255, 255), 1, cv2.LINE_AA)
    y += gap + 4

    s_color = (0, 255, 0) if abs(steering) < 0.3 else (0, 255, 255) if abs(steering) < 0.6 else (0, 100, 255)
    cv2.putText(img, f"Steering: {steering:+.3f}", (16, y), font, 0.48, s_color, 1, cv2.LINE_AA)
    y += gap

    c_color = (0, 255, 0) if confidence > 0.4 else (0, 255, 255) if confidence > 0.2 else (0, 100, 255)
    cv2.putText(img, f"Confidence: {confidence:.2f}", (16, y), font, 0.48, c_color, 1, cv2.LINE_AA)
    y += gap

    lp = lane_info["left_near_prob"]
    rp = lane_info["right_near_prob"]
    cv2.putText(img, f"L lane: {lane_info['left_near_y']:+.2f}m", (16, y), font, 0.43, (0, 255, 100), 1, cv2.LINE_AA)
    cv2.putText(img, f"({lp:.0%})", (200, y), font, 0.38, (0, 255, 100), 1, cv2.LINE_AA)
    y += gap
    cv2.putText(img, f"R lane: {lane_info['right_near_y']:+.2f}m", (16, y), font, 0.43, (255, 160, 0), 1, cv2.LINE_AA)
    cv2.putText(img, f"({rp:.0%})", (200, y), font, 0.38, (255, 160, 0), 1, cv2.LINE_AA)
    y += gap

    path_y = float(np.mean(plan_info["path_y"][:5]))
    cv2.putText(img, f"Path: {path_y:+.2f}m  p={plan_info['prob']:.0%}", (16, y), font, 0.43, (0, 140, 255), 1, cv2.LINE_AA)
    y += gap

    cv2.putText(img, f"Frame {frame_num}  {fps_actual:.1f} fps", (16, y), font, 0.38, (150, 150, 150), 1, cv2.LINE_AA)

    bx = w - 160
    by = 15
    bw = 140
    bh = 14
    draw_confidence_bar(img, bx, by, bw, bh, lp, "L-lane", (0, 255, 100))
    draw_confidence_bar(img, bx, by + 30, bw, bh, rp, "R-lane", (255, 160, 0))
    draw_confidence_bar(img, bx, by + 60, bw, bh, plan_info["prob"], "Path", (0, 140, 255))
    draw_confidence_bar(img, bx, by + 90, bw, bh, confidence, "Overall", (0, 255, 255))


def _trt_dtype_to_np(trt_dtype):
    mapping = {
        trt.DataType.FLOAT: np.float32,
        trt.DataType.HALF: np.float16,
        trt.DataType.INT32: np.int32,
        trt.DataType.INT8: np.int8,
    }
    return mapping.get(trt_dtype, np.float32)


class TRTInference:
    """tensorrt gpu runner."""

    def __init__(self, engine_path):
        logger = trt.Logger(trt.Logger.WARNING)
        with open(engine_path, "rb") as f:
            self.engine = trt.Runtime(logger).deserialize_cuda_engine(f.read())
        self.context = self.engine.create_execution_context()
        self.stream = cuda.Stream()
        self.host_buffers = {}
        self.device_buffers = {}
        self.bindings = [None] * self.engine.num_bindings
        for i in range(self.engine.num_bindings):
            name = self.engine.get_binding_name(i)
            shape = self.engine.get_binding_shape(i)
            dtype = _trt_dtype_to_np(self.engine.get_binding_dtype(i))
            size = 1
            for s in shape:
                size *= s
            host_mem = cuda.pagelocked_empty(size, dtype)
            device_mem = cuda.mem_alloc(host_mem.nbytes)
            self.bindings[i] = int(device_mem)
            self.host_buffers[name] = (host_mem, shape, i)
            self.device_buffers[name] = device_mem

    def run(self, feeds):
        for name, arr in feeds.items():
            host_mem, shape, idx = self.host_buffers[name]
            np.copyto(host_mem, arr.ravel())
            cuda.memcpy_htod_async(self.device_buffers[name], host_mem, self.stream)
        self.context.execute_async_v2(bindings=self.bindings, stream_handle=self.stream.handle)
        out_host, out_shape, _ = self.host_buffers["outputs"]
        cuda.memcpy_dtoh_async(out_host, self.device_buffers["outputs"], self.stream)
        self.stream.synchronize()
        return out_host.reshape(out_shape)


class ORTInference:
    """cpu fallback inference backend."""

    def __init__(self, model_path):
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    def run(self, feeds):
        return self.session.run(None, feeds)[0]


# main runner that loads the model, reads the video, writes the annotated output
def run(video_path, output_path, fps, traffic_conv, max_frames):
    t0 = time.time()
    if TRT_AVAILABLE and os.path.exists(ENGINE_PATH):
        print(f"[lane_viz] Loading TensorRT engine: {ENGINE_PATH}")
        inference = TRTInference(ENGINE_PATH)
        backend = "TensorRT GPU"
    elif ORT_AVAILABLE:
        print(f"[lane_viz] Loading ONNX model (CPU): {MODEL_PATH}")
        inference = ORTInference(MODEL_PATH)
        backend = "ONNX CPU"
    else:
        print("[lane_viz] ERROR: No inference backend")
        sys.exit(1)
    print(f"[lane_viz] {backend} loaded in {time.time() - t0:.1f}s")

    features_buffer = np.zeros((1, HISTORY_BUFFER_LEN, FEATURE_LEN), dtype=np.float16)
    prev_planes = None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[lane_viz] ERROR: Cannot open {video_path}")
        sys.exit(1)

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    vid_fps = cap.get(cv2.CAP_PROP_FPS)

    print(f"[lane_viz] Input: {vid_w}x{vid_h} @ {vid_fps:.1f}fps, {total} frames")
    print(f"[lane_viz] Output: {output_path} @ {fps}fps")
    print(f"[lane_viz] Traffic: {'left-hand' if traffic_conv[1] > 0.5 else 'right-hand'}")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (vid_w, vid_h))
    if not out.isOpened():
        print(f"[lane_viz] ERROR: Cannot create output video")
        sys.exit(1)

    frame_num = 0
    fps_actual = 0.0
    t_start = time.time()

    lane_colors = [
        (0, 180, 0),
        (0, 255, 100),
        (255, 160, 0),
        (200, 100, 0),
    ]

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if max_frames > 0 and frame_num >= max_frames:
            break

        t_frame = time.time()

        current_planes = preprocess_frame(frame)
        if prev_planes is not None:
            input_imgs = np.concatenate([prev_planes[:6], current_planes[:6]], axis=0)
        else:
            input_imgs = current_planes
        prev_planes = current_planes
        input_imgs = input_imgs.reshape(1, 12, 128, 256)

        feeds = {
            "input_imgs": input_imgs,
            "big_input_imgs": input_imgs.copy(),
            "desire": np.zeros((1, 100, DESIRE_LEN), dtype=np.float16),
            "traffic_convention": np.array([traffic_conv], dtype=np.float16),
            "nav_features": np.zeros((1, 256), dtype=np.float16),
            "features_buffer": features_buffer,
        }
        raw_out = inference.run(feeds)
        raw = raw_out[0].astype(np.float32)

        output_size = len(raw) - FEATURE_LEN - 2
        new_feat = raw[output_size:output_size + FEATURE_LEN]
        features_buffer = np.roll(features_buffer, -1, axis=1)
        features_buffer[0, -1, :] = new_feat.astype(np.float16)

        lines, lane_info = parse_lane_lines_full(raw)
        plan_info = parse_plan_full(raw)
        steering, confidence = compute_steering(lane_info, plan_info)

        viz = frame.copy()

        if plan_info["prob"] > 0.15:
            draw_path_corridor(viz, plan_info["positions"])

        for i, line in enumerate(lines):
            if line["prob"] > 0.15:
                thickness = 4 if i in (1, 2) else 2
                draw_lane_line(viz, line["y"], line["z"], lane_colors[i], thickness)

        draw_steering_arrow(viz, steering, confidence)

        elapsed = time.time() - t_start
        if elapsed > 0:
            fps_actual = (frame_num + 1) / elapsed
        draw_hud(viz, steering, confidence, lane_info, plan_info, frame_num, fps_actual)

        out.write(viz)

        frame_num += 1
        dt = time.time() - t_frame
        if frame_num % 10 == 0:
            print(f"[lane_viz] Frame {frame_num}/{total} ({dt:.2f}s/frame) "
                  f"steer={steering:+.3f} conf={confidence:.2f}")

    cap.release()
    out.release()
    total_time = time.time() - t_start
    print(f"\n[lane_viz] Done! {frame_num} frames in {total_time:.1f}s ({frame_num/total_time:.1f} fps)")
    print(f"[lane_viz] Output saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Lane Viz")
    parser.add_argument("video", help="Input video file")
    parser.add_argument("--output", "-o", default="", help="Output video path (default: /tmp/lane_viz_output.mp4)")
    parser.add_argument("--fps", type=float, default=5, help="Output FPS (default: 5)")
    parser.add_argument("--rhd", action="store_true", help="Right-hand drive (left-hand traffic)")
    parser.add_argument("--max-frames", type=int, default=0, help="Max frames to process (0=all)")
    args = parser.parse_args()

    if not args.output:
        args.output = "/tmp/lane_viz_output.mp4"

    if args.rhd:
        traffic_conv = [0.0, 1.0]
    else:
        traffic_conv = [1.0, 0.0]

    run(args.video, args.output, args.fps, traffic_conv, args.max_frames)


if __name__ == "__main__":
    main()
