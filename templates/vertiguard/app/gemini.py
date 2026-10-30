"""Minimal Google Gemini client (REST generateContent) using only the standard library.

Shared module: every template ships an identical copy, so each one stays self-contained.
"""

import json
import urllib.error
import urllib.request

API = "https://generativelanguage.googleapis.com/v1beta/models/"


class GeminiError(Exception):
    pass


class Gemini:
    def __init__(self, api_key, model="gemini-flash-latest"):
        self.api_key = api_key
        self.model = model

    def generate(self, contents, system=None, tools=None, timeout=120):
        """Raw call. contents is the list of turns ({"role": ..., "parts": [...]}). Returns the API response."""
        body = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = tools
        req = urllib.request.Request(
            API + self.model + ":generateContent",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            e.close()
            raise GeminiError(f"HTTP {e.code}: {detail}") from None
        except OSError as e:
            raise GeminiError(str(getattr(e, "reason", e))) from None

    def ask(self, prompt, system=None):
        """One question, one plain-text answer."""
        return answer_text(self.generate([{"role": "user", "parts": [{"text": prompt}]}], system=system))


def model_turn(response):
    """The model's turn from a response. Raises GeminiError if it was blocked or came back empty."""
    try:
        return response["candidates"][0]["content"]
    except (KeyError, IndexError):
        reason = (response.get("promptFeedback") or {}).get("blockReason") or "empty response"
        raise GeminiError(f"Gemini gave no answer ({reason})") from None


def answer_text(response):
    parts = model_turn(response).get("parts", [])
    return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
