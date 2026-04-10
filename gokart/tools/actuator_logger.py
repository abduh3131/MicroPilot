#!/usr/bin/env python3
"""logs every joystick command to a csv file"""
import csv
import os
import argparse
import signal
import sys


def signal_handler(sig, frame):
  print("\nStopped.")
  sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


# subscribes to carOutput and writes a csv row per actuator update
def main():
  parser = argparse.ArgumentParser(description="Log actuator values from Openpilot to a CSV file.")
  parser.add_argument("--output", type=str, default="actuators.csv", help="Path to the output CSV file.")
  parser.add_argument("--rate", type=float, default=100.0, help="Log rate in Hz (default: 100)")
  parser.add_argument("--serial", type=str, default=None, help="Serial port to output data to (e.g., COM3, /dev/ttyUSB0)")
  parser.add_argument("--baud", type=int, default=115200, help="Baud rate for serial output (default: 115200)")
  parser.add_argument("--serial-log", type=str, default="serialLogs.csv", help="Path to serial commands log file.")
  args = parser.parse_args()

  csv_path = args.output
  serial_log_path = args.serial_log
  print(f"Starting script... Logging to {csv_path}")
  print(f"Serial log: {serial_log_path}")

  ser = None
  if args.serial:
    try:
      import serial

      print(f"Opening serial port {args.serial} at {args.baud} baud...")
      ser = serial.Serial(args.serial, args.baud, timeout=0.1)
      print("Serial port opened.")
    except ImportError:
      print("Error: Could not import 'serial'. Please install pyserial (pip install pyserial).")
      return
    except Exception as e:
      print(f"Error opening serial port: {e}")
      return

  print("Importing messaging...")
  try:
    import cereal.messaging as messaging
  except ImportError:
    print("Error: Could not import cereal.messaging. Ensure the openpilot environment is active.")
    return

  print("Messaging imported.")

  print("Initializing SubMaster...")
  sm = messaging.SubMaster(['carOutput'])
  print("SubMaster initialized. Waiting for messages...")

  MAX_TORQUE = 500.0

  columns = ['timestamp_ns', 'torque_l', 'torque_r', 'steeringAngleDeg', 'throttle', 'steering']

  serial_columns = ['timestamp_ns', 'throttle', 'steering']

  try:
    with open(csv_path, 'a', newline='') as f, \
         open(serial_log_path, 'a', newline='') as sf:
      writer = csv.writer(f)
      serial_writer = csv.writer(sf)

      if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        writer.writerow(columns)
        f.flush()
      if not os.path.exists(serial_log_path) or os.path.getsize(serial_log_path) == 0:
        serial_writer.writerow(serial_columns)
        sf.flush()

      frame_count = 0

      while True:
        sm.update(int(1000 / args.rate))

        if sm.updated['carOutput']:
          ao = sm['carOutput'].actuatorsOutput
          timestamp = sm.logMonoTime['carOutput']

          torque_l = float(getattr(ao, 'accel', 0.0))
          torque_r = float(getattr(ao, 'torque', 0.0))
          steering_angle = float(getattr(ao, 'steeringAngleDeg', 0.0))

          throttle = max(-1.0, min(1.0, (torque_l + torque_r) / (2.0 * MAX_TORQUE)))
          steering = max(-1.0, min(1.0, (torque_l - torque_r) / (2.0 * MAX_TORQUE)))

          writer.writerow([
            timestamp,
            round(torque_l, 1),
            round(torque_r, 1),
            round(steering_angle, 4),
            round(throttle, 4),
            round(steering, 4),
          ])

          serial_writer.writerow([
            timestamp,
            round(throttle, 4),
            round(steering, 4),
          ])

          if ser:
            serial_line = f"{throttle:.4f},{steering:.4f}\n"
            try:
              ser.write(serial_line.encode('utf-8'))
            except Exception as e:
              print(f"Serial write error: {e}")

          frame_count += 1

          if frame_count % 100 == 0:
            f.flush()
            sf.flush()
            print(f"Logged {frame_count} frames | throttle={throttle:+.3f} steering={steering:+.3f}", end='\r')

  except Exception as e:
    print(f"\nError: {e}")


if __name__ == "__main__":
  main()
