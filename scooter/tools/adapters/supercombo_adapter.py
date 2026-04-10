"""openpilots supercombo road model adapter, takes yuv frames and outputs lane lines and steering"""

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

if not TRT_AVAILABLE:
    try:
        import onnxruntime as ort
        ORT_AVAILABLE = True
    except ImportError:
        pass

TRAJECTORY_SIZE = 33
PLAN_MHP_N = 5
FEATURE_LEN = 128
HISTORY_BUFFER_LEN = 99
DESIRE_LEN = 8

PLAN_OFFSET = 0
PLAN_SIZE = 4955
LANE_LINES_OFFSET = PLAN_SIZE
LANE_LINES_MEAN_SIZE = 4 * TRAJECTORY_SIZE * 2
LANE_LINES_STD_SIZE = 4 * TRAJECTORY_SIZE * 2
LANE_LINES_PROB_SIZE = 4 * 2

ENGINE_PATH = "/home/jetson/openpilotV3/selfdrive/modeld/models/supercombo.engine"
ONNX_PATH = "/home/jetson/openpilotV3/selfdrive/modeld/models/supercombo.onnx"


def _trt_dtype_to_np(trt_dtype):
    mapping = {
        trt.DataType.FLOAT: np.float32,
        trt.DataType.HALF: np.float16,
        trt.DataType.INT32: np.int32,
        trt.DataType.INT8: np.int8,
    }
    return mapping.get(trt_dtype, np.float32)


# tensorrt backend that loads the supercombo engine and runs it on gpu
class TRTInference:

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

        out_host, out_shape, out_idx = self.host_buffers["outputs"]
        cuda.memcpy_dtoh_async(out_host, self.device_buffers["outputs"], self.stream)

        self.stream.synchronize()

        return out_host.reshape(out_shape)


# onnx cpu fallback used when tensorrt is missing
class ORTInference:

    def __init__(self, model_path):
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    def run(self, feeds):
        outputs = self.session.run(None, feeds)
        return outputs[0]


