"""segformer adapter, labels every pixel and finds the sidewalk to steer along"""

import os
import sys
import time

import cv2
import numpy as np

from .base_adapter import BaseModelAdapter

TRT_AVAILABLE = False
ORT_AVAILABLE = False
try:
    import tensorrt as trt
    import pycuda.driver as cuda
    import pycuda.autoinit
    TRT_AVAILABLE = True
except ImportError:
    pass

try:
    import onnxruntime as ort
    ORT_AVAILABLE = True
except ImportError:
    pass

SEG_ENGINE_PATH = "/home/jetson/openpilotV3/selfdrive/modeld/models/sidewalk_segmentation.engine"
SEG_ONNX_PATH = "/home/jetson/openpilotV3/selfdrive/modeld/models/sidewalk_segmentation.onnx"

MODEL_WIDTH = 1024
MODEL_HEIGHT = 512

CLASS_ROAD = 0
CLASS_SIDEWALK = 1

CAM_HEIGHT = 1.22
CAM_FOCAL = 500.0
CAM_HORIZON = 0.38

X_IDXS = np.array([
    0., 0.1875, 0.75, 1.6875, 3., 4.6875, 6.75, 9.1875, 12.,
    15.1875, 18.75, 22.6875, 27., 31.6875, 36.75, 42.1875, 48.,
    54.1875, 60.75, 67.6875, 75., 82.6875, 90.75, 99.1875, 108.,
    117.1875, 126.75, 136.6875, 147., 157.6875, 168.75, 180.1875, 192.
])

NUM_SCAN_ROWS = 20


# tensorrt inference backend for the seg engine
class TRTSegmentation:

    def __init__(self, engine_path):
        logger = trt.Logger(trt.Logger.WARNING)
        with open(engine_path, "rb") as f:
            self.engine = trt.Runtime(logger).deserialize_cuda_engine(f.read())
        self.context = self.engine.create_execution_context()
        self.stream = cuda.Stream()

        self.host_inputs = {}
        self.host_outputs = {}
        self.device_inputs = {}
        self.device_outputs = {}
        self.bindings = []
        self.output_name = None
        self.output_shape = None

        for i in range(self.engine.num_bindings):
            name = self.engine.get_binding_name(i)
            shape = self.engine.get_binding_shape(i)
            dtype_trt = self.engine.get_binding_dtype(i)

            dtype_map = {
                trt.DataType.FLOAT: np.float32,
                trt.DataType.HALF: np.float16,
                trt.DataType.INT32: np.int32,
                trt.DataType.INT8: np.int8,
            }
            dtype = dtype_map.get(dtype_trt, np.float32)

            size = 1
            for s in shape:
                size *= s

            host_mem = cuda.pagelocked_empty(size, dtype)
            device_mem = cuda.mem_alloc(host_mem.nbytes)
            self.bindings.append(int(device_mem))

            if self.engine.binding_is_input(i):
                self.host_inputs[name] = (host_mem, shape)
                self.device_inputs[name] = device_mem
            else:
                self.host_outputs[name] = (host_mem, shape)
                self.device_outputs[name] = device_mem
                self.output_name = name
                self.output_shape = shape

    def run(self, input_tensor):
        input_name = list(self.host_inputs.keys())[0]
        host_mem, shape = self.host_inputs[input_name]

        np.copyto(host_mem, input_tensor.ravel())
        cuda.memcpy_htod_async(self.device_inputs[input_name], host_mem, self.stream)

        self.context.execute_async_v2(bindings=self.bindings, stream_handle=self.stream.handle)

        out_host, out_shape = self.host_outputs[self.output_name]
        cuda.memcpy_dtoh_async(out_host, self.device_outputs[self.output_name], self.stream)
        self.stream.synchronize()

        return out_host.reshape(out_shape)


# onnx runtime fallback when tensorrt is not available
class ORTSegmentation:

    def __init__(self, model_path):
        providers = ["CPUExecutionProvider"]
        try:
            available = ort.get_available_providers()
            if "CUDAExecutionProvider" in available:
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        except Exception:
            pass
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape

    def run(self, input_tensor):
        outputs = self.session.run(None, {self.input_name: input_tensor})
        return outputs[0]


