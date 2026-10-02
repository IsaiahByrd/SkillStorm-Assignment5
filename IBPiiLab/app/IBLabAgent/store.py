import json
import os
import time
from pathlib import Path

from controls import for_storage

LOG_PATH = Path(os.environ.get("LAB_LOG_PATH", "interactions.jsonl"))


def write_record(event: str, data: dict, path: Path | None = None) -> dict:
    """The only way anything gets persisted. Redaction is not optional here."""
    entry = {"ts": time.time(), "event": event, "data": for_storage(data)}
    with open(path or LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
