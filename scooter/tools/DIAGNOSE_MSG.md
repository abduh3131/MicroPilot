# diagnose_msg.py -- Cereal Message Diagnostic

Quick diagnostic script that checks whether openpilot cereal messaging services are alive and publishing. 28 lines.

---

## What It Does

Subscribes to each cereal service one at a time, waits up to 2 seconds for a message, and prints YES or NO. If a service returns NO, the corresponding daemon is either not running or not publishing messages.

---

## Services Checked

| Service | Published By |
|---------|-------------|
| `can` | virtual_panda.py or real panda |
| `carOutput` | controlsd |
| `carState` | cardw (car daemon worker) |
| `carControl` | controlsd |
| `pandaStates` | pandad or virtual_panda.py |

---

## Function

### check(service, timeout=2000)

Subscribes to the named cereal service using `messaging.sub_sock()` with the given timeout in milliseconds. Waits 0.5 seconds, then attempts to receive a single message. Prints whether a message arrived and returns a boolean.

---

## Usage

```bash
python diagnose_msg.py
```

Expected output when all daemons are running:

```
Openpilot Messaging Diagnostic
Checking can (timeout 2000ms)...
  Got message: YES
Checking carOutput (timeout 2000ms)...
  Got message: YES
Checking carState (timeout 2000ms)...
  Got message: YES
Checking carControl (timeout 2000ms)...
  Got message: YES
Checking pandaStates (timeout 2000ms)...
  Got message: YES
```

If any service prints NO, that daemon needs to be started or debugged.

---

## How to Modify

- **Add a service:** Add another `check("serviceName")` call in the `__main__` block.
- **Change timeout:** Pass a different timeout value, e.g., `check("can", timeout=5000)`.