# the actual adapter that turns segmentation masks into steering commands
class SidewalkAdapter(BaseModelAdapter):

    def __init__(self, engine_path=None, onnx_path=None, steering_gain=2.0,
                 target_class=CLASS_SIDEWALK, include_road=False):
        self.engine_path = engine_path or SEG_ENGINE_PATH
        self.onnx_path = onnx_path or SEG_ONNX_PATH
        self.steering_gain = steering_gain
        self.max_steer = 0.8
        self.target_class = target_class
        self.include_road = include_road

        self.inference = None
        self.backend = None

    def load_model(self):
        t0 = time.time()

        if TRT_AVAILABLE and os.path.exists(self.engine_path):
            print(f"[sidewalk] Loading TensorRT engine: {self.engine_path}")
            self.inference = TRTSegmentation(self.engine_path)
            self.backend = "TensorRT GPU"
        elif ORT_AVAILABLE and os.path.exists(self.onnx_path):
            print(f"[sidewalk] Loading ONNX model: {self.onnx_path}")
            self.inference = ORTSegmentation(self.onnx_path)
            self.backend = "ONNX Runtime"
            shape = self.inference.input_shape
            if len(shape) == 4:
                h = shape[2] if isinstance(shape[2], int) else MODEL_HEIGHT
                w = shape[3] if isinstance(shape[3], int) else MODEL_WIDTH
                self._model_input_hw = (h, w)
                print(f"[sidewalk] Model input size: {w}x{h}")
        else:
            raise RuntimeError(
                f"No model file found.\n"
                f"  TRT: {self.engine_path} (exists={os.path.exists(self.engine_path)})\n"
                f"  ONNX: {self.onnx_path} (exists={os.path.exists(self.onnx_path)})\n"
                f"  Run setup_sidewalk_model.py first to download the model."
            )

        target_name = "sidewalk" if self.target_class == CLASS_SIDEWALK else "road"
        if self.include_road:
            target_name = "sidewalk+road"
        print(f"[sidewalk] {self.backend} loaded in {time.time()-t0:.1f}s (target: {target_name})")
        return self.backend

    def _preprocess_frame(self, bgr_img):
        input_w, input_h = MODEL_WIDTH, MODEL_HEIGHT
        if hasattr(self, '_model_input_hw'):
            input_h, input_w = self._model_input_hw

        img = cv2.resize(bgr_img, (input_w, input_h))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img = img.astype(np.float32) / 255.0
        img = (img - mean) / std

        img = img.transpose(2, 0, 1)
        img = np.expand_dims(img, axis=0)

        return img.astype(np.float32)

    def _get_driveable_mask(self, model_output):
        if model_output.ndim == 4:
            class_map = np.argmax(model_output[0], axis=0)
        elif model_output.ndim == 3:
            class_map = model_output[0].astype(np.int32)
        else:
            class_map = model_output.astype(np.int32)

        mask = (class_map == self.target_class)

        if self.include_road:
            mask = mask | (class_map == CLASS_ROAD)

        return mask, class_map

    # scans horizontal strips of the mask and converts edges to meters
    def _mask_to_edges_and_path(self, mask, img_w=640, img_h=480):
        mask_h, mask_w = mask.shape

        scale_x = img_w / mask_w
        scale_y = img_h / mask_h

        horizon_y = int(img_h * CAM_HORIZON)

        scan_start = int(img_h * 0.95)
        scan_end = horizon_y + int(img_h * 0.05)

        if scan_start <= scan_end:
            return [], [], []

        scan_rows_px = np.linspace(scan_start, scan_end, NUM_SCAN_ROWS, dtype=int)

        left_edges = []
        right_edges = []
        center_path = []

        cx = img_w * 0.5

        for row_px in scan_rows_px:
            mask_row = int(row_px / scale_y)
            mask_row = max(0, min(mask_h - 1, mask_row))

            row_data = mask[mask_row, :]
            sidewalk_cols = np.where(row_data)[0]

            if len(sidewalk_cols) < 3:
                continue

            left_col = sidewalk_cols[0]
            right_col = sidewalk_cols[-1]

            left_px = left_col * scale_x
            right_px = right_col * scale_x
            center_px = (left_px + right_px) / 2.0

            cy = img_h * CAM_HORIZON

            v = row_px
            denom = v - cy
            if denom < 1.0:
                continue

            x_fwd = CAM_FOCAL * CAM_HEIGHT / denom

            if x_fwd < 0.5 or x_fwd > 80.0:
                continue

            y_left = (cx - left_px) * x_fwd / CAM_FOCAL
            y_right = (cx - right_px) * x_fwd / CAM_FOCAL
            y_center = (cx - center_px) * x_fwd / CAM_FOCAL

            left_edges.append((x_fwd, y_left))
            right_edges.append((x_fwd, y_right))
            center_path.append([x_fwd, y_center, 0.0])

        return left_edges, right_edges, center_path

    def _build_lane_info(self, left_edges, right_edges):
        empty_line = {"y": [0.0] * 33, "z": [0.0] * 33, "prob": 0.0}
        lane_info = {
            "left_far_y": 0.0, "left_near_y": 0.0,
            "right_near_y": 0.0, "right_far_y": 0.0,
            "left_far_prob": 0.0, "left_near_prob": 0.0,
            "right_near_prob": 0.0, "right_far_prob": 0.0,
            "_full": [dict(empty_line), dict(empty_line), dict(empty_line), dict(empty_line)],
        }

        if len(left_edges) < 2 and len(right_edges) < 2:
            return lane_info

        def edges_to_33_points(edges):
            if len(edges) < 2:
                return [0.0] * 33
            x_vals = [e[0] for e in edges]
            y_vals = [e[1] for e in edges]
            return np.interp(X_IDXS, x_vals, y_vals, left=y_vals[0], right=y_vals[-1]).tolist()

        if len(left_edges) >= 2:
            left_y_33 = edges_to_33_points(left_edges)
            close_avg = np.mean([e[1] for e in left_edges[:3]])
            prob = min(1.0, len(left_edges) / (NUM_SCAN_ROWS * 0.5))

            lane_info["left_near_y"] = float(close_avg)
            lane_info["left_near_prob"] = float(prob)
            lane_info["_full"][1] = {"y": left_y_33, "z": [0.0] * 33, "prob": float(prob)}

        if len(right_edges) >= 2:
            right_y_33 = edges_to_33_points(right_edges)
            close_avg = np.mean([e[1] for e in right_edges[:3]])
            prob = min(1.0, len(right_edges) / (NUM_SCAN_ROWS * 0.5))

            lane_info["right_near_y"] = float(close_avg)
            lane_info["right_near_prob"] = float(prob)
            lane_info["_full"][2] = {"y": right_y_33, "z": [0.0] * 33, "prob": float(prob)}

        return lane_info

    def _build_plan_info(self, center_path):
        if len(center_path) < 2:
            return {
                "positions": [[float(X_IDXS[i]), 0.0, 0.0] for i in range(33)],
                "path_y": np.zeros(33),
                "prob": 0.0,
            }

        x_vals = [p[0] for p in center_path]
        y_vals = [p[1] for p in center_path]

        y_33 = np.interp(X_IDXS, x_vals, y_vals, left=y_vals[0], right=y_vals[-1])

        positions = [[float(X_IDXS[i]), float(y_33[i]), 0.0] for i in range(33)]

        prob = min(1.0, len(center_path) / (NUM_SCAN_ROWS * 0.4))

        return {
            "positions": positions,
            "path_y": y_33,
            "prob": float(prob),
        }

    def _compute_steering(self, lane_info, plan_info):
        left_prob = lane_info["left_near_prob"]
        right_prob = lane_info["right_near_prob"]

        steering = 0.0
        confidence = 0.0

        if left_prob > 0.3 and right_prob > 0.3:
            lane_center = (lane_info["left_near_y"] + lane_info["right_near_y"]) / 2.0
            steering = np.clip(lane_center * self.steering_gain, -self.max_steer, self.max_steer)
            confidence = min(left_prob, right_prob)

        elif left_prob > 0.3 or right_prob > 0.3:
            if left_prob > right_prob:
                steering = np.clip((lane_info["left_near_y"] - 0.8) * self.steering_gain,
                                   -self.max_steer, self.max_steer)
            else:
                steering = np.clip((lane_info["right_near_y"] + 0.8) * self.steering_gain,
                                   -self.max_steer, self.max_steer)
            confidence = max(left_prob, right_prob) * 0.6

        elif plan_info["prob"] > 0.3:
            avg_y = float(np.mean(plan_info["path_y"][:5]))
            steering = np.clip(avg_y * self.steering_gain * 0.5, -self.max_steer, self.max_steer)
            confidence = plan_info["prob"] * 0.4

        return float(steering), float(confidence)

    # full frame pipeline from input image to steering command
    def run(self, bgr_frame):
        if self.inference is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        input_tensor = self._preprocess_frame(bgr_frame)

        raw_output = self.inference.run(input_tensor)

        mask, class_map = self._get_driveable_mask(raw_output)

        h, w = bgr_frame.shape[:2]
        left_edges, right_edges, center_path = self._mask_to_edges_and_path(mask, img_w=w, img_h=h)

        lane_info = self._build_lane_info(left_edges, right_edges)
        plan_info = self._build_plan_info(center_path)

        steering, confidence = self._compute_steering(lane_info, plan_info)

        return steering, confidence, lane_info, plan_info
