# setup_sidewalk_model.py -- SegFormer Model Setup

One-time setup script that downloads a SegFormer B0 Cityscapes ONNX model from HuggingFace, tests it with inference, and optionally converts it to a TensorRT engine. 235 lines.

---

## What It Does

1. Downloads the SegFormer-B0 Cityscapes ONNX model from HuggingFace.
2. Runs a test inference (random input or a provided test image) to verify the model works.
3. Optionally converts the ONNX model to a TensorRT engine using `trtexec`.

---

## Constants

| Constant | Value |
|----------|-------|
| `MODEL_DIR` | `/home/jetson/openpilotV3/selfdrive/modeld/models` |
| `ONNX_FILENAME` | `sidewalk_segmentation.onnx` |
| `ENGINE_FILENAME` | `sidewalk_segmentation.engine` |
| `ONNX_URL` | HuggingFace `Xenova/segformer-b0-finetuned-cityscapes-1024-1024` model.onnx |

---

## Functions

### download_model(output_dir, filename)

Downloads the ONNX file from `ONNX_URL` with a progress bar. Skips download if the file already exists. Returns the output path or None on failure. On failure, prints manual download instructions and an alternative export method using HuggingFace optimum CLI.

### test_model(onnx_path, test_image_path=None)

Loads the ONNX model with `onnxruntime` (CPU provider). Prints input/output tensor shapes. Runs inference on either the provided test image or random noise. Computes the class map via argmax and prints detected Cityscapes classes with pixel percentages.

Cityscapes class list (19 classes): road (0), sidewalk (1), building (2), wall (3), fence (4), pole (5), traffic_light (6), traffic_sign (7), vegetation (8), terrain (9), sky (10), person (11), rider (12), car (13), truck (14), bus (15), train (16), motorcycle (17), bicycle (18).

Class 1 (sidewalk) is marked as TARGET in the output. Returns True if inference succeeds, False otherwise.

If a test image is provided, it is resized to model input dimensions, converted to RGB, and normalized with ImageNet mean `[0.485, 0.456, 0.406]` and std `[0.229, 0.224, 0.225]`.

### convert_to_trt(onnx_path, engine_path, fp16=True)

Runs `trtexec` CLI to build a TensorRT engine. Default precision is FP16. Input shape is fixed at `pixel_values:1x3x512x1024`. Workspace is 2048 MB. Timeout is 30 minutes.

The conversion takes 5-15 minutes and must run ON the Jetson because TensorRT engines are locked to the GPU architecture they were built on. Returns True on success, False on failure. Prints helpful fallback instructions if `trtexec` is not found or conversion fails.

### main()

Parses arguments, runs download, runs test, optionally runs TRT conversion. Exits with code 1 if download or test fails.

---

## Command-Line Arguments

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | `/home/jetson/openpilotV3/selfdrive/modeld/models` | Directory to save model files |
| `--convert-trt` | off | Convert ONNX to TensorRT after download. Must run on the Jetson |
| `--test-image` | None | Path to a test image for verification |
| `--fp32` | off (FP16 default) | Use FP32 precision for TensorRT instead of FP16 |

---

## Usage

```bash
# Download and test only
python setup_sidewalk_model.py

# Download, test, and build TRT engine (run on Jetson)
python setup_sidewalk_model.py --convert-trt

# Test with a specific image
python setup_sidewalk_model.py --test-image /path/to/sidewalk_photo.jpg

# Use a different output directory
python setup_sidewalk_model.py --output-dir /tmp/models
```

After setup, the model is used by: `python3 lane_follow.py --model sidewalk`

The lane_follow adapter auto-detects a TRT engine if present and falls back to ONNX Runtime if not.

---

## How to Modify

- **Use a different model:** Change `ONNX_URL` to point to a different HuggingFace ONNX file. Update `ONNX_FILENAME` accordingly.
- **Change input shape:** Edit the `--shapes=pixel_values:1x3x512x1024` flag in `convert_to_trt()`.
- **Change output directory:** Edit `MODEL_DIR` or pass `--output-dir`.
- **Run on a different Jetson:** Only `MODEL_DIR` needs to change. The TRT conversion must always run on the target device.
