"""Turn an RFC plain-text file into a list of sections.

Two passes:
1. `strip_pagination` removes what the printed-page layout adds: form feeds, the running
   header at the top of each page, and the `[Page N]` footer line.
2. Heading detection splits the remaining lines into sections. Numbered headings are
   accepted only if they are the *next* valid section number (see `next_ids`), which keeps
   table-of-contents lines and numbered lists inside a section from being read as headings.
"""

import re
import textwrap
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


# Leading whitespace is allowed: RFC 791 centers its top-level headings.
_NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+([A-Za-z\"'].*?)\s*$")
_APPENDIX = re.compile(r"^\s*(?i:appendix)\s+([A-Z])[.:]?\s+(\S.*?)\s*$")
_APPENDIX_SUB = re.compile(r"^\s*([A-Z](?:\.\d+)+)\.?\s+([A-Za-z\"'].*?)\s*$")
_DOT_LEADER = re.compile(r"\.{3,}")

SectionId = tuple[str, ...]


def _bump(part: str) -> str:
    """Next value at one level: "3" -> "4", "A" -> "B"."""
    return str(int(part) + 1) if part.isdigit() else chr(ord(part) + 1)


def next_ids(current: SectionId | None) -> set[SectionId]:
    """Section ids that may legally follow `current`.

    After 3.2.1 the next heading can be its first child (3.2.1.1) or the next sibling at
    any level (3.2.2, 3.3, 4). Appendix A may follow any numbered section.
    """
    if current is None:
        return {("1",)}
    allowed = {current + ("1",)}
    for i in range(len(current)):
        allowed.add(current[:i] + (_bump(current[i]),))
    if current[0].isdigit():
        allowed.add(("A",))
    return allowed


def _match_heading(line: str) -> tuple[SectionId, str] | None:
    """Parse a line that looks like a heading into (id, title), ignoring context."""
    # A single-letter id only comes from an explicit "Appendix X" line; otherwise a
    # sentence like "A user interface should allow" would read as Appendix A.
    match = _APPENDIX.match(line) or _APPENDIX_SUB.match(line) or _NUMBERED.match(line)
    if match is None:
        return None
    section_id, title = tuple(match.group(1).split(".")), match.group(2)
    if title.endswith(".") or _DOT_LEADER.search(title):
        return None  # a sentence or list item, or a table-of-contents line
    return section_id, title


def _normalize(lines: list[str]) -> str:
    """Dedent, drop trailing spaces, collapse blank-line runs, trim blank edges."""
    text = textwrap.dedent("\n".join(line.rstrip() for line in lines))
    return re.sub(r"\n{3,}", "\n\n", text).strip("\n")


def _abstract(front_matter: list[str]) -> str | None:
    """The Abstract's text, if the front matter has one; it runs to the next unindented line."""
    for i, line in enumerate(front_matter):
        if line.strip().lower() == "abstract":
            body: list[str] = []
            for next_line in front_matter[i + 1 :]:
                if next_line[:1].strip():
                    break
                body.append(next_line)
            return _normalize(body) or None
    return None


def parse_numbered(lines: list[str]) -> list[Section]:
    """Split lines into sections at numbered headings. Returns [] if there are none."""
    headings: list[tuple[int, SectionId, str]] = []  # (line index, id, title)
    current: SectionId | None = None
    for i, line in enumerate(lines):
        parsed = _match_heading(line)
        if parsed is None:
            continue
        section_id, title = parsed
        if i + 1 < len(lines) and lines[i + 1].strip():
            continue  # headings are followed by a blank line; TOC entries and list items aren't
        if section_id not in next_ids(current):
            continue
        headings.append((i, section_id, title))
        current = section_id
    if not headings:
        return []

    sections: list[Section] = []
    abstract = _abstract(lines[: headings[0][0]])
    if abstract is not None:
        sections.append(Section("0", "Abstract", abstract))
    ends = [index for index, _, _ in headings[1:]] + [len(lines)]
    for (start, section_id, title), end in zip(headings, ends, strict=True):
        sections.append(Section(".".join(section_id), title, _normalize(lines[start + 1 : end])))
    return sections
