# actuator_logger.py -- Actuator Command Logger

Subscribes to openpilot cereal `carOutput` messages, extracts torque and steering values, computes normalized throttle and steering, and logs everything to CSV. Can optionally forward throttle/steering to a serial port.

131 lines. Runs as a standalone script.

---

## Cereal Subscription

Subscribes to `carOutput` via `messaging.SubMaster(['carOutput'])`. Reads the following fields from `actuatorsOutput`:

| Field | Used As |
|-------|---------|
| `accel` | `torque_l` (left torque) |
| `torque` | `torque_r` (right torque) |
| `steeringAngleDeg` | Logged directly |

---

## Computed Values

```
MAX_TORQUE = 500.0
throttle = clamp(-1, 1, (torque_l + torque_r) / (2 * MAX_TORQUE))
steering = clamp(-1, 1, (torque_l - torque_r) / (2 * MAX_TORQUE))
```

Both values are clamped to the range [-1.0, 1.0].

---

## Output Files

### Main CSV (default: `actuators.csv`)

Columns: `timestamp_ns, torque_l, torque_r, steeringAngleDeg, throttle, steering`

Appends to existing file. Writes header only if the file is empty or missing. Flushes to disk every 100 frames.

### Serial CSV (default: `serialLogs.csv`)

Columns: `timestamp_ns, throttle, steering`

Same append and flush behavior as the main CSV.

### Serial Port (optional)

When `--serial` is provided, writes `throttle,steering\n` as UTF-8 text to the serial port on every frame. Uses pyserial.

---

## Command-Line Arguments

| Flag | Default | Description |
|------|---------|-------------|
| `--output` | `actuators.csv` | Path to the main CSV output file |
| `--rate` | `100` | Polling rate in Hz. SubMaster update timeout is `1000/rate` ms |
| `--serial` | None | Serial port path (e.g., `/dev/ttyACM0`, `COM3`). Enables serial forwarding |
| `--baud` | `115200` | Baud rate for the serial port |
| `--serial-log` | `serialLogs.csv` | Path to the serial commands log file |

---

## Usage

```bash
# Log only
python actuator_logger.py --output /tmp/actuators.csv

# Log and forward to Arduino
python actuator_logger.py --serial /dev/ttyACM0 --baud 115200
```

---

## How to Modify

- **Change MAX_TORQUE:** Edit the `MAX_TORQUE = 500.0` constant inside `main()`.
- **Add more cereal fields:** Add them to the SubMaster subscription list, read from `sm['carOutput']`, and add columns to the CSV writer.
- **Change serial format:** Edit the `serial_line = f"{throttle:.4f},{steering:.4f}\n"` line.
