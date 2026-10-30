"""Reads the server through the probes, in parallel, keeping the slow ones cached for a while."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

PROBES = {
    "services": "check_services.sh",
    "system": "system.sh",
    "ssl": "ssl_check.sh",
    "fail2ban": "fail2ban_report.sh",
    "ssh": "ssh_logins.sh",
    "backups": "backup_watchdog.sh",
    "docker": "docker_status.sh",
    "updates": "updates_check.sh",
}
CACHE_SECONDS = {"updates": 6 * 3600}  # dnf and apt are slow, and pending updates change rarely
TIMEOUTS = {"updates": 600}


class Snapshot:
    def __init__(self, probes, clock=time.monotonic):
        self.probes = probes
        self.clock = clock
        self.cache = {}
        self.lock = threading.Lock()

    def read(self, names=None, fresh=False):
        """{name: probe JSON} for the given probes (all by default). A failed probe gives {"error": ...}."""
        names = list(names or PROBES)
        result, todo = {}, []
        with self.lock:
            for name in names:
                cached = self.cache.get(name)
                if not fresh and cached and self.clock() - cached[0] < CACHE_SECONDS.get(name, 0):
                    result[name] = cached[1]
                else:
                    todo.append(name)
        if todo:
            with ThreadPoolExecutor(max_workers=len(todo)) as pool:
                for name, data in zip(todo, pool.map(self.run, todo)):
                    result[name] = data
                    if name in CACHE_SECONDS and "error" not in data:
                        with self.lock:
                            self.cache[name] = (self.clock(), data)
        return result

    def run(self, name):
        try:
            return self.probes.run(PROBES[name], timeout=TIMEOUTS.get(name, 180))
        except Exception as e:
            return {"error": str(e)[:200]}
