"""
Simplified swaglog for Jetson — just uses standard Python logging.
Replaces the full swaglog which depends on zmq, numpy, and hardware paths.
"""
import logging
import os
import sys

# Create a simple logger that goes to stdout
cloudlog = logging.getLogger("openpilot")
cloudlog.setLevel(logging.DEBUG)

if not cloudlog.handlers:
  handler = logging.StreamHandler(sys.stdout)
  handler.setLevel(logging.DEBUG)
  formatter = logging.Formatter('[%(levelname)s] %(name)s: %(message)s')
  handler.setFormatter(formatter)
  cloudlog.addHandler(handler)


def add_file_handler(logger):
  """Add file handler — no-op on Jetson."""
  pass


# Stubs for SwagLogger API
class ForwardingHandler(logging.Handler):
  def __init__(self, *args, **kwargs):
    super().__init__()

  def emit(self, record):
    pass


ipchandler = ForwardingHandler()


def get_file_handler():
  return logging.StreamHandler()