# adapter that wraps supercombo with preprocessing and output parsing
class SupercomboAdapter(BaseModelAdapter):

    def __init__(self, engine_path=None, onnx_path=None, steering_gain=2.0):
        self.engine_path = engine_path or ENGINE_PATH
        self.onnx_path = onnx_path or ONNX_PATH
        self.steering_gain = steering_gain
        self.max_steer = 0.8

        self.inference = None
        self.backend = None

        self.features_buffer = np.zeros((1, HISTORY_BUFFER_LEN, FEATURE_LEN), dtype=np.float16)

        self.prev_frame = None

    def load_model(self):
        t0 = time.time()

        if TRT_AVAILABLE and os.path.exists(self.engine_path):
            print(f"[supercombo] Loading TensorRT engine: {self.engine_path}")
            self.inference = TRTInference(self.engine_path)
            self.backend = "TensorRT GPU"
        elif ORT_AVAILABLE:
            print(f"[supercombo] Loading ONNX model (CPU): {self.onnx_path}")
            self.inference = ORTInference(self.onnx_path)
            self.backend = "ONNX CPU"
        else:
            raise RuntimeError("No inference backend available (need TensorRT or onnxruntime)")

        print(f"[supercombo] {self.backend} loaded in {time.time()-t0:.1f}s")
        return self.backend

    # resizes and converts bgr into the 6 plane yuv tensor supercombo expects
    def _preprocess_frame(self, bgr_img):
        img = cv2.resize(bgr_img, (512, 256))

        yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV_I420)

        h, w = 256, 512

        y_plane = yuv[:h, :].astype(np.float32)
        u_plane = yuv[h:h + h // 4, :].reshape(h // 2, w // 2).astype(np.float32)
        v_plane = yuv[h + h // 4:, :].reshape(h // 2, w // 2).astype(np.float32)

        # y channel must be subsampled not quadrant cropped, do not divide by 255
        y_0 = y_plane[0::2, 0::2]
        y_1 = y_plane[1::2, 0::2]
        y_2 = y_plane[0::2, 1::2]
        y_3 = y_plane[1::2, 1::2]

        frame_planes = np.stack([y_0, y_1, y_2, y_3, u_plane, v_plane], axis=0)

        input_imgs = np.concatenate([frame_planes, frame_planes], axis=0)

        return input_imgs.astype(np.float16)

    def _parse_lane_lines(self, output):
        off = LANE_LINES_OFFSET

        mean_flat = output[off:off + LANE_LINES_MEAN_SIZE]
        mean = mean_flat.reshape(4, TRAJECTORY_SIZE, 2)

        prob_off = off + LANE_LINES_MEAN_SIZE + LANE_LINES_STD_SIZE
        prob_flat = output[prob_off:prob_off + LANE_LINES_PROB_SIZE]
        prob = prob_flat.reshape(4, 2)

        close_range = slice(0, 5)
        lane_info = {
            "left_far_y": float(np.mean(mean[0, close_range, 0])),
            "left_near_y": float(np.mean(mean[1, close_range, 0])),
            "right_near_y": float(np.mean(mean[2, close_range, 0])),
            "right_far_y": float(np.mean(mean[3, close_range, 0])),
            "left_far_prob": float(1.0 / (1.0 + np.exp(-prob[0, 1]))),
            "left_near_prob": float(1.0 / (1.0 + np.exp(-prob[1, 1]))),
            "right_near_prob": float(1.0 / (1.0 + np.exp(-prob[2, 1]))),
            "right_far_prob": float(1.0 / (1.0 + np.exp(-prob[3, 1]))),
        }

        lane_lines_full = []
        for i in range(4):
            lane_lines_full.append({
                "y": mean[i, :, 0].tolist(),
                "z": mean[i, :, 1].tolist(),
                "prob": float(1.0 / (1.0 + np.exp(-prob[i, 1]))),
            })
        lane_info["_full"] = lane_lines_full

        return lane_info

    def _parse_plan(self, output):
        pred_size = TRAJECTORY_SIZE * 15 * 2 + 1

        best_idx = 0
        best_prob = -999.0
        for i in range(PLAN_MHP_N):
            prob_offset = PLAN_OFFSET + i * pred_size + pred_size - 1
            prob = float(output[prob_offset])
            if prob > best_prob:
                best_prob = prob
                best_idx = i

        plan_off = PLAN_OFFSET + best_idx * pred_size
        mean_flat = output[plan_off:plan_off + TRAJECTORY_SIZE * 15]
        mean = mean_flat.reshape(TRAJECTORY_SIZE, 15)

        positions_y = mean[:, 1]
        positions_xyz = mean[:, :3]

        return {
            "path_y": positions_y,
            "positions": positions_xyz.tolist(),
            "prob": float(1.0 / (1.0 + np.exp(-best_prob))),
        }

    def _compute_steering(self, lane_info, plan_info):
        left_prob = max(lane_info["left_near_prob"], lane_info.get("left_far_prob", 0))
        right_prob = max(lane_info["right_near_prob"], lane_info.get("right_far_prob", 0))

        steering = 0.0
        confidence = 0.0

        if left_prob > 0.3 and right_prob > 0.3:
            left_y = lane_info["left_near_y"] if lane_info["left_near_prob"] > 0.3 else lane_info.get("left_far_y", 0)
            right_y = lane_info["right_near_y"] if lane_info["right_near_prob"] > 0.3 else lane_info.get("right_far_y", 0)
            lane_center = (left_y + right_y) / 2.0
            steering = np.clip(lane_center * self.steering_gain, -self.max_steer, self.max_steer)
            confidence = min(left_prob, right_prob)

        elif left_prob > 0.3 or right_prob > 0.3:
            if left_prob > right_prob:
                steering = np.clip((lane_info["left_near_y"] - 1.5) * self.steering_gain,
                                   -self.max_steer, self.max_steer)
            else:
                steering = np.clip((lane_info["right_near_y"] + 1.5) * self.steering_gain,
                                   -self.max_steer, self.max_steer)
            confidence = max(left_prob, right_prob) * 0.6

        elif plan_info["prob"] > 0.3:
            avg_y = float(np.mean(plan_info["path_y"][:5]))
            steering = np.clip(avg_y * self.steering_gain * 0.5, -self.max_steer, self.max_steer)
            confidence = plan_info["prob"] * 0.4

        return float(steering), float(confidence)

    # one full model tick from a bgr frame to steering and confidence
    def run(self, bgr_frame):
        if self.inference is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        current_planes = self._preprocess_frame(bgr_frame)

        if self.prev_frame is not None:
            input_imgs = np.concatenate([self.prev_frame[:6], current_planes[:6]], axis=0)
        else:
            input_imgs = current_planes
        self.prev_frame = current_planes

        input_imgs = input_imgs.reshape(1, 12, 128, 256)

        feeds = {
            "input_imgs": input_imgs,
            "big_input_imgs": input_imgs.copy(),
            "desire": np.zeros((1, 100, DESIRE_LEN), dtype=np.float16),
            "traffic_convention": np.array([[1.0, 0.0]], dtype=np.float16),
            "nav_features": np.zeros((1, 256), dtype=np.float16),
            "features_buffer": self.features_buffer,
        }

        raw_output = self.inference.run(feeds)[0].astype(np.float32)

        output_size = len(raw_output) - FEATURE_LEN - 2
        new_features = raw_output[output_size:output_size + FEATURE_LEN]
        self.features_buffer = np.roll(self.features_buffer, -1, axis=1)
        self.features_buffer[0, -1, :] = new_features.astype(np.float16)

        lane_info = self._parse_lane_lines(raw_output)
        plan_info = self._parse_plan(raw_output)

        steering, confidence = self._compute_steering(lane_info, plan_info)

        return steering, confidence, lane_info, plan_info
