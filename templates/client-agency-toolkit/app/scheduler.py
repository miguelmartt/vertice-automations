"""In-process scheduler: runs jobs every N seconds or daily at a given time, and reports failures.

Shared module: every template ships an identical copy, so each one stays self-contained.
"""

import logging
from datetime import datetime, timedelta

log = logging.getLogger("scheduler")


def every(seconds):
    """Every N seconds, aligned to the clock (every 5 min: :00, :05, :10...)."""
    def next_run(now):
        return datetime.fromtimestamp((int(now.timestamp()) // seconds + 1) * seconds, now.tzinfo)
    return next_run


def daily_at(hour, minute=0, weekday=None):
    """Every day at that local time, or only on that weekday (0 = Monday)."""
    def next_run(now):
        day = now.date()
        while True:
            when = datetime(day.year, day.month, day.day, hour, minute, tzinfo=now.tzinfo)
            if when > now and weekday in (None, when.weekday()):
                return when
            day += timedelta(days=1)
    return next_run


class Scheduler:
    """on_failure(name, error) is called when a job starts failing, on_recovery(name) when it works again.

    Each is called once per change, not on every run, so a broken job does not flood the chat.
    """

    def __init__(self, tz, on_failure=None, on_recovery=None):
        self.tz = tz
        self.jobs = []
        self.failing = set()
        self.on_failure = on_failure
        self.on_recovery = on_recovery

    def add(self, name, when, job):
        self.jobs.append((name, when, job))

    def run(self, name, job):
        try:
            job()
        except Exception as e:
            log.exception("Job %r failed", name)
            if name not in self.failing:
                self.failing.add(name)
                self._notify(self.on_failure, name, e)
            return False
        if name in self.failing:
            self.failing.discard(name)
            self._notify(self.on_recovery, name)
        return True

    def loop(self, stop):
        now = datetime.now(self.tz)
        due = {name: when(now) for name, when, _ in self.jobs}
        while not stop.is_set():
            for name, when, job in self.jobs:
                if datetime.now(self.tz) >= due[name]:
                    self.run(name, job)
                    due[name] = when(datetime.now(self.tz))
            stop.wait(10)

    @staticmethod
    def _notify(callback, *args):
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:
            log.exception("Could not report the job status")
