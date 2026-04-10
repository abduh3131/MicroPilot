#!/usr/bin/env python3
import sys

try:
  import msgq.ipc_pyx

  print("msgq.ipc_pyx: OK")
except ImportError as e:
  print(f"msgq.ipc_pyx: FAIL ({e})")
  sys.exit(1)

try:
  import cereal.messaging

  print("cereal.messaging: OK")
except ImportError as e:
  print(f"cereal.messaging: FAIL ({e})")
  sys.exit(1)

print("ALL IMPORTS OK")
