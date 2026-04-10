#!/usr/bin/env python3
"""old ros bridge that listens to cmd_vel from the safety node and writes tmp lidar_stop"""

import rospy
from geometry_msgs.msg import Twist
import os
import signal
import sys

STOP_FLAG = "/tmp/lidar_stop"


def write_flag(value):
    tmp = STOP_FLAG + ".tmp"
    with open(tmp, "w") as f:
        f.write(str(value))
    os.rename(tmp, STOP_FLAG)


def cmd_vel_callback(msg):
    if msg.linear.x <= 0.0:
        write_flag(1)
    else:
        write_flag(0)


def signal_handler(sig, frame):
    write_flag(0)
    print("\n[lidar_bridge] Stopped. Flag cleared.")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)

    write_flag(0)

    rospy.init_node("lidar_bridge", anonymous=True)
    rospy.Subscriber("/cmd_vel", Twist, cmd_vel_callback)

    print("[lidar_bridge] Listening on /cmd_vel, writing to " + STOP_FLAG)
    rospy.spin()


if __name__ == "__main__":
    main()
