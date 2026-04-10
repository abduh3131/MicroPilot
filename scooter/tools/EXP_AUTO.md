## EXP_AUTO.md

Documentation for `exp_auto.py` (265 lines). This is the experimental autonomy loop. It reads model output produced by `lane_follow.py`, computes steering via pure pursuit, adjusts throttle based on curvature and confidence, and writes joystick commands.

---

### Constants

| Name | Value | Purpose |
|------|-------|---------|
| DEFAULT_SPEED | 0.5 | Base throttle (0.0 to 1.0) |
| DEFAULT_RATE | 20 | Control loop rate in Hz |
| MAX_STEER | 0.9 | Absolute steering clamp |
| LOOKAHEAD_SHORT | 6.0 | Short lookahead distance in meters |
| LOOKAHEAD_LONG | 18.0 | Long lookahead distance in meters |
| BLEND_SHORT | 0.65 | Weight for short lookahead (65% near, 35% far) |
| PURE_PURSUIT_GAIN | 8.0 | Steering gain for pure pursuit |
| MIN_SPEED_RATIO | 0.3 | Minimum throttle multiplier in curves or low confidence |
| CURVATURE_BRAKE | 3.0 | How aggressively to slow in curves |
| CONFIDENCE_MIN | 0.08 | Below this confidence, throttle is zero |
| STALE_TIMEOUT | 1.5 | Seconds before model output is considered stale |
| NO_DATA_TIMEOUT | 3.0 | Seconds with no data before full stop |

---

### IPC Files Read

| Path | Format | Source |
|------|--------|--------|
| `/tmp/exp_auto` | "0" or "1" | Web UI toggle |
| `/tmp/engage` | "0" or "1" | Web UI master engage |
| `/tmp/lidar_stop` | "0" or "1" | Lidar safety node |
| `/tmp/model_output.json` | JSON | Written by `lane_follow.py` |

### IPC Files Written

| Path | Format | When Written |
|------|--------|--------------|
| `/tmp/joystick` | Text: `"throttle,steering"` | When exp_auto is active and engaged |

---

### Functions

#### `read_file(path, default="0")`

Same pattern as `lane_follow.py`. Reads a text file, returns default on error.

- **Input:** `path` (str), `default` (str).
- **Output:** str.

#### `write_joystick(throttle, steering)`

Same atomic write pattern as `lane_follow.py`. Writes to `.tmp` then renames.

- **Input:** `throttle` (float), `steering` (float).
- **Output:** None. Side effect: writes `/tmp/joystick`.

#### `read_model_output()`

Reads and parses `/tmp/model_output.json`. Returns `None` if the file is missing or if its timestamp is older than `STALE_TIMEOUT` (1.5 seconds).

- **Input:** None.
- **Output:** dict (parsed JSON) or `None`.

#### `get_lateral_at_distance(positions, target_dist)`

Given the 33-point plan path (list of [x, y, z] positions), finds the lateral (y) offset at a specific forward (x) distance using linear interpolation. If the target distance exceeds the path length, extrapolates from the last two points.

- **Input:** `positions` (list of [x, y, z]), `target_dist` (float, meters).
- **Output:** float -- lateral offset in meters. Positive means left, negative means right.

#### `compute_path_curvature(positions)`

Computes a curvature estimate from the first 15 points of the plan path. Calculated as the maximum lateral deviation divided by the forward distance covered. Higher values mean sharper turns.

- **Input:** `positions` (list of [x, y, z]).
- **Output:** float -- curvature estimate (unitless ratio).

#### `compute_steering(positions, data)`

The core steering algorithm using pure pursuit with dual lookahead.

1. Calls `get_lateral_at_distance()` at `LOOKAHEAD_SHORT` (6m) and `LOOKAHEAD_LONG` (18m).
2. Converts each lateral offset to a steering angle: `steer = y / lookahead * PURE_PURSUIT_GAIN`.
3. Blends the two: `final = BLEND_SHORT * short_steer + (1 - BLEND_SHORT) * long_steer` (65% short, 35% long).
4. If both lane edges are visible (probability > 0.4 for both `left_near_prob` and `right_near_prob`): blends 70% path-based steering with 30% lane-centering correction. Lane centering uses the average of left and right near-y values.
5. Clamps output to `[-MAX_STEER, MAX_STEER]`.

- **Input:** `positions` (list of [x, y, z]), `data` (dict from model_output.json).
- **Output:** float -- steering command (-0.9 to 0.9).

#### `compute_throttle(base_speed, curvature, confidence, lidar_stop)`

Computes throttle based on multiple factors.

- Returns 0 immediately if `lidar_stop` is True or `confidence < CONFIDENCE_MIN` (0.08).
- `curve_factor = max(1.0 - curvature * CURVATURE_BRAKE, MIN_SPEED_RATIO)` -- slows down in curves. With `CURVATURE_BRAKE = 3.0`, a curvature of 0.23 would cut speed to 30%.
- `conf_factor = max(confidence * 1.5, MIN_SPEED_RATIO)` -- slows when the model is uncertain.
- `throttle = base_speed * curve_factor * conf_factor`.

- **Input:** `base_speed` (float), `curvature` (float), `confidence` (float), `lidar_stop` (bool).
- **Output:** float -- throttle value (0.0 to base_speed).

#### `run(speed, rate)`

The main control loop. Runs at `rate` Hz.

- **Active condition:** `exp_on AND engaged`.
- Each iteration reads `model_output.json` via `read_model_output()`.
- If valid data: extracts plan positions, calls `compute_steering()` and `compute_throttle()`, writes `/tmp/joystick`.
- If no data for more than `NO_DATA_TIMEOUT` (3 seconds): stops completely (zeros joystick).
- If no data for less than 3 seconds: coasts at 20% of base speed with 50% of the last computed steering value.
- If lidar stop: zeros joystick immediately.

- **Input:** `speed` (float), `rate` (int).
- **Output:** None. Runs indefinitely.

#### `main()`

Entry point. Parses arguments and calls `run()`.

**Arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `--speed` | 0.5 | Base speed (0.0 to 1.0) |
| `--rate` | 20 | Control loop rate in Hz |
| `--lookahead` | 6.0 | Short lookahead distance (meters) |
| `--gain` | 8.0 | Pure pursuit steering gain |

---

### How to Modify

| Goal | What to Change |
|------|----------------|
| Change lookahead distances | `LOOKAHEAD_SHORT`, `LOOKAHEAD_LONG` constants or `--lookahead` flag |
| Change speed | `--speed` flag |
| Change steering aggressiveness | `--gain` flag or `PURE_PURSUIT_GAIN` constant |
| Change blend ratio | `BLEND_SHORT` constant (0.65 = 65% near, 35% far) |
| Change minimum confidence | `CONFIDENCE_MIN` constant (below this, throttle is zero) |
| Change curve braking | `CURVATURE_BRAKE` constant (higher = more braking in turns) |
| Change lane centering blend | The 0.7/0.3 split inside `compute_steering()` |
| Change coast behavior | The 20% speed and 50% steering multipliers in the no-data branch of `run()` |
| Change stale data threshold | `STALE_TIMEOUT` constant (seconds) |
