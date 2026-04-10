## Base Model Adapter

### Overview

`base_adapter.py` defines `BaseModelAdapter`, an abstract base class that every model adapter must implement. It exists so that `lane_follow.py` remains model-agnostic -- any conforming adapter can be swapped in via the `--model` flag without changing the lane-following logic.

### Methods

#### `load_model()`

Abstract. Called once at startup. The adapter should load its model (TensorRT engine, ONNX session, etc.) and return a string identifying which backend was used (e.g. `"TensorRT"` or `"ONNX"`).

#### `run(bgr_frame)`

Abstract. Called every frame. Accepts a BGR numpy array from the camera and must return a 4-tuple:

```
(steering, confidence, lane_info, plan_info)
```

**Return values:**

| Field | Type | Description |
|---|---|---|
| `steering` | float | Steering command, range -0.8 (hard left) to +0.8 (hard right) |
| `confidence` | float | Model confidence, range 0.0 to 1.0 |
| `lane_info` | dict | Lane line detections (see below) |
| `plan_info` | dict | Planned path (see below) |

**`lane_info` dict keys:**

- `left_near_y` -- lateral offset (meters) of the nearest left lane line
- `right_near_y` -- lateral offset (meters) of the nearest right lane line
- `left_near_prob` -- detection probability for the left lane line (0.0 to 1.0)
- `right_near_prob` -- detection probability for the right lane line (0.0 to 1.0)
- `_full` -- list of 4 lane dicts (left_far, left_near, right_near, right_far), each containing `y` (list of 33 floats), `z` (list of 33 floats), and `prob` (float)

**`plan_info` dict keys:**

- `positions` -- 33x3 list of [x_forward, y_lateral, z_vertical] coordinates in meters
- `path_y` -- list of 33 lateral offset floats (meters)
- `prob` -- float, probability of the selected plan hypothesis

#### `get_name()`

Non-abstract. Returns the class name of the adapter as a string. Subclasses may override this if a custom display name is needed.

### Adding a New Adapter

1. Create a new file in `tools/adapters/` (e.g. `my_model_adapter.py`).
2. Subclass `BaseModelAdapter` and implement `load_model()` and `run(bgr_frame)`.
3. Ensure `run()` returns the 4-tuple described above.
4. Register the adapter in `lane_follow.py` inside the `create_adapter()` function so it can be selected with `--model my_model`.
