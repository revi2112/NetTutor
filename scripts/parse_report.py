"""Print how each downloaded RFC parses, to check against its table of contents.

Run: uv run python -m scripts.parse_report [rfc_number ...]

`suspect` counts unindented lines after section 1 that look like numbered headings
("3.2.  Title", "A.1.  Title") but were not accepted. Each one is either a parser miss or a
false alarm; with a number argument, the suspect lines are listed.
"""

import re
import sys
from pathlib import Path

from app.ingest.parse import Section, parse_rfc, strip_pagination
from app.ingest.rfc_list import load_rfc_list

RAW_DIR = Path("data/raw")
_HEADING_SHAPE = re.compile(
    r"^(?:Appendix\s+)?(\d+(?:\.\d+)+|\d+(?=\.)|[A-Z]\.?\d+(?:\.\d+)*)\.?\s+\S"
)


def suspect_lines(raw: str, sections: list[Section]) -> list[str]:
    accepted = {s.section_id for s in sections}
    found: list[str] = []
    started = False
    for line in strip_pagination(raw):
        match = _HEADING_SHAPE.match(line)
        if match is None or "...." in line:
            continue
        section_id = match.group(1).removesuffix(".0")
        if section_id[0].isalpha() and section_id[1] != ".":
            section_id = f"{section_id[0]}.{section_id[1:]}"  # RFC 4303: "A2.1" -> "A.2.1"
        started = started or section_id == "1"
        if started and section_id not in accepted:
            found.append(line.rstrip())
    return found


def main(args: list[str]) -> None:
    wanted = {int(a) for a in args}
    for entry in load_rfc_list():
        if wanted and entry.number not in wanted:
            continue
        path = RAW_DIR / entry.filename
        if not path.exists():
            print(f"rfc{entry.number:<5} MISSING")
            continue
        raw = path.read_text()
        sections = parse_rfc(raw)
        suspects = suspect_lines(raw, sections)
        top_level = " ".join(s.section_id for s in sections if "." not in s.section_id)
        flag = "  CHECK" if len(sections) <= 2 or suspects else ""
        print(
            f"rfc{entry.number:<5} sections={len(sections):<4} suspect={len(suspects):<3} "
            f"top-level={top_level}{flag}"
        )
        if wanted:
            for line in suspects:
                print(f"    {line}")


if __name__ == "__main__":
    main(sys.argv[1:])
