# web.py -- Browser Control Panel (Go-Kart)

Hosts the browser-based control panel for the go-kart platform. Serves HTML/JS/CSS from `static/` over HTTPS on port 5000. Provides REST and WebSocket endpoints for engage, lane follow, experimental autopilot, full autopilot, speed setting, manual joystick control, and live video streaming.

BASEDIR defaults to `/home/jetson/openpilotV3_gokart` when openpilot imports are unavailable.

---

## IPC Files Written

| File | Format | Written By |
|------|--------|------------|
| `/tmp/engage` | `0` or `1` | `POST /engage` |
| `/tmp/autopilot` | `0` or `1` | `POST /autopilot` |
| `/tmp/exp_auto` | `0` or `1` | `POST /exp_auto` |
| `/tmp/lane_follow` | `0` or `1` | `POST /lane_follow` |
| `/tmp/speed_setting` | `0` through `5` | `POST /speed_setting` |
| `/tmp/joystick` | `throttle,steering` (two floats) | `POST /joystick` and WebSocket `/ws` |

Joystick writes use atomic rename (`/tmp/joystick.tmp` -> `/tmp/joystick`) to prevent partial reads.

## IPC Files Read (by GET /status)

| File | Purpose |
|------|---------|
| `/tmp/model_output.json` | Model steering, confidence, lane probabilities, frame count |
| `/tmp/joystick` | Current throttle and steering values |
| `/tmp/engage` | Engage state |
| `/tmp/autopilot` | Autopilot state |
| `/tmp/exp_auto` | Experimental auto state |
| `/tmp/lane_follow` | Lane follow state |
| `/tmp/lidar_stop` | Lidar emergency stop flag |
| `/tmp/speed_setting` | Speed level (0-5) |
| `/tmp/lidar_steer` | Lidar avoidance steering nudge (float) |
| `/tmp/overlay_frame.jpg` | MJPEG video feed (read by `/video_feed`) |

---

## Endpoints

### Toggle Endpoints (POST, JSON body)

All toggle endpoints accept a JSON body with a boolean field, write `1` or `0` to the corresponding `/tmp/` file, and return JSON status.

| Route | JSON Field | IPC File |
|-------|-----------|----------|
| `POST /engage` | `engaged` | `/tmp/engage` |
| `POST /autopilot` | `autopilot` | `/tmp/autopilot` |
| `POST /exp_auto` | `exp_auto` | `/tmp/exp_auto` |
| `POST /lane_follow` | `lane_follow` | `/tmp/lane_follow` |

### Speed Setting (Go-Kart Specific)

- **`POST /speed_setting`** -- JSON body with `speed_setting` as an integer 0-5. Clamped to that range. Writes to `/tmp/speed_setting`. The throttle multiplier is computed as `(speed_setting + 1) / 6.0`, so setting 0 gives ~17% throttle and setting 5 gives 100%.

### Joystick

- **`POST /joystick`** -- JSON body with `x` (throttle) and `y` (steering) as floats. Writes `x,y` to `/tmp/joystick`.
- **`GET /ws`** -- WebSocket endpoint. Accepts messages of type `testJoystick` with `data.axes[0]` = throttle and `data.axes[1]` = steering. Writes the same format to `/tmp/joystick`.

**Zero-skip behavior:** When the joystick sends `(0.0, 0.0)` and any autonomous mode is active (autopilot, exp_auto, or lane_follow reads as `1`), the write to `/tmp/joystick` is skipped entirely. This prevents the web UI idle state from zeroing out autonomous steering commands. The WebSocket handler does NOT have this skip logic -- only the POST handler does.

### Video and Status

- **`GET /video_feed`** -- MJPEG streaming endpoint. Reads `/tmp/overlay_frame.jpg` every 100ms and streams changed frames as multipart JPEG.
- **`GET /status`** -- Returns JSON with current model output, joystick values, all mode flags, lidar steer nudge, and a computed `gokart` object. The `gokart` object contains the final 6-value serial output that would be sent to the Arduino: `steer`, `brake`, `arm`, `throttle`, `direction`, `speed_setting`, `multiplier`, and the formatted `serial_line` string.

### Go-Kart Status Computation

The `/status` endpoint computes the final go-kart actuator values inline (same logic as `output_serial.py`):

- If not engaged: all outputs are zero.
- If lidar_stop is active: steering = joystick + lidar_nudge (clamped -1 to 1), throttle = 0, brake = 1.
- Otherwise: steering = joystick + lidar_nudge (clamped), throttle = raw_joystick * multiplier, brake = 0.
- Direction is always 1 (forward).

### WebRTC and Sound

- **`POST /offer`** -- WebRTC signaling. Forwards the SDP offer to webrtcd running on localhost:5001. Returns 503 if WebRTC is not available.
- **`POST /sound`** -- Plays a WAV sound file. Accepts `{"sound": "engage"}`, `{"sound": "disengage"}`, or `{"sound": "error"}`. Sound files are at `selfdrive/assets/sounds/`.
- **`GET /ping`** -- Returns "pong". Health check.

---

## Utility Functions

- **`play_sound(sound)`** -- Plays WAV files using pyaudio. Supports "engage", "disengage", and "error". Skips silently if pyaudio is not installed.
- **`create_ssl_cert(cert_path, key_path)`** -- Generates a self-signed SSL certificate using openssl CLI.
- **`create_ssl_context()`** -- Creates or loads SSL cert/key from `tools/bodyteleop/cert.pem` and `key.pem`. Auto-generates on first run.

---

## Differences from Scooter Version

- Has `POST /speed_setting` endpoint (scooter does not).
- The `/status` endpoint computes a `gokart` object with final 6-value serial line and throttle multiplier.
- The `/status` endpoint reads `/tmp/lidar_steer` and `/tmp/speed_setting` (scooter does not).
- No CORS middleware (scooter uses `aiohttp_cors`).
- No GPS, summon, waypoints, or nav_status endpoints (those are scooter-specific).
- BASEDIR defaults to `/home/jetson/openpilotV3_gokart` instead of `/home/jetson/openpilotV3`.

---

## How to Modify

- **Change port:** Edit the `port=5000` parameter in `web.run_app()` at the bottom of `main()`.
- **Add a new toggle:** Copy any toggle handler (e.g., `engage()`). Create a new async function that reads a JSON field, writes to a new `/tmp/` file, and returns JSON. Register it with `app.router.add_post("/new_route", handler)`.
- **Change joystick zero-skip logic:** Edit the zero-check block in the `joystick()` function. The list of flag files checked is `["/tmp/autopilot", "/tmp/exp_auto", "/tmp/lane_follow"]`.
- **Change speed range:** Edit the `speed_setting()` function. The clamp is `max(0, min(5, ss))`. The multiplier formula `(ss + 1) / 6.0` is in the `status()` function.
- **Disable SSL:** Remove `ssl_context=ssl_context` from `web.run_app()`.
