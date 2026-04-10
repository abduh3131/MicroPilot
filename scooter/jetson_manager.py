#!/usr/bin/env python3
"""
Jetson Manager — Simplified openpilot launcher for Jetson.

Starts only the processes needed for virtual panda operation:
  1. virtual_panda  — Fake panda/car interface
  2. joystickd      — Converts joystick input to actuator commands
  3. bodyteleop     — Web UI with WASD + ENGAGE button (port 5000)

Optional (started separately via deploy script):
  - output_serial  — Serial output to Arduino
  - output_can     — CAN output to Arduino

No sentry, no registration, no hardware detection, no UI.
"""

import os
import sys
import signal
import time
import importlib
from multiprocessing import Process

# Ensure openpilot root is on PYTHONPATH
BASEDIR = os.path.dirname(os.path.abspath(__file__))
os.environ['PYTHONPATH'] = BASEDIR
if BASEDIR not in sys.path:
  sys.path.insert(0, BASEDIR)

# Set virtual panda mode
os.environ['VIRTUAL_PANDA'] = '1'


def launch_process(module_name, proc_name):
  """Import and run a Python module's main() function."""
  try:
    print(f"[jetson_manager] Starting {proc_name} ({module_name})...")
    mod = importlib.import_module(module_name)
    mod.main()
  except KeyboardInterrupt:
    pass
  except Exception as e:
    print(f"[jetson_manager] {proc_name} crashed: {e}")
    import traceback
    traceback.print_exc()


def main():
  print("=" * 60)
  print("  Jetson OpenpilotV3 — Virtual Panda Mode")
  print("=" * 60)
  print()

  # Initialize params
  from openpilot.common.params import Params
  params = Params()

  # Set JoystickDebugMode so joystickd starts
  params.put_bool("JoystickDebugMode", True)

  # Safety: ensure disengaged on startup
  try:
    with open('/tmp/engage', 'w') as f:
      f.write('0')
  except Exception:
    pass

  # Create /dev/shm if needed (for msgq)
  try:
    os.makedirs('/dev/shm', exist_ok=True)
  except PermissionError:
    pass

  processes = {}

  # 1. Virtual Panda (replaces pandad + card)
  p = Process(target=launch_process, args=("openpilot.tools.virtual_panda", "virtual_panda"), daemon=True)
  p.start()
  processes['virtual_panda'] = p

  time.sleep(2)  # Let virtual panda publish CarParams first

  # 2. Joystickd (converts testJoystick messages to carControl)
  p = Process(target=launch_process, args=("openpilot.tools.joystick.joystickd", "joystickd"), daemon=True)
  p.start()
  processes['joystickd'] = p

  # 3. Bodyteleop web UI (WASD + ENGAGE button on port 5000)
  p = Process(target=launch_process, args=("openpilot.tools.bodyteleop.web", "bodyteleop"), daemon=True)
  p.start()
  processes['bodyteleop'] = p

  print()
  print("=" * 60)
  print("  All processes started!")
  print("=" * 60)
  print()
  print("  Web Control (WASD + Camera + ENGAGE):")
  print("    https://<jetson-ip>:5000")
  print()
  print("  Press Ctrl+C to stop all processes")
  print()

  # Monitor loop
  def signal_handler(sig, frame):
    print("\n[jetson_manager] Shutting down...")
    # Disengage for safety
    try:
      with open('/tmp/engage', 'w') as f:
        f.write('0')
    except Exception:
      pass
    for name, proc in processes.items():
      if proc.is_alive():
        print(f"  Stopping {name}...")
        proc.terminate()
    sys.exit(0)

  signal.signal(signal.SIGINT, signal_handler)
  signal.signal(signal.SIGTERM, signal_handler)

  while True:
    alive = []
    dead = []
    for name, proc in processes.items():
      if proc.is_alive():
        alive.append(f"\033[32m{name}\033[0m")
      else:
        dead.append(f"\033[31m{name}\033[0m")

    status = ' '.join(alive + dead)
    print(f"[jetson_manager] {status}")

    # Restart dead processes
    for name, proc in list(processes.items()):
      if not proc.is_alive() and proc.exitcode != 0:
        print(f"[jetson_manager] Restarting {name}...")
        if name == 'virtual_panda':
          new_p = Process(target=launch_process, args=("openpilot.tools.virtual_panda", "virtual_panda"), daemon=True)
        elif name == 'joystickd':
          new_p = Process(target=launch_process, args=("openpilot.tools.joystick.joystickd", "joystickd"), daemon=True)
        elif name == 'bodyteleop':
          new_p = Process(target=launch_process, args=("openpilot.tools.bodyteleop.web", "bodyteleop"), daemon=True)
        else:
          continue
        new_p.start()
        processes[name] = new_p

    time.sleep(5)


if __name__ == "__main__":
  main()
