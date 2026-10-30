"""RSS (0.9x, 1.0, 2.0) and Atom parsing with xml.etree, and the headline list sent to Gemini."""

import email.utils
import html
import re
import xml.etree.ElementTree as ET
from collections import namedtuple
from datetime import datetime, timedelta, timezone

Item = namedtuple("Item", "title link date summary")

RECENT = timedelta(hours=24)
MAX_ITEMS = 40
TAG = re.compile(r"<[^>]+>")

DATE_TAGS = ("pubDate", "published", "date", "issued", "updated", "modified")  # by preference
SUMMARY_TAGS = ("description", "summary", "content", "encoded")  # encoded = <content:encoded>


class FeedError(Exception):
    pass


def _name(element):
    """The tag without its namespace: {http://www.w3.org/2005/Atom}entry -> entry."""
    return element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""


def _text(element):
    return " ".join("".join(element.itertext()).split())


def parse_date(value):
    """RFC 822 (RSS) or ISO 8601 (Atom) date, always with a time zone (UTC if it had none). None if unreadable."""
    value = value.strip()
    if not value:
        return None
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            when = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _item(element):
    found = {}
    link = ""
    for child in element:
        name = _name(child)
        if name == "link":
            href = child.get("href")
            if href is None:  # RSS: <link>https://...</link>
                link = link or _text(child)
            elif child.get("rel", "alternate") == "alternate":  # Atom: <link rel="alternate" href="..."/>
                link = link or href
        elif name not in found:
            found[name] = child

    title = _text(found["title"]) if "title" in found else ""
    if not link:
        link = next((_text(found[n]) for n in ("guid", "id") if n in found), "")
    date = next((parse_date(_text(found[n])) for n in DATE_TAGS if n in found), None)
    summary = next((_text(found[n]) for n in SUMMARY_TAGS if n in found and _text(found[n])), "")
    return Item(title, link, date, summary)


def parse(data):
    """Every item (RSS) or entry (Atom) in a feed, in order."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise FeedError(f"not a valid feed: {e}") from None
    return [_item(el) for el in root.iter() if _name(el) in ("item", "entry")]


def plain(text):
    """HTML snippet -> one line of plain text."""
    return " ".join(html.unescape(TAG.sub(" ", text)).split())


def compile_items(items, now):
    """The numbered headline list for the prompt: the last 24 hours (or everything, if nothing is that
    recent), at most 40 items. Empty string if there are no items at all."""
    recent = [item for item in items if item.date and now - item.date <= RECENT]
    lines = []
    for i, item in enumerate((recent or items)[:MAX_ITEMS], 1):
        title = " ".join(html.unescape(item.title).split()) or "(no title)"
        lines.append(f"{i}. {title}\n   {plain(item.summary)[:160]}\n   {item.link}")
    return "\n\n".join(lines)
