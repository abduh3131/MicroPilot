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
  BASEDIR = "/home/jetson/openpilotV3"

try:
  from openpilot.common.params import Params
except ImportError:
  class Params:
    def put_bool(self, key, val): pass

# Try to import StreamRequestBody, but don't fail if webrtcd is unavailable
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

TELEOPDIR = f"{BASEDIR}/tools/bodyteleop"
WEBRTCD_HOST, WEBRTCD_PORT = "localhost", 5001


## UTILS
async def play_sound(sound: str):
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
    logger.warning(f"Sound file not found: {sound_path}")
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

## SSL
def create_ssl_cert(cert_path: str, key_path: str):
  try:
    proc = subprocess.run(f'openssl req -x509 -newkey rsa:4096 -nodes -out {cert_path} -keyout {key_path} \
                          -days 365 -subj "/C=US/ST=California/O=commaai/OU=comma body"',
                          capture_output=True, shell=True)
    proc.check_returncode()
  except subprocess.CalledProcessError as ex:
    raise ValueError(f"Error creating SSL certificate:\n[stdout]\n{proc.stdout.decode()}\n[stderr]\n{proc.stderr.decode()}") from ex


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
async def index(request: 'web.Request'):
  with open(os.path.join(TELEOPDIR, "static", "index.html")) as f:
    content = f.read()
    return web.Response(content_type="text/html", text=content)






async def nav_status(request):
  try:
    with open('/tmp/nav_status', 'r') as f:
      return web.json_response({'status': f.read().strip()})
  except Exception:
    return web.json_response({'status': ''})

async def summon_cancel(request):
  import os
  try:
    os.remove('/tmp/current_goal')
  except Exception:
    pass
  with open('/tmp/nav_status', 'w') as f:
    f.write('Idle - cancelled')
  return web.json_response({'status': 'cancelled'})

async def summon(request):
  import json as json_mod
  data = await request.json()
  with open('/tmp/current_goal.tmp', 'w') as f:
    f.write(json_mod.dumps(data))
  import os
  os.rename('/tmp/current_goal.tmp', '/tmp/current_goal')
  return web.json_response({'status': 'ok', 'goal': data})

async def waypoints(request):
  import json as json_mod
  wp_file = '/home/jetson/waypoints.json'
  if request.method == 'GET':
    try:
      with open(wp_file, 'r') as f:
        return web.Response(content_type='application/json', text=f.read())
    except Exception:
      return web.json_response([])
  elif request.method == 'POST':
    data = await request.json()
    try:
      with open(wp_file, 'r') as f:
        wps = json_mod.load(f)
    except Exception:
      wps = []
    wps.append(data)
    with open(wp_file, 'w') as f:
      json_mod.dump(wps, f)
    return web.json_response({'status': 'ok'})

async def gps(request):
  import math as _math
  import json as _json
  try:
    with open('/tmp/gps_fix', 'r') as f:
      data = _json.load(f)
    clean = {
      'lat': data['lat'] if not _math.isnan(float(data['lat'])) else None,
      'lon': data['lon'] if not _math.isnan(float(data['lon'])) else None,
      'alt': data['alt'] if not _math.isnan(float(data['alt'])) else None,
      'status': data['status']
    }
    return web.json_response(clean)
  except Exception:
    return web.json_response({'lat': None, 'lon': None, 'alt': None, 'status': -1})

async def ping(request: 'web.Request'):
  return web.Response(text="pong")


async def sound(request: 'web.Request'):
  params = await request.json()
  sound_to_play = params["sound"]

  await play_sound(sound_to_play)
  return web.json_response({"status": "ok"})


async def engage(request: 'web.Request'):
  """Toggle engagement on/off via web UI button."""
  data = await request.json()
  engaged = data.get("engaged", False)
  with open('/tmp/engage', 'w') as f:
    f.write('1' if engaged else '0')
  logger.info(f"Engagement {'ENABLED' if engaged else 'DISABLED'} via web UI")
  return web.json_response({"status": "ok", "engaged": engaged})


async def autopilot(request: 'web.Request'):
  """Toggle autopilot on/off via web UI button."""
  data = await request.json()
  active = data.get("autopilot", False)
  with open('/tmp/autopilot', 'w') as f:
    f.write('1' if active else '0')
  logger.info(f"Autopilot {'ENABLED' if active else 'DISABLED'} via web UI")
  return web.json_response({"status": "ok", "autopilot": active})


async def exp_auto(request: 'web.Request'):
  """Toggle experimental full openpilot autonomous mode."""
  data = await request.json()
  active = data.get("exp_auto", False)
  with open('/tmp/exp_auto', 'w') as f:
    f.write('1' if active else '0')
  logger.info(f"EXP AUTO {'ENABLED' if active else 'DISABLED'} via web UI")
  return web.json_response({"status": "ok", "exp_auto": active})


async def lane_follow(request: 'web.Request'):
  """Toggle lane following (openpilot vision) on/off via web UI button."""
  data = await request.json()
  active = data.get("lane_follow", False)
  with open('/tmp/lane_follow', 'w') as f:
    f.write('1' if active else '0')
  logger.info(f"Lane Follow {'ENABLED' if active else 'DISABLED'} via web UI")
  return web.json_response({"status": "ok", "lane_follow": active})


