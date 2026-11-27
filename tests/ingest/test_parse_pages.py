from app.ingest.parse import strip_pagination


def test_removes_form_feeds_headers_footers() -> None:
    raw = (
        "Body one.\n\nAuthor   Informational   [Page 1]\n"
        "\fRFC 9999   Example   March 1999\n\nBody two.\n"
    )
    text = "\n".join(strip_pagination(raw))
    assert "Body one." in text
    assert "Body two." in text
    assert "[Page 1]" not in text
    assert "RFC 9999" not in text
    assert "\f" not in text


def test_multi_line_header_block() -> None:
    raw = (
        "Body.\n"
        "\f\n   28 Aug 1980\nUser Datagram Protocol   RFC 768\nFields\n\nLength counts octets.\n"
    )
    lines = strip_pagination(raw)
    assert "Fields" not in lines
    assert "Length counts octets." in lines


def test_page_without_running_header_keeps_heading() -> None:
    lines = strip_pagination("Intro text.\n\fNotes:\n------\n\nSome note.\n")
    assert "Notes:" in lines
    assert "------" in lines


def test_double_form_feed() -> None:
    lines = strip_pagination("A.\n\f\f\n   September 1981\n\nB.\n")
    assert "A." in lines
    assert "B." in lines
    assert not any("September 1981" in line for line in lines)


def test_lowercase_and_roman_page_numbers() -> None:
    lines = strip_pagination("Text.\nPostel        [page 3]\nMore.\nAuthor    [Page iii]\n")
    assert lines[:2] == ["Text.", "More."]
    assert not any("page" in line.lower() for line in lines)


def test_crlf_normalized() -> None:
    lines = strip_pagination("a\r\nb\r\n")
    assert lines[:2] == ["a", "b"]
    assert not any("\r" in line for line in lines)
