import asyncio
import dataclasses
import json
import logging
import os
import ssl
import subprocess

try:
  import pyaudio
  import wave
  HAS_AUDIO = True
except (ImportError, TypeError):
  HAS_AUDIO = False

from aiohttp import web
from aiohttp import ClientSession

try:
  from openpilot.common.basedir import BASEDIR
except ImportError:
  BASEDIR = "/home/jetson/openpilotV3_gokart"

try:
  from openpilot.common.params import Params
except ImportError:
  class Params:
    def put_bool(self, key, val): pass

try:
  from openpilot.system.webrtc.webrtcd import StreamRequestBody
  HAS_WEBRTC = True
except (ImportError, TypeError):
  HAS_WEBRTC = False
  @dataclasses.dataclass
  class StreamRequestBody:
    sdp: str = ""
    video_streams: list = dataclasses.field(default_factory=list)
    incoming_services: list = dataclasses.field(default_factory=list)
    outgoing_services: list = dataclasses.field(default_factory=list)

logger = logging.getLogger("bodyteleop")
logging.basicConfig(level=logging.INFO)

TELEOPDIR = BASEDIR + "/tools/bodyteleop"
WEBRTCD_HOST, WEBRTCD_PORT = "localhost", 5001


## UTILS
async def play_sound(sound):
  if not HAS_AUDIO:
    logger.warning("pyaudio not available, skipping sound")
    return
  SOUNDS = {
    "engage": "selfdrive/assets/sounds/engage.wav",
    "disengage": "selfdrive/assets/sounds/disengage.wav",
    "error": "selfdrive/assets/sounds/warning_immediate.wav",
  }
  if sound not in SOUNDS:
    return
  sound_path = os.path.join(BASEDIR, SOUNDS[sound])
  if not os.path.exists(sound_path):
    return
  chunk = 5120
  with wave.open(sound_path, "rb") as wf:
    def callback(in_data, frame_count, time_info, status):
      data = wf.readframes(frame_count)
      return data, pyaudio.paContinue
    p = pyaudio.PyAudio()
    stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True,
                    frames_per_buffer=chunk,
                    stream_callback=callback)
    stream.start_stream()
    while stream.is_active():
      await asyncio.sleep(0)
    stream.stop_stream()
    stream.close()
    p.terminate()


def create_ssl_cert(cert_path, key_path):
  try:
    proc = subprocess.run(
      'openssl req -x509 -newkey rsa:4096 -nodes -out ' + cert_path + ' -keyout ' + key_path +
      ' -days 365 -subj "/C=US/ST=California/O=commaai/OU=comma body"',
      stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    proc.check_returncode()
  except subprocess.CalledProcessError as ex:
    raise ValueError("Error creating SSL cert")


def create_ssl_context():
  cert_path = os.path.join(TELEOPDIR, "cert.pem")
  key_path = os.path.join(TELEOPDIR, "key.pem")
  if not os.path.exists(cert_path) or not os.path.exists(key_path):
    logger.info("Creating certificate...")
    create_ssl_cert(cert_path, key_path)
  else:
    logger.info("Certificate exists!")
  ssl_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_SERVER)
  ssl_context.load_cert_chain(cert_path, key_path)
  return ssl_context


## ENDPOINTS
async def index(request):
  with open(os.path.join(TELEOPDIR, "static", "index.html")) as f:
    content = f.read()
    return web.Response(content_type="text/html", text=content)


async def ping(request):
  return web.Response(text="pong")


async def sound(request):
  params = await request.json()
  await play_sound(params["sound"])
  return web.json_response({"status": "ok"})


async def engage(request):
  data = await request.json()
  engaged = data.get("engaged", False)
  with open('/tmp/engage', 'w') as f:
    f.write('1' if engaged else '0')
  logger.info("Engage " + ("ON" if engaged else "OFF"))
  return web.json_response({"status": "ok", "engaged": engaged})


async def autopilot(request):
  data = await request.json()
  active = data.get("autopilot", False)
  with open('/tmp/autopilot', 'w') as f:
    f.write('1' if active else '0')
  logger.info("Autopilot " + ("ON" if active else "OFF"))
  return web.json_response({"status": "ok", "autopilot": active})


