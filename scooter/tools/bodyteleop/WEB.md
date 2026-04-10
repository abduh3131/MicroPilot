# web.py -- Browser Control Panel (Scooter)

Hosts the browser-based control panel for the scooter platform. Serves HTML/JS/CSS from `static/` over HTTPS on port 5000. Provides REST and WebSocket endpoints for engage, lane follow, experimental autopilot, full autopilot, manual joystick control, GPS/navigation, and live video streaming.

BASEDIR defaults to `/home/jetson/openpilotV3` when openpilot imports are unavailable.

---

## IPC Files Written

| File | Format | Written By |
|------|--------|------------|
| `/tmp/engage` | `0` or `1` | `POST /engage` |
| `/tmp/autopilot` | `0` or `1` | `POST /autopilot` |
| `/tmp/exp_auto` | `0` or `1` | `POST /exp_auto` |
| `/tmp/lane_follow` | `0` or `1` | `POST /lane_follow` |
| `/tmp/joystick` | `throttle,steering` (two floats) | `POST /joystick` and WebSocket `/ws` |
| `/tmp/current_goal` | JSON object with lat/lon | `POST /summon` |
| `/tmp/nav_status` | Text string | `POST /summon_cancel` |

Joystick writes use atomic rename (`/tmp/joystick.tmp` -> `/tmp/joystick`) to prevent partial reads.

## IPC Files Read (by GET /status)

| File | Purpose |
|------|---------|
| `/tmp/model_output.json` | Model steering, confidence, lane probabilities, frame count, timestamp |
| `/tmp/joystick` | Current throttle and steering values |
| `/tmp/engage` | Engage state |
| `/tmp/autopilot` | Autopilot state |
| `/tmp/exp_auto` | Experimental auto state |
| `/tmp/lane_follow` | Lane follow state |
| `/tmp/lidar_stop` | Lidar emergency stop flag |
| `/tmp/overlay_frame.jpg` | MJPEG video feed (read by `/video_feed`) |
| `/tmp/gps_fix` | GPS latitude, longitude, altitude, status (read by `/gps`) |
| `/home/jetson/waypoints.json` | Saved waypoint list (read/written by `/waypoints`) |

---

## Endpoints

### Toggle Endpoints (POST, JSON body)

All toggle endpoints follow the same pattern: accept a JSON body with a boolean field, write `1` or `0` to the corresponding `/tmp/` file, return JSON status.

| Route | JSON Field | IPC File |
|-------|-----------|----------|
| `POST /engage` | `engaged` | `/tmp/engage` |
| `POST /autopilot` | `autopilot` | `/tmp/autopilot` |
| `POST /exp_auto` | `exp_auto` | `/tmp/exp_auto` |
| `POST /lane_follow` | `lane_follow` | `/tmp/lane_follow` |

### Joystick

- **`POST /joystick`** -- JSON body with `x` (throttle) and `y` (steering) as floats. Writes `x,y` to `/tmp/joystick`.
- **`GET /ws`** -- WebSocket endpoint. Accepts messages of type `testJoystick` with `data.axes[0]` = throttle and `data.axes[1]` = steering. Writes the same format to `/tmp/joystick`.

**Zero-skip behavior:** When the joystick sends `(0.0, 0.0)` and any autonomous mode is active (autopilot, exp_auto, or lane_follow reads as `1`), the write to `/tmp/joystick` is skipped entirely. This prevents the web UI idle state from zeroing out autonomous steering commands. The WebSocket handler does NOT have this skip logic -- only the POST handler does.

### Video and Status

- **`GET /video_feed`** -- MJPEG streaming endpoint. Reads `/tmp/overlay_frame.jpg` every 100ms and streams changed frames as multipart JPEG.
- **`GET /status`** -- Returns JSON with current model output (steering, confidence, plan_prob, lane probabilities, frame, timestamp), joystick values, and all mode flags. Skips large arrays from model output for performance.

### Navigation and GPS (Scooter-Specific)

- **`POST /summon`** -- Accepts JSON with goal coordinates. Writes atomically to `/tmp/current_goal`.
- **`POST /summon_cancel`** -- Removes `/tmp/current_goal` and writes "Idle - cancelled" to `/tmp/nav_status`.
- **`GET /nav_status`** -- Reads `/tmp/nav_status` and returns it as JSON.
- **`GET /gps`** -- Reads `/tmp/gps_fix` (JSON with lat, lon, alt, status). Replaces NaN values with null.
- **`GET /waypoints`** -- Returns the saved waypoint list from `/home/jetson/waypoints.json`.
- **`POST /waypoints`** -- Appends a new waypoint to the list.

### WebRTC and Sound

- **`POST /offer`** -- WebRTC signaling. Forwards the SDP offer to webrtcd running on localhost:5001. Returns 503 if WebRTC is not available.
- **`POST /sound`** -- Plays a WAV sound file. Accepts `{"sound": "engage"}`, `{"sound": "disengage"}`, or `{"sound": "error"}`. Sound files are at `selfdrive/assets/sounds/`.
- **`GET /ping`** -- Returns "pong". Health check.

---

## Utility Functions

- **`play_sound(sound)`** -- Plays WAV files using pyaudio. Supports "engage", "disengage", and "error". Skips silently if pyaudio is not installed.
- **`create_ssl_cert(cert_path, key_path)`** -- Generates a self-signed SSL certificate using openssl CLI. Certificate is valid for 365 days.
- **`create_ssl_context()`** -- Creates or loads SSL cert/key from `tools/bodyteleop/cert.pem` and `key.pem`. Auto-generates on first run.

---

## CORS

The scooter version uses `aiohttp_cors` to enable cross-origin requests from any domain. All routes registered before the CORS setup get CORS headers. Routes added after (autopilot, exp_auto, lane_follow, video_feed, status) do not have explicit CORS -- they rely on being accessed from the same origin or via the static page.

---

## How to Modify

- **Change port:** Edit the `port=5000` parameter in `web.run_app()` at the bottom of `main()`.
- **Add a new toggle:** Copy any toggle handler (e.g., `engage()`). Create a new async function that reads a JSON field, writes to a new `/tmp/` file, and returns JSON. Register it with `app.router.add_post("/new_route", handler)`.
- **Change joystick zero-skip logic:** Edit the zero-check block in the `joystick()` function. The list of flag files checked is `["/tmp/autopilot", "/tmp/exp_auto", "/tmp/lane_follow"]`.
- **Add new status fields:** Edit the `status()` function. Add a new file read following the existing pattern.
- **Disable SSL:** Remove the `ssl_context` variable and the `ssl_context=` parameter from `web.run_app()`. The server will then run plain HTTP.
