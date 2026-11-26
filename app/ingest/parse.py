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


# Leading whitespace is allowed: RFC 791 centers its top-level headings. A top-level number
# needs its dot ("1.  Introduction") so a date line like "1 January 1980" isn't a heading.
_NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+)+|\d+(?=\.))\.?\s+(\S.*?)\s*$")
_APPENDIX = re.compile(r"^\s*(?i:appendix)\s+([A-Z])[.:]?\s+(\S.*?)\s*$")
# RFC 2328/4120 write appendices as "A.  Title" with no "Appendix"; only at column 0.
_APPENDIX_BARE = re.compile(r"^([A-Z])\.\s+(\S.*?)\s*$")
_APPENDIX_SUB = re.compile(r"^\s*([A-Z](?:\.\d+)+)\.?\s+(\S.*?)\s*$")
_DOT_LEADER = re.compile(r"\.{3,}")
# Arrows and box edges appear in protocol diagrams, not section titles. (Bare "<", ">" and "="
# do occur in real titles: RFC 5321 4.2.5 "<CRLF>.<CRLF>", RFC 1034 6.2.8 "QNAME=...".)
_DIAGRAM_CHARS = re.compile(r"-->|<--|\|")
# Figure and table rows line up in columns; titles never have wide gaps between words.
_COLUMN_GAP = re.compile(r"\S {3,}\S")

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


def _plausible_title(title: str) -> bool:
    """False for text that has a heading's shape but is a TOC line or a figure/table row."""
    return not (
        _DOT_LEADER.search(title)  # TOC: "Introduction ........ 3"
        or _DIAGRAM_CHARS.search(title)  # RFC 9293: "4.  ESTABLISHED --> <SEQ=101>"
        or _COLUMN_GAP.search(title)  # RFC 9293: "1.  ESTABLISHED        ESTABLISHED"
    )


def _match_heading(line: str) -> tuple[SectionId, str] | None:
    """Parse a line that looks like a heading into (id, title), ignoring context."""
    # A single-letter id needs "Appendix X" or a column-0 "X.  Title"; otherwise a
    # sentence like "A user interface should allow" would read as Appendix A.
    match = (
        _APPENDIX.match(line)
        or _APPENDIX_BARE.match(line)
        or _APPENDIX_SUB.match(line)
        or _NUMBERED.match(line)
    )
    if match is None:
        return None
    section_id, title = tuple(match.group(1).split(".")), match.group(2)
    if not _plausible_title(title):
        return None
    if len(section_id) > 1 and section_id[-1] == "0":
        section_id = section_id[:-1]  # RFC 3022 writes top-level sections as "3.0."
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


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _is_blank(lines: list[str], i: int) -> bool:
    return i >= len(lines) or not lines[i].strip()


def _title_continuation(lines: list[str], i: int) -> str | None:
    """The second line of a wrapped heading at `i`, if there is one.

    RFC 4301: "6.1.1.  ICMP Error Messages Received on the Unprotected Side of the" is
    followed by an indented "Boundary" and then a blank line.
    """
    nxt = lines[i + 1] if i + 1 < len(lines) else ""
    if (
        nxt.strip()
        and _indent(nxt) > _indent(lines[i])
        and _is_blank(lines, i + 2)
        and _match_heading(nxt) is None  # a TOC entry followed by its child entry
        and _plausible_title(nxt.strip())  # a two-line figure row
    ):
        return nxt.strip()
    return None


def parse_numbered(lines: list[str]) -> list[Section]:
    """Split lines into sections at numbered headings. Returns [] if there are none."""
    headings: list[tuple[int, int, SectionId, str]] = []  # (line, body start, id, title)
    current: SectionId | None = None
    for i, line in enumerate(lines):
        parsed = _match_heading(line)
        if parsed is None:
            continue
        section_id, title = parsed
        body_start = i + 1
        if not _is_blank(lines, i + 1):
            # Headings are followed by a blank line; TOC entries and list items aren't.
            continuation = _title_continuation(lines, i)
            if continuation is None:
                continue
            title, body_start = f"{title} {continuation}", i + 2
        if title.endswith(".") and line[0].isspace():
            continue  # an indented numbered list item ("   3.  Close the connection.")
        if section_id not in next_ids(current):
            continue
        title = title.rstrip(".:").strip()  # RFC 3022: "3.0. Translation phases of a session."
        headings.append((i, body_start, section_id, title))
        current = section_id
    if not headings:
        return []

    sections: list[Section] = []
    abstract = _abstract(lines[: headings[0][0]])
    if abstract is not None:
        sections.append(Section("0", "Abstract", abstract))
    ends = [index for index, _, _, _ in headings[1:]] + [len(lines)]
    for (_, body_start, section_id, title), end in zip(headings, ends, strict=True):
        sections.append(Section(".".join(section_id), title, _normalize(lines[body_start:end])))
    return sections


_UNDERLINE = re.compile(r"^[-=]{3,}\s*$")
_MAX_BARE_HEADING = 60


def _underlined_headings(lines: list[str]) -> list[int]:
    """RFC 768/826 style: an unindented line followed by a line of only `-` or `=`."""
    return [
        i
        for i in range(len(lines) - 1)
        if lines[i].strip() and not lines[i][0].isspace() and _UNDERLINE.match(lines[i + 1])
    ]


def _bare_headings(lines: list[str]) -> list[int]:
    """RFC 792 style: a short unindented line alone between blank lines (body is indented)."""

    def blank(j: int) -> bool:
        return j < 0 or j >= len(lines) or not lines[j].strip()

    return [
        i
        for i, line in enumerate(lines)
        if line.strip()
        and not line[0].isspace()
        and blank(i - 1)
        and blank(i + 1)
        and len(line.strip()) <= _MAX_BARE_HEADING
        and not line.rstrip().endswith(".")
    ]


def parse_unnumbered(lines: list[str]) -> list[Section]:
    """Split lines at unnumbered headings. Returns [] if there are none.

    Underlined headings are tried first, then bare headings. Text before the first heading
    becomes section "0" (Preamble); headings get ids u1, u2, ... in order.
    """
    headings = _underlined_headings(lines)
    skip = 2  # the heading line and its underline
    if not headings:
        headings, skip = _bare_headings(lines), 1
    if not headings:
        return []

    sections: list[Section] = []
    preamble = _normalize(lines[: headings[0]])
    if preamble:
        sections.append(Section("0", "Preamble", preamble))
    ends = headings[1:] + [len(lines)]
    for number, (start, end) in enumerate(zip(headings, ends, strict=True), start=1):
        title = lines[start].strip().removesuffix(":").strip()
        sections.append(Section(f"u{number}", title, _normalize(lines[start + skip : end])))
    return sections


def parse_rfc(raw: str) -> list[Section]:
    """Parse a whole RFC text file into sections. This is the entry point for ingestion."""
    lines = strip_pagination(raw)
    sections = parse_numbered(lines) or parse_unnumbered(lines)
    return sections or [Section("0", "Full text", _normalize(lines))]
