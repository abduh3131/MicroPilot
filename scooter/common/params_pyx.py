"""
Pure Python Params implementation for Jetson (replaces Cython params_pyx).

Stores parameters as files in a directory structure:
  ~/.comma/params/d/<key>  (PC/Jetson mode)
  /data/params/d/<key>     (TICI mode)

Compatible with the C++ Params class API.
"""
import builtins
import datetime
import enum
import fcntl
import json
import os
import tempfile
import threading


class ParamKeyFlag(enum.IntFlag):
  PERSISTENT = 0x02
  CLEAR_ON_MANAGER_START = 0x04
  CLEAR_ON_ONROAD_TRANSITION = 0x08
  CLEAR_ON_OFFROAD_TRANSITION = 0x10
  DONT_LOG = 0x20
  DEVELOPMENT_ONLY = 0x40
  CLEAR_ON_IGNITION_ON = 0x80
  ALL = 0xFFFFFFFF


class ParamKeyType(enum.IntEnum):
  STRING = 0
  BOOL = 1
  INT = 2
  FLOAT = 3
  TIME = 4
  JSON = 5
  BYTES = 6


# Known keys with their flags and types (subset needed for virtual panda operation)
KNOWN_KEYS = {
  "CarParams": (ParamKeyFlag.CLEAR_ON_MANAGER_START | ParamKeyFlag.CLEAR_ON_ONROAD_TRANSITION, ParamKeyType.BYTES),
  "CarParamsCache": (ParamKeyFlag.CLEAR_ON_MANAGER_START, ParamKeyType.BYTES),
  "CarParamsPersistent": (ParamKeyFlag.PERSISTENT, ParamKeyType.BYTES),
  "ControlsReady": (ParamKeyFlag.CLEAR_ON_MANAGER_START | ParamKeyFlag.CLEAR_ON_ONROAD_TRANSITION, ParamKeyType.BOOL),
  "FirmwareQueryDone": (ParamKeyFlag.CLEAR_ON_MANAGER_START | ParamKeyFlag.CLEAR_ON_ONROAD_TRANSITION, ParamKeyType.BOOL),
  "JoystickDebugMode": (ParamKeyFlag.PERSISTENT, ParamKeyType.BOOL),
  "DisableLogging": (ParamKeyFlag.CLEAR_ON_MANAGER_START, ParamKeyType.BOOL),
  "IsDriverViewEnabled": (ParamKeyFlag.CLEAR_ON_MANAGER_START, ParamKeyType.BOOL),
  "DongleId": (ParamKeyFlag.PERSISTENT, ParamKeyType.STRING),
  "GitBranch": (ParamKeyFlag.PERSISTENT, ParamKeyType.STRING),
  "GitCommit": (ParamKeyFlag.PERSISTENT, ParamKeyType.STRING),
  "GitCommitDate": (ParamKeyFlag.PERSISTENT, ParamKeyType.STRING),
  "GitRemote": (ParamKeyFlag.PERSISTENT, ParamKeyType.STRING),
  "Version": (ParamKeyFlag.PERSISTENT, ParamKeyType.STRING),
  "HardwareSerial": (ParamKeyFlag.PERSISTENT, ParamKeyType.STRING),
  "IsTestedBranch": (ParamKeyFlag.PERSISTENT, ParamKeyType.BOOL),
  "IsReleaseBranch": (ParamKeyFlag.PERSISTENT, ParamKeyType.BOOL),
  "RecordFront": (ParamKeyFlag.PERSISTENT, ParamKeyType.BOOL),
  "RecordFrontLock": (ParamKeyFlag.PERSISTENT, ParamKeyType.BOOL),
  "LongitudinalManeuverMode": (ParamKeyFlag.PERSISTENT, ParamKeyType.BOOL),
  "UbloxAvailable": (ParamKeyFlag.PERSISTENT, ParamKeyType.BOOL),
  "DoReboot": (ParamKeyFlag.CLEAR_ON_MANAGER_START, ParamKeyType.BOOL),
  "DoShutdown": (ParamKeyFlag.CLEAR_ON_MANAGER_START, ParamKeyType.BOOL),
  "DoUninstall": (ParamKeyFlag.CLEAR_ON_MANAGER_START, ParamKeyType.BOOL),
  "CompletedTrainingVersion": (ParamKeyFlag.PERSISTENT, ParamKeyType.STRING),
  "HasAcceptedTerms": (ParamKeyFlag.PERSISTENT, ParamKeyType.STRING),
  "DisengageOnAccelerator": (ParamKeyFlag.PERSISTENT, ParamKeyType.BOOL),
  "ExperimentalMode": (ParamKeyFlag.PERSISTENT, ParamKeyType.BOOL),
}

