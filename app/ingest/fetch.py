"""Download RFC plain-text files that aren't on disk yet, politely and atomically."""

import os
import time
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from app.ingest.rfc_list import RfcEntry

USER_AGENT = "NetTutor-fetch/0.1"
TIMEOUT_SECONDS = 30


@dataclass
class FetchResult:
    downloaded: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)
    failed: dict[int, str] = field(default_factory=dict)  # RFC number -> error message


def http_get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body: bytes = response.read()
    return body


def _check_body(body: bytes) -> None:
    stripped = body.lstrip()
    if not stripped:
        raise ValueError("empty response")
    if stripped.startswith(b"<"):
        raise ValueError("got an HTML page, not RFC text")


def fetch_rfcs(
    entries: Sequence[RfcEntry],
    dest: Path,
    *,
    get: Callable[[str], bytes] = http_get,
    sleep: Callable[[float], None] = time.sleep,
    delay: float = 1.0,
) -> FetchResult:
    """Download each missing RFC into `dest`, waiting `delay` seconds between downloads.

    Files are written to `<name>.part` and renamed when complete, so an interrupted run
    never leaves a truncated file that a later run would skip.
    """
    dest.mkdir(parents=True, exist_ok=True)
    result = FetchResult()
    first_download = True
    for entry in entries:
        target = dest / entry.filename
        if target.exists():
            result.skipped.append(entry.number)
            continue
        if not first_download:
            sleep(delay)
        first_download = False

        part = target.with_name(target.name + ".part")
        try:
            body = get(entry.txt_url)
            _check_body(body)
            part.write_bytes(body)
            os.replace(part, target)
        except Exception as exc:  # one bad RFC must not stop the others
            part.unlink(missing_ok=True)
            result.failed[entry.number] = str(exc)
        else:
            result.downloaded.append(entry.number)
    return result
