#!/usr/bin/env python3
"""grabs the mjpeg stream from the esp32 cam over wifi and saves frames to /tmp."""

import argparse
import os
import signal
import sys
import time
import urllib.request

# ── Defaults ──
DEFAULT_URL = "http://172.20.10.12:81/stream"
DEFAULT_CAPTURE_URL = "http://172.20.10.12/capture"
DEFAULT_FPS = 15
FRAME_FILE = "/tmp/camera_frame.jpg"


def read_mjpeg_stream(url, target_fps):
  # reads the mjpeg stream and saves jpegs
  print("[camera_bridge] Connecting to " + url)
  period = 1.0 / target_fps
  frame_count = 0
  last_fps_time = time.time()
  fps_count = 0

  while True:
    try:
      req = urllib.request.Request(url)
      resp = urllib.request.urlopen(req, timeout=10)
      print("[camera_bridge] Connected! Reading stream...")

      buf = b""
      while True:
        t0 = time.time()
        chunk = resp.read(4096)
        if not chunk:
          print("[camera_bridge] Stream ended, reconnecting...")
          break
        buf += chunk

        # Find JPEG boundaries
        while True:
          start = buf.find(b"\xff\xd8")  # JPEG start
          if start < 0:
            buf = buf[-2:]  # Keep last 2 bytes in case boundary is split
            break
          end = buf.find(b"\xff\xd9", start + 2)  # JPEG end
          if end < 0:
            buf = buf[start:]  # Keep from start marker
            break

          # Extract complete JPEG frame
          frame = buf[start:end + 2]
          buf = buf[end + 2:]

          # write the frame so other scripts can read it
          tmp = FRAME_FILE + ".tmp"
          with open(tmp, "wb") as f:
            f.write(frame)
          os.rename(tmp, FRAME_FILE)

          frame_count += 1
          fps_count += 1

          # FPS stats every 5 seconds
          now = time.time()
          if now - last_fps_time >= 5.0:
            fps = fps_count / (now - last_fps_time)
            print("[camera_bridge] frames=" + str(frame_count) +
                  " fps=" + str(round(fps, 1)) +
                  " size=" + str(len(frame)) + "B")
            fps_count = 0
            last_fps_time = now

    except KeyboardInterrupt:
      raise
    except Exception as e:
      print("[camera_bridge] Error: " + str(e) + ", retrying in 2s...")
      time.sleep(2)


def read_capture_mode(url, target_fps):
  # fallback: pulls one jpeg at a time
  print("[camera_bridge] Using capture mode: " + url)
  period = 1.0 / target_fps
  frame_count = 0
  last_fps_time = time.time()
  fps_count = 0

  while True:
    t0 = time.time()
    try:
      resp = urllib.request.urlopen(url, timeout=5)
      frame = resp.read()
      if frame and len(frame) > 100:
        tmp = FRAME_FILE + ".tmp"
        with open(tmp, "wb") as f:
          f.write(frame)
        os.rename(tmp, FRAME_FILE)
        frame_count += 1
        fps_count += 1
    except Exception as e:
      if frame_count == 0:
        print("[camera_bridge] Capture error: " + str(e))

    # FPS stats
    now = time.time()
    if now - last_fps_time >= 5.0:
      fps = fps_count / (now - last_fps_time)
      print("[camera_bridge] frames=" + str(frame_count) +
            " fps=" + str(round(fps, 1)))
      fps_count = 0
      last_fps_time = now

    elapsed = time.time() - t0
    if elapsed < period:
      time.sleep(period - elapsed)


def main():
  parser = argparse.ArgumentParser(description="ESP32-CAM bridge")
  parser.add_argument("--url", default=DEFAULT_URL,
                      help="MJPEG stream URL (default: " + DEFAULT_URL + ")")
  parser.add_argument("--capture-url", default=DEFAULT_CAPTURE_URL,
                      help="Single capture URL fallback")
  parser.add_argument("--fps", type=int, default=DEFAULT_FPS,
                      help="Target FPS (default: " + str(DEFAULT_FPS) + ")")
  parser.add_argument("--capture-mode", action="store_true",
                      help="Use single capture instead of MJPEG stream")
  args = parser.parse_args()

  signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
  signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

  print("[camera_bridge] ESP32-CAM Bridge starting")
  print("[camera_bridge] Frame output: " + FRAME_FILE)

  try:
    if args.capture_mode:
      read_capture_mode(args.capture_url, args.fps)
    else:
      read_mjpeg_stream(args.url, args.fps)
  finally:
    print("[camera_bridge] Stopped.")


if __name__ == "__main__":
  main()
