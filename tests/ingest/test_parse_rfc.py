from pathlib import Path

import pytest

from app.ingest.parse import Section, parse_rfc
from app.ingest.rfc_list import load_rfc_list

FIXTURES = Path(__file__).parent / "fixtures"
RAW = Path("data/raw")


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_unnumbered_sections() -> None:
    sections = parse_rfc(fixture("rfc_unnumbered.txt"))
    assert [s.section_id for s in sections] == ["0", "u1", "u2", "u3"]
    assert [s.section_title for s in sections] == ["Preamble", "Introduction", "Fields", "Notes"]
    by_id = {s.section_id: s for s in sections}
    assert by_id["u2"].text == "Port is a 16-bit field.\n\nLength counts octets."
    assert by_id["u3"].text == "Checksums are optional."
    assert "Example Datagram Protocol" in by_id["0"].text


def test_ids_are_stable() -> None:
    raw = fixture("rfc_unnumbered.txt")
    assert parse_rfc(raw) == parse_rfc(raw)


def test_numbered_preferred() -> None:
    sections = parse_rfc(fixture("rfc_old_paged.txt"))
    assert [s.section_id for s in sections] == ["0", "1", "1.1", "2", "A", "A.1"]


def test_no_headings_at_all() -> None:
    assert parse_rfc("Just a note.\n\nMore.\n") == [
        Section("0", "Full text", "Just a note.\n\nMore.")
    ]


@pytest.mark.skipif(not (RAW / "rfc9293.txt").exists(), reason="run make fetch")
def test_real_rfcs_parse() -> None:
    for entry in load_rfc_list():
        path = RAW / entry.filename
        if path.exists():
            assert len(parse_rfc(path.read_text())) >= 3, entry.number

    tcp = parse_rfc((RAW / "rfc9293.txt").read_text())
    top_level = [s.section_id for s in tcp if "." not in s.section_id]
    assert top_level == ["0", "1", "2", "3", "4", "5", "6", "7", "8", "A", "B"]
    titles = {s.section_id: s.section_title for s in tcp}
    assert titles["3.9.1.9"] == (
        "Set Differentiated Services Field (IPv4 TOS or IPv6 Traffic Class)"
    )

    http = {s.section_id: s for s in parse_rfc((RAW / "rfc9110.txt").read_text())}
    assert len(http["B.9"].text) < 2000  # no Acknowledgements/Index/Authors after it

    bgp_sections = parse_rfc((RAW / "rfc4271.txt").read_text())
    bgp = {s.section_id for s in bgp_sections}
    assert {"F.1", "F.6"} <= bgp
    assert "Security Considerations" in {s.section_title for s in bgp_sections}

    private = parse_rfc((RAW / "rfc1918.txt").read_text())
    assert "Authors' Addresses" not in {s.section_title for s in private}
    esp = {s.section_id for s in parse_rfc((RAW / "rfc4303.txt").read_text())}
    assert {"A.1", "A.2.1", "A.3.2"} <= esp

    tls = parse_rfc((RAW / "rfc8446.txt").read_text())
    tls_top = [s.section_id for s in tls if "." not in s.section_id]
    assert tls_top == ["0", *[str(n) for n in range(1, 13)], "A", "B", "C", "D", "E"]
    assert titles["4"] == "Glossary"
    assert titles["3.10.7"] == "SEGMENT ARRIVES"

    udp = parse_rfc((RAW / "rfc768.txt").read_text())
    assert [s.section_title for s in udp][:9] == [
        "Preamble",
        "Introduction",
        "Format",
        "Fields",
        "User Interface",
        "IP Interface",
        "Protocol Application",
        "Protocol Number",
        "References",
    ]


