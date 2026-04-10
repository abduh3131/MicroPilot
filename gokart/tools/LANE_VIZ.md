## Lane Viz

Offline visualization tool that runs the supercombo model on a video file and produces an annotated output video with lane lines and planned path overlaid.

### Overview

This is a standalone offline tool, not part of the live pipeline. It reads a video file frame by frame, runs the supercombo TensorRT model on each frame, draws lane lines and the planned driving path, and saves the annotated result as an output video file. It is useful for evaluating model performance on recorded footage without running the full system.

- **Lines of code**: 511
- **Default output**: same directory as input, with `_lanes` suffix

---

### Functions

#### `preprocess_frame(bgr_img)`

Converts a BGR image to the YUV format expected by the supercombo model. Uses quadrant crop for Y channel subsampling (an older preprocessing variant compared to the subsampling used in `supercombo_adapter`).

#### `parse_lane_lines_full(output)`

Extracts 4 lane lines from the raw model output tensor. Each lane line has 33 points with x/y/z coordinates and a probability value.

#### `parse_plan_full(output)`

Extracts the planned driving path from the model output. Picks the best of 5 plan hypotheses based on confidence scores.

#### `compute_steering(lane_info, plan_info)`

Computes a steering angle using a 3-tier strategy, the same logic as `supercombo_adapter`.

#### `road_to_pixel()`

Projects a 3D road coordinate to a 2D image pixel using a pinhole camera model.

#### `draw_lane_line()`

Draws a single lane line on the image as a series of connected line segments.

#### `draw_path_corridor()`

Draws the planned path as a filled polygon corridor on the image.

#### `draw_steering_arrow()`

Draws an arrow indicating the computed steering direction.

#### `draw_confidence_bar()`

Draws a horizontal bar showing model confidence level.

#### `draw_hud()`

Draws the heads-up display with steering value, confidence, and lane probabilities.

#### `run(video_path, output_path, fps, traffic_conv, max_frames)`

Main processing loop. Opens the input video, processes each frame through the model, draws all overlays, and writes the annotated frame to the output video. If `max_frames` is set, stops after that many frames.

#### `main()`

Entry point. Parses command-line arguments and calls `run()`.

**Arguments:**

| Argument        | Type       | Default       | Description                              |
|-----------------|------------|---------------|------------------------------------------|
| `video`         | positional | --            | Path to input video file                 |
| `--output`      | optional   | auto-named    | Path for the output annotated video      |
| `--fps`         | optional   | from input    | Output video frame rate                  |
| `--rhd`         | flag       | off           | Right-hand drive (flips traffic logic)   |
| `--max-frames`  | optional   | all           | Stop after N frames                      |

---

### How to Modify

- **Limit processing time**: Pass `--max-frames` to process only a subset of the video.
- **Change output location**: Pass `--output` with the desired file path.
- **Test right-hand drive**: Add the `--rhd` flag.
