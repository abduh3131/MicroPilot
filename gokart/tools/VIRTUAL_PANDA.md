## Virtual Panda

Emulates a comma body panda so that openpilot daemons can run without real panda hardware attached.

### Overview

This script publishes fake cereal messages that openpilot expects from a physical panda device. It allows the full openpilot stack (controls, planning, modeld) to start and operate on a platform that has no comma body or panda connected.

- **Lines of code**: 186
- **Loop rate**: 100 Hz (via Ratekeeper)

---

### Published Messages

| Message           | Rate   | Description                                    |
|-------------------|--------|------------------------------------------------|
| `pandaStates`     | 10 Hz  | Ignition on, controls allowed, safety=body     |
| `peripheralState` | 2 Hz   | Peripheral heartbeat                           |
| `can`             | 100 Hz | Empty CAN bus frames                           |
| `carParams`       | Once   | Fake vehicle parameters (re-sent for 30s)      |
| `carState`        | 100 Hz | Standstill, vEgo=0, cruise enabled             |
| `carOutput`       | 100 Hz | Echoes back actuator commands from carControl   |
| `liveTracks`      | 100 Hz | Empty live tracks                              |

### Subscribed Messages

| Message           | Description                          |
|-------------------|--------------------------------------|
| `carControl`      | Actuator commands from controls      |
| `selfdriveState`  | Self-drive state from controls       |

---

### Functions

#### `build_car_params()`

Builds and returns a fake `CarParams` cereal message. Key settings:

- `brand="body"`, `carFingerprint="COMMA BODY"`, `notCar=True`
- `minEnableSpeed=0.0`, `minSteerSpeed=0.0` (system enables at zero speed)
- `steerControlType="torque"`, `steerRatio=0.5`
- `wheelbase=0.406m`, `mass=9.0kg`
- `safetyModel=body`, `safetyParam=0`
- `lateralTuning`: torque mode with `friction=0.0`

#### `main()`

Main loop. Performs the following on startup:

1. Writes `CarParams` to the openpilot Params store so it persists across restarts.
2. Enters a 100 Hz loop via `Ratekeeper`.

Per-tick behavior:

- Every 10 ticks (10 Hz): sends `pandaStates` with `ignitionLine=True`, `controlsAllowed=True`, `safetyModel=body`.
- Every 50 ticks (2 Hz): sends `peripheralState`.
- Every tick: sends empty CAN frames.
- For the first 30 seconds: re-writes `CarParams` to Params (openpilot manager wipes params on ignition events).
- Every tick: sends `carState` with `standstill=True`, `vEgo=0`, `cruiseState.enabled=True`.
- Every tick: reads `carControl` actuators and echoes them back in `carOutput`.

---

### How to Modify

- **Change vehicle mass**: Edit `CP.mass` in `build_car_params()`.
- **Change steer ratio**: Edit `CP.steerRatio` in `build_car_params()`.
- **Change safety model**: Edit the `safetyModel` field (must match what openpilot expects).
- **Change publish rate**: Change the value passed to `Ratekeeper(100)`.