async def exp_auto(request):
  data = await request.json()
  active = data.get("exp_auto", False)
  with open('/tmp/exp_auto', 'w') as f:
    f.write('1' if active else '0')
  logger.info("Exp auto " + ("ON" if active else "OFF"))
  return web.json_response({"status": "ok", "exp_auto": active})


async def lane_follow(request):
  data = await request.json()
  active = data.get("lane_follow", False)
  with open('/tmp/lane_follow', 'w') as f:
    f.write('1' if active else '0')
  logger.info("Lane follow " + ("ON" if active else "OFF"))
  return web.json_response({"status": "ok", "lane_follow": active})


async def speed_setting(request):
  # gokart speed setting 0-5
  data = await request.json()
  ss = int(data.get("speed_setting", 3))
  ss = max(0, min(5, ss))
  with open('/tmp/speed_setting', 'w') as f:
    f.write(str(ss))
  logger.info("Speed setting: " + str(ss))
  return web.json_response({"status": "ok", "speed_setting": ss})


async def joystick(request):
  data = await request.json()
  x = float(data.get("x", 0.0))
  y = float(data.get("y", 0.0))
  # Skip zero joystick when autonomous mode active
  if x == 0.0 and y == 0.0:
    for flag in ["/tmp/autopilot", "/tmp/exp_auto", "/tmp/lane_follow"]:
      try:
        fh = open(flag)
        val = fh.read().strip()
        fh.close()
        if val == "1":
          return web.json_response({"status": "ok"})
      except Exception:
        pass
  tmp = "/tmp/joystick.tmp"
  with open(tmp, "w") as f:
    f.write(str(x) + "," + str(y))
  os.rename(tmp, "/tmp/joystick")
  return web.json_response({"status": "ok"})

async def ws_handler(request):
  ws = web.WebSocketResponse()
  await ws.prepare(request)
  logger.info("WS joystick connected")
  try:
    async for msg in ws:
      if msg.type == web.WSMsgType.TEXT:
        try:
          data = json.loads(msg.data)
          if data.get("type") == "testJoystick":
            axes = data["data"]["axes"]
            x, y = float(axes[0]), float(axes[1])
            tmp = "/tmp/joystick.tmp"
            with open(tmp, "w") as f:
              f.write(str(x) + "," + str(y))
            os.rename(tmp, "/tmp/joystick")
        except Exception:
          pass
      elif msg.type == web.WSMsgType.ERROR:
        break
  finally:
    logger.info("WS joystick disconnected")
  return ws


async def offer(request):
  if not HAS_WEBRTC:
    return web.json_response({"error": "no webrtc"}, status=503)
  params = await request.json()
  body = StreamRequestBody(params["sdp"], ["driver"], ["testJoystick"], ["carState"])
  body_json = json.dumps(dataclasses.asdict(body))
  webrtcd_url = "http://" + WEBRTCD_HOST + ":" + str(WEBRTCD_PORT) + "/stream"
  try:
    async with ClientSession() as session, session.post(webrtcd_url, data=body_json) as resp:
      assert resp.status == 200
      answer = await resp.json()
      return web.json_response(answer)
  except Exception as e:
    return web.json_response({"error": str(e)}, status=503)


OVERLAY_FRAME = "/tmp/overlay_frame.jpg"
MODEL_OUTPUT = "/tmp/model_output.json"


