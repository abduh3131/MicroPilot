## Video Feed

Plays a video file into the shared camera file for offline testing.

### Overview

This script opens a video file with OpenCV and writes each frame as a JPEG to `/tmp/camera_frame.jpg` at a target frame rate. It replaces `webcam_capture.py` during testing with recorded video. The downstream pipeline (`lane_follow.py`, `overlay_stream.py`) reads `/tmp/camera_frame.jpg` regardless of whether it came from a real camera or this script.

- **Lines of code**: 78
- **Default frame rate**: 10 fps

---

### IPC

| Direction | Path                      | Format | Description                  |
|-----------|---------------------------|--------|------------------------------|
| Write     | `/tmp/camera_frame.jpg`   | JPEG   | Current video frame as JPEG  |

---

### Functions

#### `run(video_path, fps, loop, flip)`

Main playback loop. Opens the video file at `video_path` with OpenCV, reads frames one at a time, and writes each to `/tmp/camera_frame.jpg` at the target fps. If `loop` is enabled, the video restarts from the beginning when it reaches the end. If `flip` is enabled, each frame is flipped horizontally before writing.

#### `main()`

Entry point. Parses command-line arguments and calls `run()`.

**Arguments:**

| Argument     | Type       | Default | Description                          |
|--------------|------------|---------|--------------------------------------|
| `video`      | positional | --      | Path to the video file               |
| `--fps`      | optional   | `10`    | Target playback frame rate           |
| `--loop`     | flag       | off     | Loop video when it reaches the end   |
| `--flip`     | flag       | off     | Flip frames horizontally             |

---

### When to Use

Use `video_feed.py` instead of `webcam_capture.py` when testing with a recorded video file. The rest of the pipeline operates identically because it reads from the same `/tmp/camera_frame.jpg` path.

---

### How to Modify

- **Change playback speed**: Pass `--fps` with the desired frame rate.
- **Enable looping**: Add the `--loop` flag.
- **Mirror the video**: Add the `--flip` flag.
