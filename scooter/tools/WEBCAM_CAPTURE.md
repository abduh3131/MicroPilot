## Webcam Capture

Captures frames from a USB webcam and writes them to a shared file for downstream consumers.

### Overview

This script opens a USB webcam via the V4L2 backend with MJPEG codec, captures frames at a target frame rate, and writes each frame as a JPEG to `/tmp/camera_frame.jpg`. The write is atomic: each frame is first written to `/tmp/_camera_tmp.jpg`, then renamed to the final path. This prevents downstream readers from seeing a partially written file.

The script exits automatically after 50 consecutive read errors from the camera device.

- **Lines of code**: 88
- **Default resolution**: 640x480
- **Default frame rate**: 20 fps
- **Output path**: `/tmp/camera_frame.jpg`

---

### Functions

#### `run(device, fps, width, height)`

Main capture loop. Opens the V4L2 device at the given index, sets the MJPG fourcc codec, and configures the requested resolution. Enters a loop that reads frames and writes them as JPEG to `/tmp/camera_frame.jpg` using atomic rename. Throttles to the target fps using a sleep calculation. Prints actual measured fps to the console every 5 seconds.

#### `main()`

Entry point. Parses command-line arguments and calls `run()`.

**Arguments:**

| Flag       | Default | Description              |
|------------|---------|--------------------------|
| `--device` | `0`     | V4L2 camera device index |
| `--fps`    | `20`    | Target frames per second |
| `--width`  | `640`   | Capture width in pixels  |
| `--height` | `480`   | Capture height in pixels |

---

### IPC

| Direction | Path                      | Format | Description                  |
|-----------|---------------------------|--------|------------------------------|
| Write     | `/tmp/camera_frame.jpg`   | JPEG   | Latest captured camera frame |

---

### How to Modify

- **Change resolution**: Pass `--width` and `--height` flags on the command line.
- **Change camera device**: Pass `--device` with the device index (0, 1, 2, etc.).
- **Change output path**: Edit the `FRAME_FILE` constant at the top of the script.
- **Change JPEG quality**: Add a quality parameter to the `cv2.imwrite` call, e.g., `cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])`.