async def status(request):
  data = {}
  # model output
  try:
    if os.path.exists(MODEL_OUTPUT):
      with open(MODEL_OUTPUT, 'r') as f:
        model = json.load(f)
      data['model'] = {
        'steering': model.get('steering', 0),
        'confidence': model.get('confidence', 0),
        'plan_prob': model.get('plan_prob', 0),
        'left_near_y': model.get('left_near_y', 0),
        'right_near_y': model.get('right_near_y', 0),
        'left_near_prob': model.get('left_near_prob', 0),
        'right_near_prob': model.get('right_near_prob', 0),
        'frame': model.get('frame', 0),
      }
  except Exception:
    pass
  # joystick raw
  try:
    if os.path.exists('/tmp/joystick'):
      with open('/tmp/joystick', 'r') as f:
        parts = f.read().strip().split(',')
        data['joystick'] = {'throttle': float(parts[0]), 'steering': float(parts[1])}
  except Exception:
    pass
  # ipc flags
  for name in ['engage', 'autopilot', 'exp_auto', 'lane_follow', 'lidar_stop', 'speed_setting']:
    try:
      with open('/tmp/' + name, 'r') as f:
        data[name] = f.read().strip()
    except Exception:
      data[name] = '0'
  # lidar steer
  try:
    data['lidar_steer'] = float(open('/tmp/lidar_steer').read().strip())
  except Exception:
    data['lidar_steer'] = 0.0
  # compute gokart 6 vals (same as output_serial.py)
  engaged = data.get('engage') == '1'
  lidar_stop = data.get('lidar_stop') == '1'
  joy_x = data.get('joystick', {}).get('throttle', 0.0)
  joy_y = data.get('joystick', {}).get('steering', 0.0)
  lidar_nudge = data.get('lidar_steer', 0.0)
  try:
    ss = int(data.get('speed_setting', '3'))
    ss = max(0, min(5, ss))
  except Exception:
    ss = 3
  multiplier = (ss + 1) / 6.0
  arm = 1 if engaged else 0
  direction = 1
  if not engaged:
    steer_out = 0.0; throttle_out = 0.0; brake_out = 0.0
  elif lidar_stop:
    steer_out = max(-1.0, min(1.0, joy_y + lidar_nudge))
    throttle_out = 0.0; brake_out = 1.0
  else:
    steer_out = max(-1.0, min(1.0, joy_y + lidar_nudge))
    raw_thr = max(-1.0, min(1.0, joy_x))
    throttle_out = raw_thr * multiplier; brake_out = 0.0
  data['gokart'] = {
    'steer': round(steer_out, 3),
    'brake': round(brake_out, 2),
    'arm': arm,
    'throttle': round(throttle_out, 3),
    'direction': direction,
    'speed_setting': ss,
    'multiplier': round(multiplier, 2),
    'serial_line': str(round(steer_out,2))+','+str(round(brake_out,2))+','+str(arm)+','+str(round(throttle_out,2))+','+str(direction)+','+str(ss),
  }
  return web.json_response(data)


async def video_feed(request):
  boundary = "frame"
  response = web.StreamResponse(
    status=200, reason='OK',
    headers={
      'Content-Type': 'multipart/x-mixed-replace; boundary=' + boundary,
      'Cache-Control': 'no-cache',
    },
  )
  await response.prepare(request)
  last_data = None
  try:
    while True:
      try:
        if os.path.exists(OVERLAY_FRAME):
          with open(OVERLAY_FRAME, 'rb') as f:
            data = f.read()
          if data and data != last_data:
            last_data = data
            await response.write(
              b'--' + boundary.encode() + b'\r\n'
              b'Content-Type: image/jpeg\r\n'
              b'Content-Length: ' + str(len(data)).encode() + b'\r\n\r\n'
              + data + b'\r\n'
            )
      except Exception:
        pass
      await asyncio.sleep(0.1)
  except (ConnectionResetError, asyncio.CancelledError):
    pass
  return response


def main():
  Params().put_bool("JoystickDebugMode", True)
  ssl_context = create_ssl_context()
  app = web.Application()
  app.router.add_get("/", index)
  app.router.add_get("/ping", ping, allow_head=True)
  app.router.add_post("/offer", offer)
  app.router.add_post("/sound", sound)
  app.router.add_post("/engage", engage)
  app.router.add_get("/ws", ws_handler)
  app.router.add_post("/joystick", joystick)
  app.router.add_post("/autopilot", autopilot)
  app.router.add_post("/exp_auto", exp_auto)
  app.router.add_post("/lane_follow", lane_follow)
  app.router.add_post("/speed_setting", speed_setting)
  app.router.add_get("/video_feed", video_feed)
  app.router.add_get("/status", status)
  app.router.add_static('/static', os.path.join(TELEOPDIR, 'static'))
  web.run_app(app, access_log=None, host="0.0.0.0", port=5000, ssl_context=ssl_context)


if __name__ == "__main__":
  main()
