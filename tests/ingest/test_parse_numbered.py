from pathlib import Path

from app.ingest.parse import Section, next_ids, parse_numbered, strip_pagination

FIXTURES = Path(__file__).parent / "fixtures"


def parse_fixture(name: str) -> list[Section]:
    return parse_numbered(strip_pagination((FIXTURES / name).read_text()))


def test_old_paged_sections() -> None:
    sections = parse_fixture("rfc_old_paged.txt")
    assert [(s.section_id, s.section_title, s.text) for s in sections] == [
        ("0", "Abstract", "This memo defines the Example Transfer Protocol."),
        ("1", "Introduction", "The protocol moves examples between hosts."),
        ("1.1", "Terminology", "An example is a unit of data."),
        (
            "2",
            "Operation",
            "Hosts follow these steps:\n\n1.  Open a connection.\n\n"
            "2.  Send the example.\n\n3.  Close the connection.\n\n"
            "The steps repeat until done.\n\nThe receiver acknowledges each example.",
        ),
        ("A", "Examples", "A sample exchange."),
        ("A.1", "Simple Exchange", "One host sends one example."),
    ]


def test_old_paged_excludes_front_matter() -> None:
    for section in parse_fixture("rfc_old_paged.txt"):
        assert "Distribution of this memo" not in section.text
        assert "...." not in section.text
        assert "Table of Contents" not in section.text


def test_new_unpaged_ids_and_titles() -> None:
    sections = {s.section_id: s for s in parse_fixture("rfc_new_unpaged.txt")}
    assert list(sections) == ["0", "1", "2", "2.1", "2.1.1", "2.2", "3"]
    assert sections["2.1.1"].section_title == "Hello"
    assert sections["3"].section_title == "Security Considerations"
    assert sections["2"].text == ""


def test_next_ids() -> None:
    assert next_ids(None) == {("1",)}
    assert next_ids(("2", "1", "1")) == {
        ("2", "1", "1", "1"),
        ("2", "1", "2"),
        ("2", "2"),
        ("3",),
        ("A",),
    }
    assert next_ids(("A", "1")) == {("A", "1", "1"), ("A", "2"), ("B",)}


def test_no_numbered_headings_returns_empty() -> None:
    assert parse_numbered(["Introduction", "------", "", "Text."]) == []
