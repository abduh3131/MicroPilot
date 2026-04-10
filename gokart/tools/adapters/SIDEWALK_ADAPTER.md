## Sidewalk Adapter

### Overview

`sidewalk_adapter.py` (~387 lines) implements `SidewalkAdapter`, a `BaseModelAdapter` subclass that uses a semantic segmentation model to detect sidewalk and road surfaces. It converts a per-pixel class mask into lane edges and a driveable path, then computes a steering command. This is the default adapter for sidewalk-following operation.

### Classes

#### `TRTSegmentation`

TensorRT GPU inference backend. The constructor loads a serialized TensorRT engine file and allocates paired host/device memory buffers. The `run(input_tensor)` method copies the input to the GPU, executes inference, and copies the result back to the host.

#### `ORTSegmentation`

ONNX Runtime CPU fallback. The constructor loads an ONNX session. The `run(input_tensor)` method runs inference on the CPU. Used automatically when TensorRT is unavailable.

#### `SidewalkAdapter(BaseModelAdapter)`

Main adapter class. Orchestrates the full pipeline from raw camera frame to steering output.

### Constants

| Constant | Value | Purpose |
|---|---|---|
| `SEG_ENGINE_PATH` | `/home/jetson/openpilotV3/selfdrive/modeld/models/sidewalk_segmentation.engine` | Default TensorRT engine path |
| `SEG_ONNX_PATH` | Same path but `.onnx` | Default ONNX model path |
| `MODEL_WIDTH` | 1024 | Input width in pixels |
| `MODEL_HEIGHT` | 512 | Input height in pixels |
| `CLASS_ROAD` | 0 | Class index for road |
| `CLASS_SIDEWALK` | 1 | Class index for sidewalk |
| `CAM_HEIGHT` | 1.22 | Camera mounting height in meters |
| `CAM_FOCAL` | 500.0 | Camera focal length in pixels |
| `CAM_HORIZON` | 0.38 | Horizon position as fraction of image height from top |
| `X_IDXS` | 33 values, 0 to 192 meters | Standard openpilot longitudinal sample distances |
| `NUM_SCAN_ROWS` | 20 | Number of horizontal strips scanned for edge detection |

### Constructor

```
SidewalkAdapter(engine_path, onnx_path, steering_gain=2.0, target_class=1, include_road=False)
```

- `engine_path` / `onnx_path` -- paths to the segmentation model files
- `steering_gain` -- multiplier for the raw steering signal
- `target_class` -- which segmentation class to follow (default 1 = sidewalk)
- `include_road` -- if True, the driveable mask includes both road (class 0) and the target class

### Methods

#### `load_model()`

Attempts to load the TensorRT engine first. If that fails, falls back to the ONNX backend. Returns a string naming the backend that was loaded.

#### `_preprocess_frame(bgr_img)`

Resizes the input to 1024x512, converts BGR to RGB, applies ImageNet normalization (mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]), transposes to CHW format, and adds a batch dimension.

#### `_get_driveable_mask(model_output)`

Takes the raw model output, applies argmax across the class dimension to get per-pixel class labels, and creates a binary mask where the target class (and optionally road) pixels are True.

#### `_mask_to_edges_and_path(mask, img_w, img_h)`

Scans 20 horizontal strips from the bottom of the image (95% height) up to just above the horizon (horizon + 5%). For each strip, finds the leftmost and rightmost sidewalk pixels. Converts pixel coordinates to real-world meters using a pinhole camera model with `CAM_FOCAL` and `CAM_HEIGHT`. Returns three lists of (x_forward, y_lateral) tuples: `left_edges`, `right_edges`, and `center_path`.

#### `_build_lane_info(left_edges, right_edges)`

Interpolates the detected edges to the 33 standard `X_IDXS` longitudinal distances. Computes detection probabilities based on how many scan rows produced valid edges. Returns a `lane_info` dict conforming to the `BaseModelAdapter` return format.

#### `_build_plan_info(center_path)`

Interpolates the center path to the 33 standard `X_IDXS` points. Returns a `plan_info` dict with `positions`, `path_y`, and `prob` keys.

#### `_compute_steering(lane_info, plan_info)`

Computes a steering command using a 3-tier priority system:

1. **Both edges visible** -- steer toward the center point between left and right edges.
2. **One edge visible** -- steer to maintain 0.8 meters of clearance from the visible edge.
3. **Fallback** -- follow the center path from `plan_info` at 0.5x gain.

#### `run(bgr_frame)`

Executes the full pipeline: preprocess the frame, run inference, generate the driveable mask, extract edges and center path, build `lane_info` and `plan_info`, compute steering and confidence. Returns the standard 4-tuple `(steering, confidence, lane_info, plan_info)`.

### Common Modifications

| Goal | What to change |
|---|---|
| Adjust for a different camera mounting height | `CAM_HEIGHT` constant at the top of the file |
| Adjust for a different camera lens | `CAM_FOCAL` constant |
| Change the assumed horizon position | `CAM_HORIZON` constant |
| Increase or decrease steering sensitivity | `steering_gain` constructor parameter, or `STEERING_GAIN` in `lane_follow.py` |
| Follow road instead of sidewalk | Set `target_class=0` in the constructor |
| Follow both road and sidewalk | Set `include_road=True` in the constructor |
| Change edge detection resolution | `NUM_SCAN_ROWS` constant |
| Use a different segmentation model | Point `SEG_ENGINE_PATH` / `SEG_ONNX_PATH` to a different model (must output per-pixel class labels) |
| Change the single-edge avoidance margin | Modify the `0.8` value inside `_compute_steering` |
