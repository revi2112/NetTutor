import urllib.error
from collections.abc import Callable
from email.message import Message
from pathlib import Path

from app.ingest.fetch import fetch_rfcs
from app.ingest.rfc_list import RfcEntry


def entries(*numbers: int) -> list[RfcEntry]:
    return [RfcEntry(number=n, title=f"RFC {n}") for n in numbers]


def fake_get(responses: dict[int, bytes | Exception], calls: list[str]) -> Callable[[str], bytes]:
    def get(url: str) -> bytes:
        calls.append(url)
        number = int(url.rsplit("rfc", 1)[1].removesuffix(".txt"))
        response = responses[number]
        if isinstance(response, Exception):
            raise response
        return response

    return get


def no_sleep(_: float) -> None:
    pass


def test_downloads_missing_and_skips_present(tmp_path: Path) -> None:
    (tmp_path / "rfc768.txt").write_text("old 768")
    calls: list[str] = []
    result = fetch_rfcs(
        entries(768, 791), tmp_path, get=fake_get({791: b"RFC 791"}, calls), sleep=no_sleep
    )
    assert result.downloaded == [791]
    assert result.skipped == [768]
    assert calls == ["https://www.rfc-editor.org/rfc/rfc791.txt"]
    assert (tmp_path / "rfc768.txt").read_text() == "old 768"
    assert (tmp_path / "rfc791.txt").read_bytes() == b"RFC 791"


def test_sleeps_between_downloads_only(tmp_path: Path) -> None:
    (tmp_path / "rfc1.txt").write_text("present")
    sleeps: list[float] = []
    responses: dict[int, bytes | Exception] = {n: b"text" for n in (2, 3, 4)}
    fetch_rfcs(entries(1, 2, 3, 4), tmp_path, get=fake_get(responses, []), sleep=sleeps.append)
    assert sleeps == [1.0, 1.0]


def test_failure_does_not_stop_others(tmp_path: Path) -> None:
    url = "https://www.rfc-editor.org/rfc/rfc791.txt"
    not_found = urllib.error.HTTPError(url, 404, "Not Found", Message(), None)
    responses: dict[int, bytes | Exception] = {768: b"a", 791: not_found, 9293: b"b"}
    result = fetch_rfcs(
        entries(768, 791, 9293), tmp_path, get=fake_get(responses, []), sleep=no_sleep
    )
    assert list(result.failed) == [791]
    assert "404" in result.failed[791]
    assert result.downloaded == [768, 9293]


def test_html_error_page_rejected(tmp_path: Path) -> None:
    responses: dict[int, bytes | Exception] = {791: b"  <!DOCTYPE html><html>oops</html>"}
    result = fetch_rfcs(entries(791), tmp_path, get=fake_get(responses, []), sleep=no_sleep)
    assert 791 in result.failed
    assert not (tmp_path / "rfc791.txt").exists()


def test_no_partial_file_on_error(tmp_path: Path) -> None:
    result = fetch_rfcs(entries(791), tmp_path, get=fake_get({791: b""}, []), sleep=no_sleep)
    assert 791 in result.failed
    assert list(tmp_path.iterdir()) == []


def test_creates_dest_dir(tmp_path: Path) -> None:
    dest = tmp_path / "raw"
    fetch_rfcs(entries(768), dest, get=fake_get({768: b"a"}, []), sleep=no_sleep)
    assert (dest / "rfc768.txt").exists()
