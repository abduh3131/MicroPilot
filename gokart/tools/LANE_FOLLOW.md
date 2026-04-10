## LANE_FOLLOW.md

Documentation for `lane_follow.py` (232 lines). This is the main model inference loop. It reads camera frames, runs a lane detection model, and outputs steering commands.

---

### Constants

| Name | Value | Purpose |
|------|-------|---------|
| DEFAULT_SPEED | 0.45 | Base throttle when lane following (0.0 to 1.0) |
| DEFAULT_RATE | 20 | Model inference rate in Hz |
| DEFAULT_MODEL | "supercombo" | Which model adapter to use |
| STEERING_GAIN | 2.0 | Multiplier on raw model steering output |
| MAX_STEER | 0.8 | Absolute steering clamp value |
| NO_LANE_TIMEOUT | 2.0 | Seconds to drive straight before stopping when no frame is available |

---

### IPC Files Read

| Path | Format | Source |
|------|--------|--------|
| `/tmp/lane_follow` | "0" or "1" | Web UI toggle for lane follow mode |
| `/tmp/exp_auto` | "0" or "1" | Web UI toggle for experimental autonomy mode |
| `/tmp/engage` | "0" or "1" | Web UI master engage toggle |
| `/tmp/lidar_stop` | "0" or "1" | Lidar safety node, "1" means obstacle detected |
| `/tmp/camera_frame.jpg` | JPEG image | Written by `webcam_capture.py` |

### IPC Files Written

| Path | Format | When Written |
|------|--------|--------------|
| `/tmp/model_output.json` | JSON (see below) | Always when the model runs, regardless of mode |
| `/tmp/joystick` | Text: `"throttle,steering"` | Only in Lane Follow mode, NOT in Exp Auto mode |

**model_output.json contents:**

```json
{
  "steering": float,
  "confidence": float,
  "lane_lines": [[33 points] x 4 lines],
  "plan_positions": [[x, y, z] x 33 points],
  "plan_prob": float,
  "left_near_y": float,
  "left_near_prob": float,
  "right_near_y": float,
  "right_near_prob": float,
  "frame": int,
  "ts": float
}
```

---

### Functions

#### `read_file(path, default="0")`

Reads a text file and returns its stripped contents. Returns `default` on any error (file missing, permission denied, etc.).

- **Input:** `path` (str) -- file path; `default` (str) -- fallback value.
- **Output:** str -- file contents or default.

#### `write_joystick(throttle, steering)`

Writes throttle and steering to `/tmp/joystick` using an atomic write pattern: writes to `/tmp/joystick.tmp` first, then calls `os.rename` to move it into place. This prevents readers from seeing a partial write.

- **Input:** `throttle` (float), `steering` (float).
- **Output:** None. Side effect: writes `/tmp/joystick`.

#### `write_model_output(steering, confidence, lane_info, plan_info, frame_num)`

Writes the full model output to `/tmp/model_output.json` using the same atomic write pattern. Includes steering, confidence, all four lane lines (33 points each), the 33-point plan path, plan probability, left/right lane edge positions and probabilities, frame number, and timestamp.

- **Input:** steering (float), confidence (float), lane_info (dict), plan_info (dict), frame_num (int).
- **Output:** None. Side effect: writes `/tmp/model_output.json`.

#### `load_frame()`

Reads `/tmp/camera_frame.jpg` from disk. Returns `None` if the file is missing or if the file modification time is more than 2 seconds old (stale frame detection).

- **Input:** None.
- **Output:** numpy array (BGR image) or `None`.

#### `create_adapter(model_name, steering_gain)`

Factory function that creates the correct model adapter based on a string name.

- `"supercombo"` returns a `SupercomboAdapter` instance.
- `"sidewalk"` returns a `SidewalkAdapter` instance.
- `"sidewalk+road"` returns a `SidewalkAdapter(include_road=True)` instance.

- **Input:** `model_name` (str), `steering_gain` (float).
- **Output:** adapter object with a `.run(frame)` method.

#### `run(speed, rate, adapter)`

The main loop. Runs at `rate` Hz. Core logic:

1. **Determine if model is needed:** `model_needed = (lane_on or exp_auto_on) and engaged`.
2. **When model_needed is True:**
   - Calls `load_frame()` to get the latest camera image.
   - Calls `adapter.run(frame)` to get steering, confidence, lane info, and plan info.
   - Always writes `/tmp/model_output.json` with the full output.
3. **When lane_on is True (Lane Follow mode):**
   - Also writes `/tmp/joystick` with throttle and steering.
   - Throttle is scaled by confidence: `throttle = speed * (0.5 + 0.5 * min(confidence, 1.0))`. At 100% confidence the vehicle gets full speed; at 0% confidence it gets half speed.
4. **When exp_auto_on is True but lane_on is False:**
   - Only writes `model_output.json`. Does NOT write `/tmp/joystick`. The `exp_auto.py` script handles joystick output in this mode.
5. **When deactivated (not engaged or neither mode on):**
   - If lane_on or not exp_auto: zeros the joystick (stops the vehicle).
   - Deletes `model_output.json`.
6. **Lidar stop:** If `/tmp/lidar_stop` is "1" and lane_on, zeros the joystick immediately.
7. **No frame timeout:** If `load_frame()` returns `None`, drives straight at 30% of base speed for up to `NO_LANE_TIMEOUT` seconds, then stops completely.

- **Input:** `speed` (float), `rate` (int), `adapter` (model adapter).
- **Output:** None. Runs indefinitely until interrupted.

#### `main()`

Entry point. Parses command-line arguments, sets up signal handlers for clean shutdown, creates the model adapter via `create_adapter()`, and calls `run()`.

**Arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `--model` | "supercombo" | Model adapter name |
| `--speed` | 0.45 | Base speed (0.0 to 1.0) |
| `--rate` | 20 | Inference rate in Hz |
| `--steering-gain` | 2.0 | Steering sensitivity multiplier |

---

### How to Modify

| Goal | What to Change |
|------|----------------|
| Change default model | `DEFAULT_MODEL` constant or pass `--model` flag |
| Change speed | `--speed` flag (0.0 to 1.0) |
| Change model rate | `--rate` flag (Hz) |
| Change steering sensitivity | `--steering-gain` flag or `STEERING_GAIN` constant |
| Add a new model | Add an `elif` branch in `create_adapter()` and add the name to the `choices` list in `argparse` |
| Change throttle curve | Edit the line `throttle = speed * (0.5 + 0.5 * min(confidence, 1.0))` in `run()` |
| Change no-lane timeout | `NO_LANE_TIMEOUT` constant (seconds) |
