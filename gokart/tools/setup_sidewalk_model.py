#!/usr/bin/env python3
"""one time setup that downloads the segformer sidewalk model and optionally builds a tensorrt engine"""

import argparse
import os
import sys
import subprocess
import urllib.request
import time

MODEL_DIR = "/home/jetson/openpilotV3/selfdrive/modeld/models"
ONNX_FILENAME = "sidewalk_segmentation.onnx"
ENGINE_FILENAME = "sidewalk_segmentation.engine"

ONNX_URL = "https://huggingface.co/Xenova/segformer-b0-finetuned-cityscapes-1024-1024/resolve/main/onnx/model.onnx"


# downloads the onnx model file
def download_model(output_dir, filename):
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[setup] Model already exists: {output_path} ({size_mb:.1f} MB)")
        return output_path

    print(f"[setup] Downloading SegFormer B0 Cityscapes model")
    print(f"[setup] URL: {ONNX_URL}")
    print(f"[setup] Saving to: {output_path}")

    try:
        def progress(count, block_size, total_size):
            percent = int(count * block_size * 100 / total_size)
            mb_done = count * block_size / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            sys.stdout.write(f"\r[setup] Downloading: {percent}% ({mb_done:.1f}/{mb_total:.1f} MB)")
            sys.stdout.flush()

        urllib.request.urlretrieve(ONNX_URL, output_path, reporthook=progress)
        print()

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[setup] Download complete: {size_mb:.1f} MB")
        return output_path

    except Exception as e:
        print(f"\n[setup] ERROR downloading model: {e}")
        print(f"[setup] Manual download available at: {ONNX_URL}")
        print(f"[setup] Place the file at: {output_path}")

        print(f"\n[setup] Alternative export using HuggingFace optimum:")
        print(f"  pip install optimum[onnxruntime] transformers")
        print(f"  optimum-cli export onnx --model nvidia/segformer-b0-finetuned-cityscapes-1024-1024 /tmp/segformer_onnx/")
        print(f"  cp /tmp/segformer_onnx/model.onnx {output_path}")
        return None


# quick sanity test on the model
def test_model(onnx_path, test_image_path=None):
    try:
        import onnxruntime as ort
        import numpy as np
    except ImportError:
        print("[setup] ERROR: onnxruntime not installed. Run: pip install onnxruntime")
        return False

    print(f"\n[setup] Testing model: {onnx_path}")

    t0 = time.time()
    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    print(f"[setup] Model loaded in {time.time()-t0:.2f}s")

    print(f"\n[setup] Model inputs:")
    for inp in session.get_inputs():
        print(f"  {inp.name}: shape={inp.shape}, type={inp.type}")

    print(f"\n[setup] Model outputs:")
    for out in session.get_outputs():
        print(f"  {out.name}: shape={out.shape}, type={out.type}")

    input_info = session.get_inputs()[0]
    input_name = input_info.name

    shape = input_info.shape
    batch = shape[0] if isinstance(shape[0], int) else 1
    channels = shape[1] if isinstance(shape[1], int) else 3
    height = shape[2] if isinstance(shape[2], int) else 512
    width = shape[3] if isinstance(shape[3], int) else 1024

    if test_image_path and os.path.exists(test_image_path):
        import cv2
        img = cv2.imread(test_image_path)
        img = cv2.resize(img, (width, height))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img = img.astype(np.float32) / 255.0
        img = (img - mean) / std
        input_tensor = img.transpose(2, 0, 1).reshape(1, 3, height, width).astype(np.float32)
        print(f"\n[setup] Using test image: {test_image_path}")
    else:
        input_tensor = np.random.randn(batch, channels, height, width).astype(np.float32)
        print(f"\n[setup] Using random test image (shape: {input_tensor.shape})")

    t0 = time.time()
    outputs = session.run(None, {input_name: input_tensor})
    inference_time = time.time() - t0

    output = outputs[0]
    print(f"\n[setup] Inference completed in {inference_time*1000:.1f}ms")
    print(f"[setup] Output shape: {output.shape}")

    if output.ndim == 4:
        num_classes = output.shape[1]
        class_map = np.argmax(output[0], axis=0)
        print(f"[setup] Number of classes: {num_classes}")
    elif output.ndim == 3:
        class_map = output[0].astype(np.int32)
    else:
        class_map = output.astype(np.int32)

    class_names = [
        "road", "sidewalk", "building", "wall", "fence",
        "pole", "traffic_light", "traffic_sign", "vegetation", "terrain",
        "sky", "person", "rider", "car", "truck",
        "bus", "train", "motorcycle", "bicycle"
    ]

    unique_classes = np.unique(class_map)
    print(f"\n[setup] Classes detected in test image:")
    for c in unique_classes:
        if c < len(class_names):
            count = np.sum(class_map == c)
            pct = count / class_map.size * 100
            marker = " TARGET" if c == 1 else ""
            print(f"  Class {c:2d} ({class_names[c]:15s}): {pct:5.1f}% of pixels{marker}")

    sidewalk_pct = np.sum(class_map == 1) / class_map.size * 100
    if test_image_path:
        print(f"\n[setup] Sidewalk coverage: {sidewalk_pct:.1f}%")
        if sidewalk_pct > 1.0:
            print("[setup] Sidewalk detected successfully")
        else:
            print("[setup] Very little sidewalk detected, normal for non sidewalk images")

    print(f"\n[setup] Model is working correctly")
    print(f"[setup] Estimated speed: {1000/inference_time:.0f} fps on cpu, faster with tensorrt")
    return True


