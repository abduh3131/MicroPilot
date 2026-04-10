## Autopilot

Simple constant-throttle autopilot for testing forward driving and lidar avoidance without the lane model.

### Overview

This script pushes a constant throttle value and zero steering when activated. It is a minimal testing tool, not the main autonomy loop. The main autonomy system is `exp_auto.py`.

When lidar detects an obstacle, this script zeros the throttle to stop the vehicle. When deactivated, it writes zero values to the joystick file.

- **Lines of code**: 111
- **Default speed**: 0.6
- **Default loop rate**: 10 Hz

---

### IPC

| Direction | Path              | Format | Description                              |
|-----------|-------------------|--------|------------------------------------------|
| Read      | `/tmp/autopilot`  | Text   | "1" to activate, anything else to stop   |
| Read      | `/tmp/engage`     | Text   | "1" if system is engaged                 |
| Read      | `/tmp/lidar_stop` | Text   | "1" if lidar emergency stop is active    |
| Write     | `/tmp/joystick`   | Text   | Throttle and steering values             |

---

### Functions

#### `run(speed, rate)`

Main loop at the given rate (default 10 Hz). Behavior per tick:

- If `/tmp/autopilot` contains "1" and the system is engaged: writes the constant throttle value (from `speed`) and zero steering to `/tmp/joystick`.
- If lidar stop is active: writes zero throttle (overrides the speed value).
- On deactivation: writes zero throttle and zero steering to `/tmp/joystick`.

#### `main()`

Entry point. Parses command-line arguments and calls `run()`.

**Arguments:**

| Flag      | Default | Description                    |
|-----------|---------|--------------------------------|
| `--speed` | `0.6`   | Constant throttle value (0-1)  |
| `--rate`  | `10`    | Loop rate in Hz                |

---

### Relationship to Other Scripts

This script is **not** the main autonomy loop. It exists for simple forward-driving tests and to verify that lidar stop works correctly. The full lane-following autonomy system is `exp_auto.py`, which uses model output to compute steering.

---

### How to Modify

- **Change default speed**: Pass `--speed` on the command line or edit the default in `main()`.
- **Change loop rate**: Pass `--rate` on the command line.
