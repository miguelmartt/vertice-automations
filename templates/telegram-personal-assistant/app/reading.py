"""Read-it-later: fetches a page, keeps its readable text, asks Gemini for a summary and saves it.

Tab layout, first row as header: Date | Title | URL | Summary (columns A to D).
"""

import logging
import re
from html.parser import HTMLParser

import web

log = logging.getLogger("reading")

MAX_PAGE_BYTES = 2_000_000
MAX_TEXT = 6000
PAGE_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([\w.:-]+)""", re.IGNORECASE)

PROMPT = (
    "Summarize this article for my read-it-later list. Give: a 2-3 sentence summary, then 3 bullet key "
    "points, then 3 short topic tags (comma-separated, lowercase). Keep it tight. Plain text only, no "
    "Markdown. Write it in {language}.\n\n"
    "Title: {title}\nURL: {url}\n\nContent:\n{text}"
)


class _PageText(HTMLParser):
    """Collects the <title> and the visible text, skipping scripts, styles and the like."""

    SKIP = {"script", "style", "noscript", "template", "svg", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self.chunks = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
            self._in_title = tag == "title" and self._skip == 1 and self.title is None

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or "") + data
        elif not self._skip:
            self.chunks.append(data)


def page_text(markup):
    """(title, text) of an HTML page: whitespace collapsed, text cut at MAX_TEXT characters."""
    parser = _PageText()
    parser.feed(markup)
    parser.close()
    title = " ".join((parser.title or "").split())
    return title, " ".join(" ".join(parser.chunks).split())[:MAX_TEXT]


def decode(body, charset):
    """Bytes to text with the charset of the HTTP header, else the page's <meta charset>, else UTF-8."""
    if not charset:
        match = META_CHARSET.search(body[:4096])
        charset = match.group(1).decode("ascii") if match else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def read_page(url, fetch=web.fetch):
    """(title, text) of the page; empty text if it is not an HTML or text page."""
    body, content_type, charset = fetch(url, MAX_PAGE_BYTES)
    if content_type not in PAGE_TYPES:
        return "", ""
    return page_text(decode(body, charset))


class ReadItLater:
    def __init__(self, sheets, sheet, ai, t, now, fetch=web.fetch):
        self.sheets = sheets
        self.sheet = sheet
        self.ai = ai
        self.t = t
        self.now = now
        self.fetch = fetch

    def save(self, url):
        """Summarizes the page, saves a row and returns the reply. A page that cannot be read is saved
        anyway, without a summary, so the link is not lost."""
        try:
            title, text = read_page(url, self.fetch)
        except web.FetchError as e:
            log.warning("Could not fetch %s: %s", url, e)
            title, text = "", ""
        title = title or url
        if text:
            summary = self.ai.ask(PROMPT.format(language=self.t("language_name"), title=title, url=url,
                                                text=text))
            reply = summary
        else:
            summary, reply = "", self.t("reading_unreadable")
        self.sheets.append(self.sheet, [self.now().isoformat(timespec="seconds"), title, url, summary])
        return self.t("reading_saved", title=title, summary=reply)
