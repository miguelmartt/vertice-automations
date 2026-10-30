"""The three morning digests: email (Gmail + Gemini), today's agenda (Calendar) and news (RSS + Gemini).

Each function returns the text to send to Telegram; the scheduler sends it.
"""

import html
import logging
import urllib.parse
from collections import namedtuple
from datetime import date, datetime, timedelta

import rss
import web

log = logging.getLogger("digests")

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/"
MAX_FEED_BYTES = 5_000_000
MIN_GAP = timedelta(minutes=30)

EMAIL_PROMPT = (
    "You are my email assistant. Below are the emails I received in the last 24 hours. Write a short "
    "morning digest. Group by priority: first \"Needs a reply / action\", then \"FYI\", then \"Probably "
    "noise\". For each item give one line: sender - what it's about. End with a one-sentence summary of "
    "how busy my inbox is. Plain text only, no Markdown. Write it in {language}.\n\n"
    "Emails:\n{emails}"
)

NEWS_PROMPT = (
    "You are my news editor. From the headlines below (last 24h from my RSS feeds), pick the 5-8 most "
    "relevant and write a short morning digest. For each: a one-line takeaway followed by the link. Skip "
    "duplicates and clickbait. Start with a one-sentence overview of the day's themes. Plain text only, "
    "no Markdown. Write it in {language}.\n\n"
    "Headlines:\n{headlines}"
)


# Email ------------------------------------------------------------------------------------------------

def fetch_emails(google, query, limit):
    """Sender, subject and preview of the messages that match the Gmail search, newest first."""
    listing = google.get(GMAIL, {"q": query, "maxResults": limit})
    emails = []
    for ref in listing.get("messages", [])[:limit]:
        message = google.get(f"{GMAIL}/{ref['id']}",
                             {"format": "metadata", "metadataHeaders": ["From", "Subject"]})
        headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
        emails.append({
            "from": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "snippet": html.unescape(message.get("snippet", "")),
        })
    return emails


def compile_emails(emails):
    """The numbered list the model reads."""
    lines = []
    for i, mail in enumerate(emails, 1):
        preview = " ".join(mail["snippet"].split())[:240]
        lines.append(f"{i}. From: {mail['from'] or '(unknown sender)'}\n"
                     f"   Subject: {mail['subject'] or '(no subject)'}\n"
                     f"   Preview: {preview}")
    return "\n\n".join(lines)


def email_digest(google, ai, t, query, limit):
    emails = fetch_emails(google, query, limit)
    if not emails:
        return t("email_none")
    summary = ai.ask(EMAIL_PROMPT.format(language=t("language_name"), emails=compile_emails(emails)))
    return t("email_title") + "\n\n" + summary


# Calendar ---------------------------------------------------------------------------------------------

Event = namedtuple("Event", "summary start end all_day location")


def fetch_events(google, calendar_id, start, end):
    """Every event between start and end, recurring ones expanded, ordered by start time."""
    url = CALENDAR + urllib.parse.quote(calendar_id, safe="") + "/events"
    params = {"timeMin": start.isoformat(), "timeMax": end.isoformat(), "singleEvents": "true",
              "orderBy": "startTime", "maxResults": 250}
    items = []
    while True:
        data = google.get(url, params)
        items += data.get("items", [])
        if not data.get("nextPageToken"):
            return items
        params["pageToken"] = data["nextPageToken"]


def _datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _events(items, tz):
    events = []
    for item in items:
        start, end = item.get("start") or {}, item.get("end") or {}
        if start.get("dateTime"):
            begins = _datetime(start["dateTime"]).astimezone(tz)
            ends = _datetime(end["dateTime"]).astimezone(tz) if end.get("dateTime") else begins
            all_day = False
        elif start.get("date"):
            day = date.fromisoformat(start["date"])
            begins = ends = datetime(day.year, day.month, day.day, tzinfo=tz)
            all_day = True
        else:
            continue
        events.append(Event(item.get("summary") or "", begins, ends, all_day, item.get("location") or ""))
    return sorted(events, key=lambda e: e.start)


def free_gaps(events, day_start, day_end):
    """Free slots of 30 minutes or more between day_start and day_end, around the timed events."""
    gaps = []
    cursor = day_start
    for event in events:
        if event.all_day:
            continue
        if event.start > cursor:
            stop = min(event.start, day_end)
            if stop - cursor >= MIN_GAP:
                gaps.append((cursor, stop))
        cursor = max(cursor, event.end)
    if day_end - cursor >= MIN_GAP:
        gaps.append((cursor, day_end))
    return gaps


def agenda(items, now, t, work_start=(9, 0), work_end=(19, 0)):
    """Today's events and the free slots in the working hours, from the Calendar API items."""
    events = _events(items, now.tzinfo)
    text = t("agenda_title", date=now.strftime(t("date_format"))) + "\n\n"
    if not events:
        return text + t("agenda_empty")

    hhmm = "%H:%M"
    lines = [t("agenda_count", count=len(events)), ""]
    for e in events:
        summary = e.summary or t("no_title")
        if e.all_day:
            line = f"• {t('agenda_all_day')} {summary}"
        else:
            line = f"• {e.start.strftime(hhmm)}–{e.end.strftime(hhmm)} {summary}"
        lines.append(line + (f"  📍{e.location}" if e.location else ""))
    text += "\n".join(lines)

    day_start = now.replace(hour=work_start[0], minute=work_start[1], second=0, microsecond=0)
    day_end = now.replace(hour=work_end[0], minute=work_end[1], second=0, microsecond=0)
    gaps = free_gaps(events, day_start, day_end)
    if gaps:
        slots = ", ".join(f"{a.strftime(hhmm)}–{b.strftime(hhmm)}" for a, b in gaps)
        text += "\n\n" + t("agenda_gaps", start=day_start.strftime(hhmm), end=day_end.strftime(hhmm),
                           gaps=slots)
    return text


def calendar_digest(google, t, calendar_id, now, work_start, work_end):
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    items = fetch_events(google, calendar_id, midnight, midnight + timedelta(days=1))
    return agenda(items, now, t, work_start, work_end)


# News -------------------------------------------------------------------------------------------------

def news_digest(feeds, ai, t, now, fetch=web.fetch):
    """A feed that cannot be read is skipped; if none can be read, the job fails (and says so)."""
    items, failed = [], 0
    for url in feeds:
        try:
            items += rss.parse(fetch(url, MAX_FEED_BYTES)[0])
        except (web.FetchError, rss.FeedError) as e:
            failed += 1
            log.warning("Skipping the feed %s: %s", url, e)
    if failed == len(feeds):
        raise RuntimeError(f"none of the {len(feeds)} feed(s) could be read")
    headlines = rss.compile_items(items, now)
    if not headlines:
        return t("news_none")
    summary = ai.ask(NEWS_PROMPT.format(language=t("language_name"), headlines=headlines))
    return t("news_title") + "\n\n" + summary
