"""Runs the root probes in /opt/vertiguard through sudo. Each one prints a single line of JSON.

The sudoers rule installed by install.sh lets the vertiguard user run /opt/vertiguard/*.sh as root,
and nothing else.
"""

import json
import subprocess

DIRECTORY = "/opt/vertiguard"


class ProbeError(Exception):
    pass


class Probes:
    def __init__(self, directory=DIRECTORY):
        self.directory = directory

    def run(self, name, *args, timeout=180):
        try:
            r = subprocess.run(
                ["sudo", "-n", f"{self.directory}/{name}", *args],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise ProbeError(f"{name} took more than {timeout} s") from None
        out = r.stdout.strip()
        if not out:
            raise ProbeError(f"{name} printed nothing (exit {r.returncode}): {r.stderr.strip()[:200]}")
        try:
            data = json.loads(out)
        except ValueError:
            raise ProbeError(f"{name} did not print JSON: {out[:200]}") from None
        if r.returncode != 0:
            raise ProbeError(f"{name}: {data.get('error') or r.stderr.strip()[:200]}")
        return data
