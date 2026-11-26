"""Turn an RFC plain-text file into a list of sections.

Two passes:
1. `strip_pagination` removes what the printed-page layout adds: form feeds, the running
   header at the top of each page, and the `[Page N]` footer line.
2. Heading detection splits the remaining lines into sections (added in later steps).
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    section_id: str  # "4.1.2", "A.1", or synthetic "0" / "u1" for RFCs without numbers
    section_title: str
    text: str


# A footer line ends with "[Page 12]" (old RFCs: "[page 1]", front matter: "[Page iii]").
_FOOTER = re.compile(r"\[page\s+[0-9ivxlc]+\]\s*$", re.IGNORECASE)
# A running header mentions the RFC number or the publication year.
_HEADER_HINT = re.compile(r"RFC\s*\d+|\b(19|20)\d\d\b")


def _drop_running_header(page: list[str]) -> list[str]:
    """Drop the header block (first non-blank lines up to a blank line) if it looks like one.

    Some old RFCs (e.g. 826) have no running header, and a page may start with a heading,
    so a block is only treated as a header if its first line has an RFC number or a year.
    """
    i = 0
    while i < len(page) and not page[i].strip():
        i += 1
    if i == len(page) or not _HEADER_HINT.search(page[i]):
        return page
    while i < len(page) and page[i].strip():
        i += 1
    return page[i:]


def strip_pagination(raw: str) -> list[str]:
    """Return the document's lines with form feeds, running headers and footers removed."""
    pages = raw.replace("\r\n", "\n").split("\f")
    lines: list[str] = []
    for number, page in enumerate(pages):
        page_lines = page.split("\n")
        if number > 0:
            page_lines = _drop_running_header(page_lines)
        lines.extend(line for line in page_lines if not _FOOTER.search(line))
    return lines
