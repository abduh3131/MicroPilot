## Camera Bridge

Pulls an MJPEG video stream from a WiFi ESP32-CAM and writes frames to the shared camera file.

### Overview

This script connects to an ESP32-CAM over WiFi, receives MJPEG video frames, and writes each frame as a JPEG to `/tmp/camera_frame.jpg`. It is an alternative to `webcam_capture.py` for setups where the camera is a wireless ESP32-CAM instead of a USB webcam. Both scripts write to the same output path, so downstream consumers (lane_follow, overlay_stream) work identically regardless of camera source.

The script auto-reconnects on network errors.

- **Lines of code**: 143
- **Default stream URL**: `http://172.20.10.12:81/stream`
- **Default frame rate**: 15 fps
- **Output path**: `/tmp/camera_frame.jpg`

---

### IPC

| Direction | Path                      | Format | Description                  |
|-----------|---------------------------|--------|------------------------------|
| Write     | `/tmp/camera_frame.jpg`   | JPEG   | Latest captured camera frame |

---

### Functions

#### `read_mjpeg_stream(url, target_fps)`

Primary capture mode. Connects to the MJPEG stream endpoint, reads the byte stream, and parses individual JPEG frames by locating FFD8 (start of JPEG) and FFD9 (end of JPEG) markers in the data. Each complete frame is written atomically to `/tmp/camera_frame.jpg`. Auto-reconnects on any connection or read error.

#### `read_capture_mode(url, target_fps)`

Fallback capture mode. Instead of reading a continuous MJPEG stream, fetches one JPEG image at a time from the ESP32-CAM `/capture` endpoint. Slower than stream mode but more reliable on poor WiFi connections.

#### `main()`

Entry point. Parses command-line arguments and calls the appropriate capture function.

**Arguments:**

| Flag              | Default                           | Description                        |
|-------------------|-----------------------------------|------------------------------------|
| `--url`           | `http://172.20.10.12:81/stream`   | MJPEG stream URL                   |
| `--capture-url`   | (derived from --url)              | Single-capture endpoint URL        |
| `--fps`           | `15`                              | Target frames per second           |
| `--capture-mode`  | (flag)                            | Use single-capture mode instead    |

---

### When to Use

Use `camera_bridge.py` when the camera is a WiFi ESP32-CAM. Use `webcam_capture.py` when the camera is a USB webcam. Both produce the same `/tmp/camera_frame.jpg` output file.

---

### How to Modify

- **Change ESP32-CAM address**: Pass `--url` with the correct IP and port.
- **Switch to capture mode**: Add the `--capture-mode` flag for unreliable WiFi.
- **Change frame rate**: Pass `--fps` with the desired value.
