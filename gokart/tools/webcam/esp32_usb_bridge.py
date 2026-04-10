#!/usr/bin/env python3
"""pulls jpeg frames from an esp32 cam over wifi and feeds them into openpilot"""

import os
import time
import signal
import sys
import urllib.request

ESP32_URL = os.getenv("ESP32_URL", "http://172.20.10.12/capture")
FRAME_FILE = "/tmp/camera_frame.jpg"
TARGET_FPS = 10

HAS_CEREAL = False
HAS_CV2 = False
HAS_AV = False

try:
  import cv2
  HAS_CV2 = True
except ImportError:
  pass

try:
  import av
  import numpy as np
  HAS_AV = True
except ImportError:
  pass

try:
  from cereal import messaging, car
  from msgq.visionipc import VisionIpcServer, VisionStreamType
  from openpilot.common.params import Params
  HAS_CEREAL = True
except ImportError:
  pass


class ESP32Bridge:
  def __init__(self):
    self.running = True
    self.frame_count = 0
    self.vipc_server = None
    self.pm = None

    if HAS_CEREAL:
      print("[esp32_bridge] cereal available, full openpilot integration")
      self.pm = messaging.PubMaster(['roadCameraState', 'deviceState',
                                      'carParams', 'carState', 'pandaStates'])
      self.vipc_server = VisionIpcServer("camerad")
      self.vipc_server.create_buffers(VisionStreamType.VISION_STREAM_ROAD, 40, 1928, 1208)
      self.vipc_server.start_listener()

      params = Params()
      params.put_bool("IsDriverViewEnabled", False)
      params.put_bool("Passive", False)
      params.put_bool("OpenpilotEnabledToggle", True)

      import threading
      self.sys_thread = threading.Thread(target=self._publish_system_state, daemon=True)
      self.sys_thread.start()
    else:
      print("[esp32_bridge] cereal not available, file-based mode only")
      print("[esp32_bridge] Frames saved to " + FRAME_FILE)

  def _publish_system_state(self):
    """Publish fake car/device state for openpilot pipeline."""
    fc = 0
    while self.running:
      dat = messaging.new_message('deviceState')
      dat.deviceState.deviceType = "scooter"
      dat.deviceState.started = True
      dat.deviceState.startIdx = 0
      self.pm.send('deviceState', dat)

      if fc % 100 == 0:
        cp = messaging.new_message('carParams')
        cp.carParams.carFingerprint = "MOCK"
        cp.carParams.openpilotLongitudinalControl = True
        cp.carParams.brand = "mock"
        self.pm.send('carParams', cp)

      cs = messaging.new_message('carState')
      cs.carState.vEgo = 2.0
      cs.carState.gearShifter = car.CarState.GearShifter.drive
      cs.carState.cruiseState.enabled = True
      cs.carState.cruiseState.available = True
      cs.carState.cruiseState.speed = 2.0
      self.pm.send('carState', cs)

      ps = messaging.new_message('pandaStates', 1)
      ps.pandaStates[0].ignitionLine = True
      ps.pandaStates[0].pandaType = "dos"
      self.pm.send('pandaStates', ps)

      time.sleep(0.01)
      fc += 1

  def _send_to_vipc(self, jpeg_data):
    """Convert JPEG to NV12 and publish via VisionIPC."""
    if not (HAS_CV2 and HAS_AV and self.vipc_server):
      return

    try:
      import numpy as np
      arr = np.frombuffer(jpeg_data, dtype=np.uint8)
      bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
      if bgr is None:
        return
      bgr = cv2.resize(bgr, (1928, 1208))
      frame = av.VideoFrame.from_ndarray(bgr, format='bgr24')
      yuv = frame.reformat(format='nv12').to_ndarray()
      yuv_data = yuv.data.tobytes()

      eof = int(self.frame_count * 0.05 * 1e9)
      self.vipc_server.send(VisionStreamType.VISION_STREAM_ROAD,
                            yuv_data, self.frame_count, eof, eof)

      dat = messaging.new_message('roadCameraState')
      dat.valid = True
      dat.roadCameraState = {
        "frameId": self.frame_count,
        "transform": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "image": yuv_data[:100],
        "sensor": "unknown",
      }
      self.pm.send('roadCameraState', dat)
    except Exception as e:
      if self.frame_count % 50 == 0:
        print("[esp32_bridge] VIPC error: " + str(e))

  def run(self):
    """main loop that grabs frames from the esp32 and distributes them"""
    print("[esp32_bridge] Starting. URL: " + ESP32_URL)
    print("[esp32_bridge] Target FPS: " + str(TARGET_FPS))

    period = 1.0 / TARGET_FPS
    last_fps_time = time.time()
    fps_count = 0

    while self.running:
      t0 = time.time()

      try:
        resp = urllib.request.urlopen(ESP32_URL, timeout=5)
        jpeg_data = resp.read()
      except Exception as e:
        if self.frame_count == 0:
          print("[esp32_bridge] Fetch error: " + str(e))
        time.sleep(1)
        continue

      if not jpeg_data or len(jpeg_data) < 100:
        continue

      # Save frame to file (for all modes)
      try:
        tmp = FRAME_FILE + ".tmp"
        with open(tmp, "wb") as f:
          f.write(jpeg_data)
        os.rename(tmp, FRAME_FILE)
      except Exception:
        pass

      # Send to openpilot pipeline if available
      if HAS_CEREAL:
        self._send_to_vipc(jpeg_data)

      self.frame_count += 1
      fps_count += 1

      # FPS stats every 5 seconds
      now = time.time()
      if now - last_fps_time >= 5.0:
        fps = fps_count / (now - last_fps_time)
        mode = "VIPC+file" if HAS_CEREAL else "file-only"
        print("[esp32_bridge] frames=" + str(self.frame_count) +
              " fps=" + str(round(fps, 1)) +
              " mode=" + mode)
        fps_count = 0
        last_fps_time = now

      elapsed = time.time() - t0
      if elapsed < period:
        time.sleep(period - elapsed)

  def stop(self):
    self.running = False


def main():
  signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
  signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

  bridge = ESP32Bridge()
  try:
    bridge.run()
  finally:
    bridge.stop()
    print("[esp32_bridge] Stopped.")


if __name__ == "__main__":
  main()