async def joystick(request: 'web.Request'):
  """Direct POST endpoint for joystick data."""
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
    f.write(f"{x},{y}")
  os.rename(tmp, "/tmp/joystick")
  return web.json_response({"status": "ok"})

async def ws_handler(request: 'web.Request'):
  """WebSocket fallback for joystick data (used when WebRTC unavailable)."""
  ws = web.WebSocketResponse()
  await ws.prepare(request)
  logger.info("WebSocket joystick client connected")
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
              f.write(f"{x},{y}")
            os.rename(tmp, "/tmp/joystick")
        except Exception:
          pass
      elif msg.type == web.WSMsgType.ERROR:
        break
  finally:
    logger.info("WebSocket joystick client disconnected")
  return ws


async def offer(request: 'web.Request'):
  if not HAS_WEBRTC:
    return web.json_response({"error": "WebRTC not available on this platform"}, status=503)

  params = await request.json()
  body = StreamRequestBody(params["sdp"], ["driver"], ["testJoystick"], ["carState"])
  body_json = json.dumps(dataclasses.asdict(body))

  logger.info("Sending offer to webrtcd...")
  webrtcd_url = f"http://{WEBRTCD_HOST}:{WEBRTCD_PORT}/stream"
  try:
    async with ClientSession() as session, session.post(webrtcd_url, data=body_json) as resp:
      assert resp.status == 200
      answer = await resp.json()
      return web.json_response(answer)
  except Exception as e:
    logger.error(f"WebRTC offer failed: {e}")
    return web.json_response({"error": str(e)}, status=503)


OVERLAY_FRAME = "/tmp/overlay_frame.jpg"
MODEL_OUTPUT = "/tmp/model_output.json"


async def status(request: 'web.Request'):
  """Return live actuator/model status for the web UI log panel."""
  data = {}
  # Model output
  try:
    if os.path.exists(MODEL_OUTPUT):
      with open(MODEL_OUTPUT, 'r') as f:
        model = json.load(f)
      # Return a subset (skip large arrays for performance)
      data['model'] = {
        'steering': model.get('steering', 0),
        'confidence': model.get('confidence', 0),
        'plan_prob': model.get('plan_prob', 0),
        'left_near_y': model.get('left_near_y', 0),
        'right_near_y': model.get('right_near_y', 0),
        'left_near_prob': model.get('left_near_prob', 0),
        'right_near_prob': model.get('right_near_prob', 0),
        'frame': model.get('frame', 0),
        'ts': model.get('ts', 0),
      }
  except Exception:
    pass
  # Joystick (throttle, steering being sent to Arduino)
  try:
    if os.path.exists('/tmp/joystick'):
      with open('/tmp/joystick', 'r') as f:
        parts = f.read().strip().split(',')
        data['joystick'] = {'throttle': float(parts[0]), 'steering': float(parts[1])}
  except Exception:
    pass
  # Mode states
  for name in ['engage', 'autopilot', 'exp_auto', 'lane_follow', 'lidar_stop']:
    try:
      with open(f'/tmp/{name}', 'r') as f:
        data[name] = f.read().strip()
    except Exception:
      data[name] = '0'
  return web.json_response(data)


async def video_feed(request: 'web.Request'):
  """mjpeg streaming endpoint that serves the openpilot overlay video feed"""
  boundary = "frame"
  response = web.StreamResponse(
    status=200,
    reason='OK',
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
  # Enable joystick debug mode
  Params().put_bool("JoystickDebugMode", True)

  # App needs to be HTTPS for microphone and audio autoplay to work on the browser
  ssl_context = create_ssl_context()

  import aiohttp_cors
  app = web.Application()
  cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
      allow_credentials=True,
      expose_headers="*",
      allow_headers="*",
      allow_methods="*"
    )
  })
  app.router.add_get("/", index)
  app.router.add_post("/summon", summon)
  app.router.add_get("/nav_status", nav_status)
  app.router.add_post("/summon_cancel", summon_cancel)
  app.router.add_get("/gps", gps)
  app.router.add_get("/waypoints", waypoints)
  app.router.add_post("/waypoints", waypoints)
  app.router.add_get("/ping", ping, allow_head=True)
  app.router.add_post("/offer", offer)
  app.router.add_post("/sound", sound)
  app.router.add_post("/engage", engage)
  app.router.add_get("/ws", ws_handler)
  app.router.add_post("/joystick", joystick)
  for route in list(app.router.routes()):
    cors.add(route)
  app.router.add_post("/autopilot", autopilot)
  app.router.add_post("/exp_auto", exp_auto)
  app.router.add_post("/lane_follow", lane_follow)
  app.router.add_get("/video_feed", video_feed)
  app.router.add_get("/status", status)
  app.router.add_static('/static', os.path.join(TELEOPDIR, 'static'))
  web.run_app(app, access_log=None, host="0.0.0.0", port=5000)


if __name__ == "__main__":
  main()
