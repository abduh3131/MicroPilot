## Supercombo Adapter

### Overview

`supercombo_adapter.py` (~297 lines) implements `SupercomboAdapter`, a `BaseModelAdapter` subclass that wraps the openpilot supercombo model. This model is an end-to-end driving network that takes YUV camera frames and produces lane lines and driving plans directly, without an intermediate segmentation step. The adapter is present in both vehicle codebases but is not the default launch path on either vehicle.

### Classes

#### `TRTInference`

TensorRT GPU inference backend for supercombo. Handles multiple named inputs (images, desire, traffic convention, navigation features, features buffer). The constructor loads the engine and allocates buffers for each input/output binding.

#### `ORTInference`

ONNX Runtime CPU fallback. Loads an ONNX session and runs inference with the same named inputs.

#### `SupercomboAdapter(BaseModelAdapter)`

Main adapter class. Manages frame history, feature buffer state, and the full inference pipeline.

### Constants

| Constant | Value | Purpose |
|---|---|---|
| `TRAJECTORY_SIZE` | 33 | Number of longitudinal sample points per output |
| `PLAN_MHP_N` | 5 | Number of plan hypotheses the model outputs |
| `FEATURE_LEN` | 128 | Length of each feature vector in the rolling history |
| `HISTORY_BUFFER_LEN` | 99 | Number of past feature vectors retained |
| `DESIRE_LEN` | 8 | Dimension of the desire (navigation intent) vector |
| `PLAN_OFFSET` | 0 | Start index of plan data in the flat output array |
| `PLAN_SIZE` | 4955 | Length of the plan block in the output |
| `LANE_LINES_OFFSET` | 4955 | Start index of lane line data in the output |
| `ENGINE_PATH` | Points to `supercombo.engine` | Default TensorRT engine path |
| `ONNX_PATH` | Points to `supercombo.onnx` | Default ONNX model path |

### Constructor

```
SupercomboAdapter(engine_path, onnx_path, steering_gain=2.0)
```

Also initializes:
- `features_buffer` -- shape (1, 99, 128), dtype float16, rolling window of past model features
- `prev_frame` -- stores the previous preprocessed frame for two-frame input

### Methods

#### `load_model()`

Attempts to load the TensorRT engine first, then falls back to ONNX. Returns a string naming the backend.

#### `_preprocess_frame(bgr_img)`

Converts a BGR camera frame into the model's expected input format:

1. Resize to 512x256.
2. Convert BGR to YUV I420.
3. Subsample the Y plane into 4 channels: `Y[0::2,0::2]`, `Y[1::2,0::2]`, `Y[0::2,1::2]`, `Y[1::2,1::2]`.
4. Stack with U and V planes to produce 6 planes total.
5. Duplicate for 2 frames (current + previous) to produce 12 planes.

**Critical**: Raw uint8 values (0-255) are cast to float16 without any division by 255. Normalizing to [0,1] breaks the model and produces constant 0.50 confidence outputs.

#### `_parse_lane_lines(output)`

Extracts 4 lane lines from the model output: left_far, left_near, right_near, right_far. Each lane has 33 sample points with y (lateral) and z (vertical) coordinates, plus a detection probability computed as sigmoid of the raw logit.

#### `_parse_plan(output)`

Finds the best of 5 plan hypotheses by probability (softmax over plan logits). Extracts 33x3 position coordinates from the winning hypothesis.

#### `_compute_steering(lane_info, plan_info)`

Computes steering using a 3-tier priority system:

1. **Both lanes visible** -- steer toward the center between the two nearest lane lines.
2. **One lane visible** -- steer to maintain 1.5 meters of clearance from the detected lane.
3. **Fallback** -- follow the planned path at 0.5x gain.

#### `run(bgr_frame)`

Full pipeline per frame:

1. Preprocess the current frame.
2. Concatenate with the previous frame to form a 12-plane input.
3. Build the feeds dictionary (see Model Inputs below).
4. Run inference.
5. Parse lane lines and plan from the output.
6. Compute steering and confidence.
7. Update `features_buffer` with the rolling window of model features.

Returns the standard 4-tuple `(steering, confidence, lane_info, plan_info)`.

### Model Inputs (feeds dict)

| Key | Shape | Dtype | Description |
|---|---|---|---|
| `input_imgs` | (1, 12, 128, 256) | float16 | 2 frames x 6 YUV planes each |
| `big_input_imgs` | (1, 12, 128, 256) | float16 | Copy of `input_imgs` (wide-angle input, same data here) |
| `desire` | (1, 100, 8) | float16 | Navigation intent vector, filled with zeros (unused) |
| `traffic_convention` | (1, 2) | float16 | `[[1.0, 0.0]]` for right-hand traffic |
| `nav_features` | (1, 256) | float16 | Navigation features, filled with zeros (unused) |
| `features_buffer` | (1, 99, 128) | float16 | Rolling history of model feature outputs |

### Common Modifications

| Goal | What to change |
|---|---|
| Change lane avoidance margin | The `1.5` value inside `_compute_steering` (compared to `0.8` in the sidewalk adapter) |
| Switch to left-hand traffic | Change `traffic_convention` from `[1.0, 0.0]` to `[0.0, 1.0]` |
| Adjust steering sensitivity | `steering_gain` constructor parameter |
| Activate this adapter | Run `python3 lane_follow.py --model supercombo` |
