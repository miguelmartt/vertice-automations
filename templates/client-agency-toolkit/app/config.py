"""Reads the KEY=value config file of a template (for example /etc/vertiguard/vertiguard.env).

Shared module: every template ships an identical copy, so each one stays self-contained.
"""


class ConfigError(Exception):
    pass


class Config(dict):
    """The parsed file. Missing keys and blank values count as "not set"."""

    def need(self, key):
        value = self.get(key, "").strip()
        if not value:
            raise ConfigError(f"{key} is not set in the config file")
        return value

    def get_str(self, key, default=""):
        return self.get(key, "").strip() or default

    def get_int(self, key, default):
        value = self.get(key, "").strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            raise ConfigError(f"{key} must be a whole number, not {value!r}") from None

    def get_list(self, key, default=""):
        """Comma-separated values, trimmed, empty items dropped."""
        return [item.strip() for item in (self.get(key) or default).split(",") if item.strip()]


def load(path):
    """One KEY=value per line. The value is literal (no quotes, no escapes); a line starting with # is a comment."""
    config = Config()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if line.strip() and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                config[key.strip()] = value
    return config
