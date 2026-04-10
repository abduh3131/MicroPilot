## Overlay Stream

Draws lane lines and the planned path on the camera feed, producing an annotated overlay image for the web UI.

### Overview

This script reads the latest camera frame and model output, draws lane lines, the planned driving path, a horizon line, and a heads-up display onto the image, then writes the result to `/tmp/overlay_frame.jpg`. The web UI serves this file to display the annotated live view.

- **Lines of code**: 359
- **Default frame rate**: 20 fps

---

### Constants

| Constant         | Value   | Description                                      |
|------------------|---------|--------------------------------------------------|
| `CAM_HEIGHT`     | 1.22 m  | Camera mounting height above ground               |
| `CAM_FOCAL`      | 500.0   | Focal length in pixels for pinhole projection     |
| `CAM_HORIZON`    | 0.38    | Horizon position as a fraction of image height    |
| `MAX_DRAW_DIST`  | 80 m    | Maximum forward distance to draw lane/path points |
| `PATH_HALF_W`    | 0.9 m   | Half-width of the planned path corridor           |

---

### IPC

| Direction | Path                        | Format | Description                          |
|-----------|-----------------------------|--------|--------------------------------------|
| Read      | `/tmp/camera_frame.jpg`     | JPEG   | Raw camera frame                     |
| Read      | `/tmp/model_output.json`    | JSON   | Lane lines and plan from supercombo  |
| Read      | `/tmp/engage`               | Text   | "1" if system is engaged             |
| Read      | `/tmp/lane_follow`          | Text   | "1" if lane follow mode is active    |
| Read      | `/tmp/exp_auto`             | Text   | "1" if experimental auto is active   |
| Read      | `/tmp/lidar_stop`           | Text   | "1" if lidar emergency stop is active|
| Write     | `/tmp/overlay_frame.jpg`    | JPEG   | Annotated overlay frame              |

---

### Functions

#### `read_model_output()`

Reads `/tmp/model_output.json` and returns the parsed dictionary. Returns `None` if the file is missing or stale (older than 2 seconds).

#### `road_to_screen(x_fwd, y_lat, img_w, img_h, z)`

Converts a 3D road coordinate (forward distance, lateral offset, height) into a 2D screen pixel coordinate using a pinhole camera model. Returns floating-point pixel coordinates.

#### `road_to_pixel()`

Same as `road_to_screen()` but returns integer pixel coordinates. Returns `None` if the projected point falls outside the image bounds.

#### `draw_path_corridor(img, positions, active)`

Fills a polygon between the left and right edges of the planned driving path. The corridor is green when the system is active, grey when inactive. Draws a chevron arrow at the base of the path.

#### `draw_lane_lines(img, lane_lines)`

Draws all 4 lane lines from the model output. Inner lanes (indices 1 and 2) are drawn white and thick. Outer lanes (indices 0 and 3) are drawn grey and thin. Opacity of each line scales with its probability value from the model.

#### `draw_horizon_line(img)`

Draws a dashed yellow line across the image at the `CAM_HORIZON` fraction of image height.

#### `draw_green_border(img)`

Draws a green rectangle border around the image when the system is actively engaged.

#### `draw_hud(img, data, mode_name, lidar_stop, fps)`

Draws the heads-up display overlay containing: the current mode name, model confidence percentage, steering value, left and right lane probabilities, fps counter, and a red "LIDAR STOP" warning when lidar stop is active.

#### `draw_no_signal(img)`

Draws red "NO CAMERA" text on the image when no camera frame is available.

#### `run(fps)`

Main loop running at the specified fps (default 20). Each iteration reads the camera frame, reads the model output, draws all overlays, and writes the result to `/tmp/overlay_frame.jpg`.

#### `main()`

Entry point. Parses command-line arguments and calls `run()`.

**Arguments:**

| Flag             | Default | Description                              |
|------------------|---------|------------------------------------------|
| `--fps`          | `20`    | Target overlay frame rate                |
| `--cam-height`   | `1.22`  | Camera height above ground in meters     |
| `--cam-focal`    | `500.0` | Camera focal length in pixels            |
| `--cam-horizon`  | `0.38`  | Horizon position as fraction of height   |

---

### How to Modify

- **Change camera parameters**: Pass `--cam-height`, `--cam-focal`, or `--cam-horizon` flags.
- **Change draw distance**: Edit the `MAX_DRAW_DIST` constant.
- **Change path width**: Edit the `PATH_HALF_W` constant.
- **Change overlay colors**: Edit the color tuples in the draw functions. Colors use BGR format (OpenCV convention).