PYTHON_2_CPP = {
  (str, ParamKeyType.STRING): lambda v: v,
  (builtins.bool, ParamKeyType.BOOL): lambda v: "1" if v else "0",
  (int, ParamKeyType.INT): str,
  (float, ParamKeyType.FLOAT): str,
  (datetime.datetime, ParamKeyType.TIME): lambda v: v.isoformat(),
  (dict, ParamKeyType.JSON): json.dumps,
  (list, ParamKeyType.JSON): json.dumps,
  (bytes, ParamKeyType.BYTES): lambda v: v,
}

CPP_2_PYTHON = {
  ParamKeyType.STRING: lambda v: v.decode("utf-8") if isinstance(v, bytes) else v,
  ParamKeyType.BOOL: lambda v: (v == b"1") if isinstance(v, bytes) else (v == "1"),
  ParamKeyType.INT: int,
  ParamKeyType.FLOAT: float,
  ParamKeyType.TIME: lambda v: datetime.datetime.fromisoformat(v.decode("utf-8") if isinstance(v, bytes) else v),
  ParamKeyType.JSON: json.loads,
  ParamKeyType.BYTES: lambda v: v,
}


def ensure_bytes(v):
  return v.encode() if isinstance(v, str) else v


class UnknownKeyName(Exception):
  pass


class Params:
  def __init__(self, d=""):
    prefix = os.environ.get("OPENPILOT_PREFIX", "d")
    if d:
      self._params_path = d
    else:
      # Determine params root
      if os.path.isfile('/TICI'):
        self._params_path = "/data/params"
      else:
        home = os.path.expanduser("~")
        self._params_path = os.path.join(home, ".comma", "params")

    self._key_path = os.path.join(self._params_path, prefix)
    os.makedirs(self._key_path, exist_ok=True)
    self._lock = threading.Lock()

  def _file_path(self, key):
    return os.path.join(self._key_path, key)

  def check_key(self, key):
    if isinstance(key, bytes):
      key = key.decode()
    # Accept all keys (relaxed for Jetson - no strict key checking)
    return key if isinstance(key, bytes) else key.encode()

  def get(self, key, block=False, return_default=False):
    if isinstance(key, bytes):
      key = key.decode()
    fp = self._file_path(key)
    try:
      with open(fp, 'rb') as f:
        val = f.read()
      if val == b"":
        return None
      # Try to convert based on known type
      ktype = KNOWN_KEYS.get(key, (0, ParamKeyType.BYTES))[1]
      try:
        return CPP_2_PYTHON[ktype](val)
      except Exception:
        return val
    except FileNotFoundError:
      return None

  def get_bool(self, key, block=False):
    if isinstance(key, bytes):
      key = key.decode()
    fp = self._file_path(key)
    try:
      with open(fp, 'rb') as f:
        return f.read().strip() == b"1"
    except FileNotFoundError:
      return False

  def put(self, key, dat):
    if isinstance(key, bytes):
      key = key.decode()
    fp = self._file_path(key)
    if isinstance(dat, str):
      dat = dat.encode()
    elif isinstance(dat, bool):
      dat = b"1" if dat else b"0"
    elif not isinstance(dat, bytes):
      dat = str(dat).encode()
    # Atomic write
    fd, tmp = tempfile.mkstemp(dir=self._params_path)
    try:
      os.write(fd, dat)
      os.fsync(fd)
      os.close(fd)
      os.rename(tmp, fp)
    except Exception:
      os.close(fd)
      try:
        os.unlink(tmp)
      except OSError:
        pass
      raise

  def put_bool(self, key, val):
    self.put(key, b"1" if val else b"0")

  def put_nonblocking(self, key, dat):
    # On Jetson, just do a blocking put (no background thread needed)
    self.put(key, dat)

  def put_bool_nonblocking(self, key, val):
    self.put_bool(key, val)

  def remove(self, key):
    if isinstance(key, bytes):
      key = key.decode()
    fp = self._file_path(key)
    try:
      os.unlink(fp)
    except FileNotFoundError:
      pass

  def clear_all(self, tx_flag=ParamKeyFlag.ALL):
    # Clear params matching the given flag
    for key, (flags, _) in KNOWN_KEYS.items():
      if flags & tx_flag:
        self.remove(key)

  def all_keys(self):
    return [k.encode() for k in KNOWN_KEYS.keys()]

  def get_param_path(self, key=""):
    if key:
      return self._file_path(key if isinstance(key, str) else key.decode())
    return self._key_path

  def get_type(self, key):
    if isinstance(key, bytes):
      key = key.decode()
    return KNOWN_KEYS.get(key, (0, ParamKeyType.BYTES))[1]

  def get_default_value(self, key):
    return None