def test_bare_headings_with_indented_body() -> None:
    # RFC 792 style: unindented heading lines between blank lines, body indented.
    sections = parse_rfc(fixture("rfc_bare_headings.txt"))
    assert [(s.section_id, s.section_title) for s in sections] == [
        ("0", "Preamble"),
        ("u1", "Introduction"),
        ("u2", "Echo Message"),
        ("u3", "References"),
    ]
    by_id = {s.section_id: s for s in sections}
    assert by_id["u1"].text == "Control messages report errors.\n\nThey are sent by gateways."
    assert by_id["u3"].text == '[1]  Somebody, "A Paper," 1980.'


def test_layout_quirks() -> None:
    # RFC 3022: "2.0." top-level ids, titles ending in "." or ":".
    # RFC 4271: "6.  BGP Error Handling." RFC 2328/4120: appendices as "A.  Title".
    # RFC 9293: numbered rows in connection diagrams are not headings.
    # RFC 4301: a long title wraps onto an indented second line. RFC 8446: "7.4.  (EC)DHE ...".
    # RFC 9110: a wrapped list item is not a heading.
    # RFC 8446/5321: titles may start with a digit or "#" ("8.  0-RTT", "F.4.  #-literals").
    sections = parse_rfc(fixture("rfc_quirks.txt"))
    assert [(s.section_id, s.section_title) for s in sections] == [
        ("1", "Introduction"),
        ("2", "Translation phases of a session"),
        ("2.1", "Address binding"),
        ("3", "Error Handling"),
        ("3.1", "ICMP Error Messages Received on the Unprotected Side of the Boundary"),
        ("3.2", "(EC)DHE Shared Secret Calculation"),
        ("3.3", "0-RTT"),
        ("3.4", "#-literals"),
        ("A", "Data formats"),
        ("A.1", "Packet header"),
    ]
    by_id = {s.section_id: s for s in sections}
    assert by_id["2.1"].text == "Binding text.\n\n3.  Close the connection."
    assert "4.  ESTABLISHED -->" in by_id["3"].text
    assert by_id["3.1"].text == "Wrapped text."


def test_back_matter_not_in_last_section() -> None:
    # RFC 9110: Acknowledgements/Index/Authors' Addresses after the last appendix are dropped.
    # RFC 4271: unnumbered Security Considerations after the last appendix is kept, as "u1".
    raw = (
        "1.  Intro\n\n   Text.\n\n2.  Last\n\n   Real content.\n\n"
        "Acknowledgements\n\n   Thanks.\n\n"
        "Security Considerations\n\n   Be careful.\n\n"
        "Index\n\n   A  B  C\n\nAuthors' Addresses\n\n   Someone\n"
    )
    sections = parse_rfc(raw)
    assert [(s.section_id, s.section_title, s.text) for s in sections] == [
        ("1", "Intro", "Text."),
        ("2", "Last", "Real content."),
        ("u1", "Security Considerations", "Be careful."),
    ]


def test_numbered_back_matter_sections_dropped() -> None:
    # RFC 1918: "10. Authors' Addresses"; RFC 2131: "5.  Acknowledgments".
    raw = (
        "1.  Intro\n\n   T.\n\n2.  Acknowledgments\n\n   Thanks.\n\n"
        "3.  Protocol\n\n   P.\n\n4.  Author's Address\n\n   Someone\n"
    )
    assert [s.section_id for s in parse_rfc(raw)] == ["1", "3"]


def test_appendix_subsection_styles() -> None:
    # RFC 4271: "Appendix F.1.  Title". RFC 4303: "A1.  Title", "A2.1.  Title" (no dot after A).
    raw = (
        "1.  Intro\n\n   T.\n\nAppendix A.  Extra\n\n   E.\n\n"
        "A1.  Overview\n\n   O.\n\nA1.1.  Detail\n\n   D.\n\n"
        "Appendix B.  More\n\n   M.\n\nAppendix B.1.  Multiple Networks\n\n   N.\n"
    )
    sections = parse_rfc(raw)
    assert [s.section_id for s in sections] == ["1", "A", "A.1", "A.1.1", "B", "B.1"]
    assert sections[2].section_title == "Overview"
