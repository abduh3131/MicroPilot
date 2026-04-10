import os
import sys
import capnp

capnp.remove_import_hook()

# Python 3.8 compatibility: use importlib_resources backport or stdlib
if sys.version_info >= (3, 9):
  from importlib.resources import as_file, files
  with as_file(files("cereal")) as fspath:
    CEREAL_PATH = fspath.as_posix()
else:
  try:
    from importlib_resources import as_file, files
    with as_file(files("cereal")) as fspath:
      CEREAL_PATH = fspath.as_posix()
  except ImportError:
    CEREAL_PATH = os.path.dirname(os.path.abspath(__file__))

log = capnp.load(os.path.join(CEREAL_PATH, "log.capnp"))
car = capnp.load(os.path.join(CEREAL_PATH, "car.capnp"))
custom = capnp.load(os.path.join(CEREAL_PATH, "custom.capnp"))
