# Openpilot Actuator Values Report

This report documents the actuator values available in Openpilot's `CarOutput` / `CarControl` messages, their meanings, ranges, and coordinate systems. It also includes instructions for using the `actuator_logger.py` tool.

## 1. Actuator Fields and Meanings

The `actuatorsOutput` field in `CarOutput` (and `CarControl`) contains the following signals sent to the vehicle:

| Field | Unit / Type | Description | Sign / Coordinate System |
| :--- | :--- | :--- | :--- |
| **`gas`** | Normalized (0.0 to 1.0) | Throttle command. | `0.0` = No throttle, `1.0` = Max throttle. |
| **`brake`** | Normalized (0.0 to 1.0) | Brake pedal command. | `0.0` = No brake, `1.0` = Max brake. |
| **`steer`** | Normalized (-1.0 to 1.0) | Steering torque request. | **Positive (+)** = Left (Counter-Clockwise)<br>**Negative (-)** = Right (Clockwise) |
| **`steeringAngleDeg`**| Degrees (°) | Sensed or Requested Angle | **Positive (+)** = Left (Counter-Clockwise)<br>**Negative (-)** = Right (Clockwise)<br>*Note: This usually tracks the steering wheel angle.* |
| **`torque`** | Newton-Meters (Nm) | Steering torque (if supported). | **Positive (+)** = Left<br>**Negative (-)** = Right |
| **`accel`** | m/s² | Targeted Acceleration. | **Positive (+)** = Accelerate<br>**Negative (-)** = Decelerate/Brake |
| **`speed`** | m/s | Targeted Speed. | Always positive (forward motion). |
| **`steeringPressed`** | Boolean | Driver override status. | `True` if driver is actively steering, `False` otherwise. |

## 2. Limits and Scaling

Actuator limits are vehicle-specific and defined in `selfdrive/car/*/interface.py` or `values.py`.

- **Steering:**
    - Most vehicles accept a normalized torque (`steer`) between -1.0 and 1.0.
    - This is scaled by `STEER_MAX` in the car's parameters to physical units (often raw CAN values or Nm).
    - Rate limits (how fast torque can change) are also applied (`STEER_DELTA_UP`, `STEER_DELTA_DOWN`).

- **Gas/Brake:**
    - Normalized 0.0 to 1.0.
    - Scaled to CAN signals (e.g., pedal position ticks).
    - Longitudinal control often uses `accel` (m/s²) as the primary interface, which the car controller converts to gas/brake commands.

## 3. Using the Actuator Logger

A script has been added to `tools/actuator_logger.py` to extract these values to a CSV file.

### Usage

Run the script from the root of the openpilot directory:

```bash
python tools/actuator_logger.py
```

By default, this saves to `./actuators.csv` at 100 Hz.

### Options

```bash
python tools/actuator_logger.py --output /path/to/file.csv --rate 50
```

- `--output`: Change the destination file.
- `--rate`: Change the logging frequency (Hz).
- `--serial`: Serial port for Arduino (e.g., `COM3`, `/dev/ttyUSB0`).
- `--baud`: Serial baud rate (default: 115200).

### Stopping
Press `Ctrl+C` to stop the logger. The file will be correctly closed and saved.

## 4. Serial Protocol for External Controllers (Arduino)

If you use the `--serial` argument, the script will output a comma-separated line for each frame. This is designed to be easily parsed by an Arduino or other microcontroller.

**Baud Rate:** `115200` (default, configurable via `--baud`)
**Line Ending:** `\n` (Newline)

### Data Format
Each line contains the following values in order:

```text
gas,brake,steer,steeringAngleDeg,torque,accel,speed,steeringPressed
```

**Example Line:**
```text
0.0,0.0,0.15,-3.5,0.0,0.5,22.4,False
```

### Sample Arduino Code
Here is a basic snippet to read and parse this data on an Arduino:

```cpp
void setup() {
  Serial.begin(115200); // Must match --baud
}

void loop() {
  if (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');

    // Parse comma-separated values
    // Note: You may need a more robust parser for high-speed applications
    float gas = getValue(line, ',', 0).toFloat();
    float brake = getValue(line, ',', 1).toFloat();
    float steer = getValue(line, ',', 2).toFloat();
    float angle = getValue(line, ',', 3).toFloat();
    // ... continue for other fields

    // Control your hardware based on these values
  }
}

// Helper function to extract comma-separated string
String getValue(String data, char separator, int index) {
  int found = 0;
  int strIndex[] = {0, -1};
  int maxIndex = data.length()-1;

  for(int i=0; i<=maxIndex && found<=index; i++){
    if(data.charAt(i)==separator || i==maxIndex){
        found++;
        strIndex[0] = strIndex[1]+1;
        strIndex[1] = (i == maxIndex) ? i+1 : i;
    }
  }
  return found>index ? data.substring(strIndex[0], strIndex[1]) : "";
}
```

