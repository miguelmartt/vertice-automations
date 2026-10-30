"""One-time helper that gets the Google refresh token the assistant needs.

Run it on a computer with a web browser (your laptop, not the server):

    python3 google_auth.py client_secret.json       # the file of your "Desktop app" OAuth client
    python3 google_auth.py                          # or type the client ID and secret

It opens Google's consent page, catches the answer on http://127.0.0.1:<random port> and prints the
GOOGLE_* lines to paste in /etc/personal-assistant/personal-assistant.env. Use --scopes to ask only
for what you use, for example --scopes calendar,sheets.
"""

import argparse
import base64
import getpass
import hashlib
import http.server
import json
import secrets
import sys
import time
import urllib.parse
import webbrowser

import google

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
WAIT_SECONDS = 300


def pkce_pair():
    """(verifier, challenge) for PKCE, so a stolen authorization code is useless on its own."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def consent_url(client_id, redirect_uri, scopes, state, challenge):
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",  # we want a refresh token...
        "prompt": "consent",       # ...every time, even if you authorized this client before
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })


def read_client(path):
    """Client ID and secret from the JSON file Google Cloud gives for a Desktop app client."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "installed" not in data:
        raise SystemExit("That file is not a Desktop app client. Create one of type \"Desktop app\".")
    return data["installed"]["client_id"], data["installed"]["client_secret"]


class _Redirect(http.server.BaseHTTPRequestHandler):
    """Receives Google's redirect (?code=...&state=... or ?error=...) and stores it on the server."""

    def do_GET(self):
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
        if "code" not in query and "error" not in query:  # the browser asking for /favicon.ico...
            self.send_response(404)
            self.end_headers()
            return
        self.server.answer = query
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Done. You can close this tab and go back to the terminal.")

    def log_message(self, *args):
        pass


def wait_for_answer(server, seconds=WAIT_SECONDS):
    server.answer = None
    server.timeout = 5
    deadline = time.monotonic() + seconds
    while server.answer is None and time.monotonic() < deadline:
        server.handle_request()
    return server.answer


def main(argv=None):
    parser = argparse.ArgumentParser(description="Get the Google refresh token for the personal assistant.")
    parser.add_argument("client_file", nargs="?", help="client_secret_*.json of your Desktop app OAuth client")
    parser.add_argument("--scopes", default=",".join(google.SCOPES),
                        help="comma-separated, from: " + ", ".join(google.SCOPES) + " (default: all)")
    args = parser.parse_args(argv)

    names = [name.strip() for name in args.scopes.split(",") if name.strip()]
    unknown = [name for name in names if name not in google.SCOPES]
    if unknown or not names:
        parser.error("unknown scope(s): " + ", ".join(unknown) if unknown else "no scopes given")
    if args.client_file:
        client_id, client_secret = read_client(args.client_file)
    else:
        client_id = input("OAuth client ID: ").strip()
        client_secret = getpass.getpass("OAuth client secret: ").strip()

    server = http.server.HTTPServer(("127.0.0.1", 0), _Redirect)
    redirect_uri = f"http://127.0.0.1:{server.server_port}"
    state = secrets.token_urlsafe(16)
    verifier, challenge = pkce_pair()
    url = consent_url(client_id, redirect_uri, [google.SCOPES[name] for name in names], state, challenge)

    print("Opening Google's consent page. If no browser opens, visit this URL on this computer:\n")
    print(url + "\n")
    webbrowser.open(url)
    try:
        answer = wait_for_answer(server)
    finally:
        server.server_close()

    if answer is None:
        raise SystemExit("No answer from Google after 5 minutes. Run it again.")
    if answer.get("state") != state:
        raise SystemExit("The answer did not come from this run (state mismatch). Run it again.")
    if "error" in answer:
        raise SystemExit(f"Google said: {answer['error']}")

    tokens = google.token_request({
        "code": answer["code"],
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    })
    if "refresh_token" not in tokens:
        raise SystemExit("Google gave no refresh token. Remove the app's access at "
                         "https://myaccount.google.com/permissions and run this again.")

    print("Paste these lines in /etc/personal-assistant/personal-assistant.env:\n")
    print(f"GOOGLE_CLIENT_ID={client_id}")
    print(f"GOOGLE_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN={tokens['refresh_token']}")


if __name__ == "__main__":
    try:
        main()
    except google.GoogleError as e:
        sys.exit(f"Google refused the code: {e}")
    except KeyboardInterrupt:
        sys.exit(1)
