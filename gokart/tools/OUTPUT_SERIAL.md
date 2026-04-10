## OUTPUT_SERIAL.md -- Go-kart Version

Documentation for the go-kart `output_serial.py` (244 lines). This script reads joystick and safety IPC files, computes final actuator values, and sends them to the Arduino over serial. It also logs all output to a CSV file.

---

### IPC Files Read

| Path | Format | Source |
|------|--------|--------|
| `/tmp/joystick` | Text: `"throttle,steering"` | Written by `lane_follow.py` or `exp_auto.py` |
| `/tmp/engage` | "0" or "1" | Web UI master engage |
| `/tmp/lidar_stop` | "0" or "1" | Lidar safety node |
| `/tmp/lidar_steer` | Float as text | Lidar avoidance nudge value |
| `/tmp/speed_setting` | "0" to "5" | Web UI speed setting selector |

---

### Serial Protocol

Sends 6 comma-separated values per line to the Arduino:

```
steer,brake,arm,throttle,direction,speed_setting\n
```

| Field | Range | Description |
|-------|-------|-------------|
| steer | -1.0 to 1.0 | Steering angle |
| brake | 0.0 or 1.0 | Lidar emergency stop (e-stop) |
| arm | 0 or 1 | Engaged state (1 = armed) |
| throttle | 0.0 to 1.0 | Forward speed, scaled by speed_setting |
| direction | 0 or 1 | 0 = reverse, 1 = forward |
| speed_setting | 0 to 5 | Current speed setting from web UI |

---

### Functions

#### `compute_values()`

Reads all IPC files and computes the final 6-value output for the Arduino.

- Reads `/tmp/joystick` and splits into throttle (X) and steering (Y) floats.
- Reads `/tmp/engage` -- if not engaged, arm=0, throttle and steering are zeroed.
- Reads `/tmp/lidar_stop` -- converted to brake value (0.0 or 1.0). When lidar e-stop is active, steering remains alive but throttle is zeroed.
- Reads `/tmp/lidar_steer` -- nudge value added to steering.
- Reads `/tmp/speed_setting` -- integer 0 to 5.
- **Direction:** determined by joystick X sign. If X < -0.05, direction = 0 (reverse). If X > 0.05, direction = 1 (forward). Between -0.05 and 0.05, direction holds its previous value.
- **Throttle scaling:** `throttle = abs(joy_x) * (speed_setting + 1) / 6.0`. At speed_setting 0, throttle is scaled to 1/6. At speed_setting 5, throttle passes through at full value.

- **Input:** None (reads IPC files directly).
- **Output:** Tuple of `(steer, brake, arm, throttle, direction, speed_setting, lidar_nudge)`.
  - `steer`: float, -1.0 to 1.0.
  - `brake`: float, 0.0 or 1.0.
  - `arm`: int, 0 or 1.
  - `throttle`: float, 0.0 to 1.0.
  - `direction`: int, 0 or 1.
  - `speed_setting`: int, 0 to 5.
  - `lidar_nudge`: float.

#### `serial_thread_func(port, baud, rate)`

Runs in a separate thread. Opens the serial port, waits 10 seconds for the Arduino to finish its reset cycle, then sends the 6-value CSV string at a fixed rate (default 4 Hz).

- On each tick: calls `compute_values()`, formats as `"steer,brake,arm,throttle,direction,speed_setting\n"`, writes to serial.
- Same reconnection logic as the scooter version: 10+ consecutive errors triggers a reconnect with a 10-second Arduino reset wait.

- **Input:** `port` (str), `baud` (int), `rate` (int, Hz).
- **Output:** None. Runs indefinitely in a thread.

#### `main()`

Entry point. Starts the serial thread and a CSV logging loop.

- CSV columns: `timestamp_ns, steer, brake, arm, throttle, direction, speed_setting, lidar_nudge`.

**Arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `--serial` | "/dev/ttyACM0" | Serial port path |
| `--baud` | 115200 | Baud rate |
| `--rate` | 4 | Serial send rate in Hz |

---

### Key Differences from Scooter Version

| Aspect | Scooter | Go-kart |
|--------|---------|---------|
| Values sent | 3 (throttle, steering, lidar) | 6 (steer, brake, arm, throttle, direction, speed_setting) |
| Throttle clamp | Hard max 0.25 | Scaled by speed_setting, up to 1.0 |
| Direction | Always forward | Forward/reverse from joystick sign |
| Arm field | Not present | Explicit arm/disarm in serial output |
| Brake field | Not present | Explicit brake from lidar |
| Speed setting | Not present | Read from `/tmp/speed_setting` (0-5) |
| Lidar e-stop behavior | Zeros all values | Zeros throttle but keeps steering alive |

---

### How to Modify

| Goal | What to Change |
|------|----------------|
| Change speed scaling | The `(speed_setting + 1) / 6.0` formula in `compute_values()` |
| Change direction thresholds | The -0.05 and 0.05 thresholds in `compute_values()` |
| Change serial rate | `--rate` flag (default 4 Hz) |
| Change baud rate | `--baud` flag (default 115200) |
| Change serial port | `--serial` flag |
| Change reconnection threshold | The consecutive error count (10) in `serial_thread_func()` |
