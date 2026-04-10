## OUTPUT_SERIAL.md -- Scooter Version

Documentation for the scooter `output_serial.py` (236 lines). This script reads joystick and safety IPC files, computes final actuator values, and sends them to the Arduino over serial. It also logs all output to a CSV file.

---

### IPC Files Read

| Path | Format | Source |
|------|--------|--------|
| `/tmp/joystick` | Text: `"throttle,steering"` | Written by `lane_follow.py` or `exp_auto.py` |
| `/tmp/engage` | "0" or "1" | Web UI master engage |
| `/tmp/lidar_stop` | "0" or "1" | Lidar safety node |
| `/tmp/lidar_steer` | Float as text | Lidar avoidance nudge value |

---

### Serial Protocol

Sends 3 comma-separated values per line to the Arduino:

```
throttle,steering,lidar\n
```

| Field | Range | Description |
|-------|-------|-------------|
| throttle | 0.0 to 0.25 | Forward speed, hard-clamped at 0.25 max |
| steering | -1.0 to 1.0 | Steering angle, includes lidar nudge offset |
| lidar | 0.0 or 1.0 | Lidar emergency stop flag |

---

### Functions

#### `compute_values()`

Reads all IPC files and computes the final throttle, steering, and lidar values to send to the Arduino.

- Reads `/tmp/joystick` and splits into throttle and steering floats.
- Reads `/tmp/engage` -- if not engaged, throttle and steering are zeroed.
- Reads `/tmp/lidar_stop` -- converted to 0.0 or 1.0 float.
- Reads `/tmp/lidar_steer` -- a float nudge value added to the steering output.
- Clamps throttle to a maximum of 0.25 (safety limit).
- Adds `lidar_nudge` to steering for obstacle avoidance.

- **Input:** None (reads IPC files directly).
- **Output:** Tuple of `(throttle, steering, lidar, engaged, lidar_nudge)`.
  - `throttle`: float, 0.0 to 0.25.
  - `steering`: float, -1.0 to 1.0.
  - `lidar`: float, 0.0 or 1.0.
  - `engaged`: bool.
  - `lidar_nudge`: float.

#### `serial_thread_func(port, baud, rate)`

Runs in a separate thread. Opens the serial port, waits 10 seconds for the Arduino to finish its reset cycle, then sends the 3-value CSV string at a fixed rate (default 4 Hz).

- On each tick: calls `compute_values()`, formats as `"throttle,steering,lidar\n"`, writes to serial.
- Handles reconnection: if 10 or more consecutive serial write errors occur (timeout or exception), closes the port and re-opens it. Waits 10 seconds again after reconnection for the Arduino reset.

- **Input:** `port` (str, e.g., "/dev/ttyACM0"), `baud` (int, e.g., 115200), `rate` (int, Hz).
- **Output:** None. Runs indefinitely in a thread.

#### `main()`

Entry point. Starts the serial thread and a CSV logging loop.

- The serial thread handles all communication with the Arduino.
- The main thread runs a logging loop that calls `compute_values()` and appends a row to a CSV log file.
- CSV columns: `timestamp_ns, throttle, steering, lidar, lidar_nudge, engaged`.

**Arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `--serial` | "/dev/ttyACM0" | Serial port path |
| `--baud` | 115200 | Baud rate |
| `--rate` | 4 | Serial send rate in Hz |

---

### How to Modify

| Goal | What to Change |
|------|----------------|
| Change max throttle | The 0.25 clamp in `compute_values()` |
| Change serial rate | `--rate` flag (default 4 Hz) |
| Change baud rate | `--baud` flag (default 115200) |
| Change serial port | `--serial` flag |
| Change reconnection threshold | The consecutive error count (10) in `serial_thread_func()` |
| Change Arduino reset wait | The 10-second sleep in `serial_thread_func()` |
