"""Plain HTTP GET with a size cap, for RSS feeds and read-it-later pages."""

import http.client
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "Mozilla/5.0 (compatible; personal-assistant)"


class FetchError(Exception):
    pass


def fetch(url, max_bytes, timeout=20):
    """Returns (body, content type, charset or None). Reads at most max_bytes, so a huge page cannot fill
    the memory. Raises FetchError for anything that is not an http(s) URL or that cannot be downloaded."""
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise FetchError(f"not an http(s) URL: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(max_bytes), r.headers.get_content_type(), r.headers.get_content_charset()
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code}") from None
    except (OSError, ValueError, http.client.HTTPException) as e:
        raise FetchError(str(getattr(e, "reason", e)) or type(e).__name__) from None
