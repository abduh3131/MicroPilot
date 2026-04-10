#!/usr/bin/env python3
import os
import sys

path = "/data/actuators.csv"
print(f"Testing write to {path}")
try:
  with open(path, "w") as f:
    f.write("test_header\n")
  print(f"Successfully wrote to {path}")
  print(f"Exists: {os.path.exists(path)}")
  print(f"Size: {os.path.getsize(path)}")
except Exception as e:
  print(f"Failed to write: {e}")
