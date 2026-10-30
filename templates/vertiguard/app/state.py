"""Small JSON state file (what was last reported, cursors...) that survives restarts.

Shared module: every template ships an identical copy, so each one stays self-contained.
"""

import json
import os
import threading


class State:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    def get(self, key, default=None):
        with self._lock:
            return self.data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self.data[key] = value
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
