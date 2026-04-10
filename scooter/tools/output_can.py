#!/usr/bin/env python3
"""sends actuator commands to the arduino over can bus"""

import csv
import struct
import argparse
import signal
import sys


def signal_handler(sig, frame):
  print("\nStopped.")
  sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


# CAN message ID for scooter commands
SCOOTER_CMD_ID = 0x200
CAN_BUS = 0  # main bus


def main():
  parser = argparse.ArgumentParser(description="Send actuator values over CAN to Arduino.")
  parser.add_argument("--output", type=str, default="can_actuators.csv", help="CSV log file")
  parser.add_argument("--rate", type=float, default=100.0, help="Loop rate in Hz")
  parser.add_argument("--can-id", type=lambda x: int(x, 0), default=SCOOTER_CMD_ID,
                       help="CAN message ID (default: 0x200)")
  args = parser.parse_args()

  print(f"[output_can] Starting. CAN ID: 0x{args.can_id:03X}, log: {args.output}")

  import cereal.messaging as messaging
  from openpilot.selfdrive.pandad.pandad_api_impl import can_list_to_can_capnp

  sm = messaging.SubMaster(['carOutput', 'selfdriveState'])
  pm = messaging.PubMaster(['sendcan'])

  MAX_TORQUE = 500.0
  columns = ['timestamp_ns', 'throttle', 'steering', 'engaged', 'raw_accel', 'raw_torque']

  frame_count = 0

  with open(args.output, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(columns)
    f.flush()

    while True:
      sm.update(int(1000 / args.rate))

      if sm.updated['carOutput']:
        ao = sm['carOutput'].actuatorsOutput
        timestamp = sm.logMonoTime['carOutput']

        raw_accel = float(ao.accel)
        raw_torque = float(ao.torque)

        # Convert differential → scooter
        throttle = max(-1.0, min(1.0, (raw_accel + raw_torque) / (2.0 * MAX_TORQUE)))
        steering = max(-1.0, min(1.0, (raw_accel - raw_torque) / (2.0 * MAX_TORQUE)))

        engaged = sm['selfdriveState'].enabled if sm.valid['selfdriveState'] else False

        # Pack CAN frame: 2x int16 + flags = 5 bytes, padded to 8
        throttle_int = int(max(-10000, min(10000, throttle * 10000)))
        steering_int = int(max(-10000, min(10000, steering * 10000)))
        flags = 0x01 if engaged else 0x00

        can_data = struct.pack('>hhBxxx', throttle_int, steering_int, flags)

        # Publish on sendcan
        can_msg = (args.can_id, can_data, CAN_BUS)
        pm.send('sendcan', can_list_to_can_capnp([can_msg], msgtype='sendcan'))

        # Log to CSV
        writer.writerow([timestamp, round(throttle, 4), round(steering, 4),
                         int(engaged), round(raw_accel, 1), round(raw_torque, 1)])

        frame_count += 1
        if frame_count % 100 == 0:
          f.flush()
          status = "ENGAGED" if engaged else "disengaged"
          print(f"[output_can] {frame_count} frames | {status} | T={throttle:+.3f} S={steering:+.3f}", end='\r')


if __name__ == "__main__":
  main()
