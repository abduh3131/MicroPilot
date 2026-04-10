#!/usr/bin/env python3
"""prints openpilot cereal messages for debugging"""
import cereal.messaging as messaging
import time


def check(service, timeout=2000):
  print(f"Checking {service} (timeout {timeout}ms)...")
  try:
    sock = messaging.sub_sock(service, timeout=timeout)
    time.sleep(0.5)
    msg = sock.receive()
    print(f"  Got message: {'YES' if msg is not None else 'NO'}")
    return msg is not None
  except Exception as e:
    print(f"  Error checking {service}: {e}")
    return False


if __name__ == "__main__":
  print("Openpilot Messaging Diagnostic")
  check("can")
  check("carOutput")
  check("carState")
  check("carControl")
  check("pandaStates")
