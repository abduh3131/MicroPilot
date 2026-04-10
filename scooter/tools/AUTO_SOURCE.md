# auto_source.py -- Log Identifier Printer

Reads an openpilot log file and prints all log identifiers found inside it. 19 lines.

---

## What It Does

Uses openpilot's `LogReader` to open a recorded log file in AUTO mode (sorted by time), then prints each log identifier on its own line. Useful for debugging which data sources and message types are present in a recorded drive log.

---

## Usage

```bash
python auto_source.py <log_path>
```

The `log_path` argument is required. Exits with an error if not provided.

---

## Dependencies

Requires `openpilot.tools.lib.logreader.LogReader` and `ReadMode` to be importable. This means the openpilot environment must be set up (typically run from within the openpilot source tree or with PYTHONPATH configured).

---

## How to Modify

- **Print more detail:** After reading `lr`, iterate over messages with `for msg in lr:` and print individual fields.
- **Filter by type:** Add a command-line argument for a service name and filter the output.