# builds a tensorrt engine from the onnx file
def convert_to_trt(onnx_path, engine_path, fp16=True):
    print(f"\n[setup] Converting ONNX to TensorRT engine")
    print(f"[setup] Input:  {onnx_path}")
    print(f"[setup] Output: {engine_path}")
    print(f"[setup] FP16: {fp16}")
    print(f"[setup] This will take 5 to 15 minutes")

    cmd = [
        "trtexec",
        f"--onnx={onnx_path}",
        f"--saveEngine={engine_path}",
        "--workspace=2048",
    ]

    if fp16:
        cmd.append("--fp16")

    cmd.append("--shapes=pixel_values:1x3x512x1024")

    print(f"[setup] Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode == 0:
            size_mb = os.path.getsize(engine_path) / (1024 * 1024)
            print(f"\n[setup] TensorRT engine created: {engine_path} ({size_mb:.1f} MB)")
            return True
        else:
            print(f"\n[setup] TensorRT conversion failed")
            print(result.stderr[-500:] if result.stderr else "No error output")
            print(f"\n[setup] The ONNX model still works fine with ONNX Runtime instead")
            print(f"[setup] Try running with: python3 lane_follow.py --model sidewalk")
            return False
    except FileNotFoundError:
        print(f"\n[setup] trtexec not found, TensorRT not installed on this machine")
        print(f"[setup] Run this script on the Jetson to convert to TensorRT")
        print(f"[setup] The ONNX model still works with ONNX Runtime")
        return False
    except subprocess.TimeoutExpired:
        print(f"\n[setup] TensorRT conversion timed out after 30 minutes")
        return False


def main():
    parser = argparse.ArgumentParser(description="Setup sidewalk segmentation model")
    parser.add_argument("--output-dir", type=str, default=MODEL_DIR,
                        help=f"Directory to save model files (default: {MODEL_DIR})")
    parser.add_argument("--convert-trt", action="store_true",
                        help="Convert ONNX to TensorRT after download, run on Jetson")
    parser.add_argument("--test-image", type=str, default=None,
                        help="Path to a test image to verify the model")
    parser.add_argument("--fp32", action="store_true",
                        help="Use FP32 for TensorRT, default is FP16 for speed")
    args = parser.parse_args()

    print("Sidewalk Model Setup")
    print("Model: SegFormer B0 NVIDIA Cityscapes")

    onnx_path = download_model(args.output_dir, ONNX_FILENAME)
    if onnx_path is None:
        sys.exit(1)

    if not test_model(onnx_path, args.test_image):
        print("\n[setup] Model test failed")
        sys.exit(1)

    if args.convert_trt:
        engine_path = os.path.join(args.output_dir, ENGINE_FILENAME)
        convert_to_trt(onnx_path, engine_path, fp16=not args.fp32)

    print("\nSetup Complete")
    print(f"\n  ONNX model: {onnx_path}")
    if args.convert_trt:
        engine_path = os.path.join(args.output_dir, ENGINE_FILENAME)
        if os.path.exists(engine_path):
            print(f"  TRT engine: {engine_path}")
    print(f"\n  To use: python3 lane_follow.py --model sidewalk")
    print(f"  The adapter will auto detect TRT engine or fall back to ONNX.")


if __name__ == "__main__":
    main()
