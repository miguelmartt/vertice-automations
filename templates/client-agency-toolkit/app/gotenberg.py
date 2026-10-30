"""Turns an HTML page into a PDF with a self-hosted Gotenberg (https://gotenberg.dev)."""

import urllib.error
import urllib.request
import uuid

TIMEOUT = 60
# printBackground keeps the coloured table header; preferCssPageSize uses the template's @page size (A4).
OPTIONS = {"printBackground": "true", "preferCssPageSize": "true"}


class GotenbergError(Exception):
    pass


def multipart(fields, files, boundary):
    """A multipart/form-data body and its Content-Type.

    fields: {name: value}; files: (field name, file name, content type, bytes) tuples.
    """
    parts = []
    for name, value in fields.items():
        head = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
        parts.append(head.encode() + str(value).encode() + b"\r\n")
    for name, filename, content_type, data in files:
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        )
        parts.append(head.encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def html_to_pdf(base_url, page, boundary=None):
    """Sends the page as index.html to the Chromium HTML route and returns the PDF bytes."""
    body, content_type = multipart(
        OPTIONS,
        [("files", "index.html", "text/html; charset=utf-8", page.encode("utf-8"))],
        boundary or uuid.uuid4().hex,
    )
    req = urllib.request.Request(
        base_url.rstrip("/") + "/forms/chromium/convert/html",
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            pdf = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        e.close()
        raise GotenbergError(f"Gotenberg answered HTTP {e.code}: {detail}") from None
    except OSError as e:
        raise GotenbergError(f"Could not reach Gotenberg at {base_url}: {getattr(e, 'reason', e)}") from None
    if not pdf.startswith(b"%PDF"):
        raise GotenbergError("Gotenberg did not return a PDF")
    return pdf
