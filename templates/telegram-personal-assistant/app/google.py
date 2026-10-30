"""Google APIs (Gmail, Calendar, Sheets) over plain HTTPS, using only the standard library.

Authentication is the OAuth2 refresh-token flow: google_auth.py gets a refresh token once, and
Google() trades it for a short-lived access token whenever the cached one is about to expire.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://oauth2.googleapis.com/token"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets/"

# The scopes google_auth.py asks for, read-only where the assistant only reads.
SCOPES = {
    "gmail": "https://www.googleapis.com/auth/gmail.readonly",
    "calendar": "https://www.googleapis.com/auth/calendar.readonly",
    "sheets": "https://www.googleapis.com/auth/spreadsheets",
}


class GoogleError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def request_json(req, timeout=30):
    """Sends a request and returns its JSON answer. Errors say the HTTP status and Google's reason."""
    parts = urllib.parse.urlsplit(req.full_url)
    where = parts.netloc + parts.path  # never the query string or the headers
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise GoogleError(f"{where}: HTTP {e.code} {_reason(e)}".rstrip(), e.code) from None
    except OSError as e:
        raise GoogleError(f"{where}: {getattr(e, 'reason', e)}") from None
    return json.loads(body) if body.strip() else {}


def _reason(error):
    try:
        raw = error.read().decode(errors="replace")
    finally:
        error.close()
    try:
        data = json.loads(raw)
    except ValueError:
        return raw[:300]
    detail = data.get("error") if isinstance(data, dict) else None
    if isinstance(detail, dict):  # the APIs: {"error": {"code": 403, "message": "..."}}
        return str(detail.get("message", ""))[:300]
    if detail:  # the token endpoint: {"error": "invalid_grant", "error_description": "..."}
        return f"{detail}: {data.get('error_description', '')}".rstrip(": ")[:300]
    return raw[:300]


def token_request(fields):
    """POST to Google's token endpoint (refreshing a token, or exchanging an authorization code)."""
    req = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return request_json(req)


class Google:
    def __init__(self, client_id, client_secret, refresh_token, clock=time.monotonic):
        self._fields = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        self._clock = clock
        self._token = None
        self._expires = 0
        self._lock = threading.Lock()  # the scheduler and the bot run in different threads

    def access_token(self):
        """The cached access token, or a new one if it expires within a minute."""
        with self._lock:
            if self._token is None or self._clock() >= self._expires:
                data = token_request(self._fields)
                if "access_token" not in data:
                    raise GoogleError("The token endpoint gave no access token")
                self._token = data["access_token"]
                self._expires = self._clock() + int(data.get("expires_in", 3600)) - 60
            return self._token

    def get(self, url, params=None):
        return self.request("GET", url, params)

    def post(self, url, body, params=None):
        return self.request("POST", url, params, body)

    def request(self, method, url, params=None, body=None):
        """JSON call with the access token. params may hold lists (repeated query parameters)."""
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        data = json.dumps(body).encode() if body is not None else None
        for attempt in (1, 2):
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Authorization": "Bearer " + self.access_token(),
                "Content-Type": "application/json",
            })
            try:
                return request_json(req)
            except GoogleError as e:
                if e.status != 401 or attempt == 2:
                    raise
                with self._lock:  # revoked or expired early: get a new token and try once more
                    self._token = None


class Sheets:
    """The two Sheets calls the assistant needs, on one spreadsheet."""

    def __init__(self, google, spreadsheet_id):
        self.google = google
        self.spreadsheet_id = spreadsheet_id

    def _url(self, sheet, suffix=""):
        name = "'" + sheet.replace("'", "''") + "'"  # the whole tab, even with spaces in its name
        return (SHEETS_API + urllib.parse.quote(self.spreadsheet_id, safe="") + "/values/"
                + urllib.parse.quote(name, safe="") + suffix)

    def append(self, sheet, row):
        """Adds a row under the last one. RAW: values are stored as they are, never run as formulas."""
        self.google.post(self._url(sheet, ":append"), {"values": [row]},
                         {"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"})

    def rows(self, sheet):
        """Every row of the tab (header included), numbers as numbers."""
        data = self.google.get(self._url(sheet), {
            "valueRenderOption": "UNFORMATTED_VALUE",
            "dateTimeRenderOption": "FORMATTED_STRING",
        })
        return data.get("values", [])
