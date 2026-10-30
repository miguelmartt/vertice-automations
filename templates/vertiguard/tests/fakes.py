"""Test doubles: Telegram, probes and state without network, sudo or disk."""


class FakeTelegram:
    def __init__(self):
        self.sent = []
        self.calls = []

    def send(self, chat_id, text, markdown=False, **extra):
        self.sent.append({"chat_id": chat_id, "text": text, "markdown": markdown, **extra})

    def send_long(self, chat_id, text, **extra):
        self.send(chat_id, text, **extra)

    def call(self, method, params=None, timeout=30):
        self.calls.append((method, params))
        return True

    @property
    def texts(self):
        return [m["text"] for m in self.sent]


class FakeProbes:
    """outputs maps a probe name to its JSON (a dict), a function of its arguments, or an exception."""

    def __init__(self, outputs):
        self.outputs = outputs
        self.ran = []

    def run(self, name, *args, timeout=180):
        self.ran.append((name,) + args)
        out = self.outputs[name]
        if isinstance(out, Exception):
            raise out
        return out(*args) if callable(out) else out


class MemoryState:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
