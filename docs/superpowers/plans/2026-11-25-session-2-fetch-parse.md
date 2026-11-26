# Session 2: Fetch and Parse RFCs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Download ~30 plain-text RFCs into `data/raw/` and turn each into a list of `(section_id, section_title, text)` sections, with stable synthetic ids for RFCs that have no numbered sections.

**Architecture:** `data/rfc_list.yaml` is the single list of RFCs (number + title), loaded and validated by `app/ingest/rfc_list.py`. `app/ingest/fetch.py` downloads missing files with stdlib `urllib`, one second apart, writing atomically; `scripts/fetch_rfcs.py` is a thin CLI around it. `app/ingest/parse.py` works in two passes: first remove pagination (form feeds, running headers, `[Page N]` footers), then find headings. Numbered headings are accepted only if they are the *next* valid section number, which keeps TOC lines and numbered lists from being taken as sections. If there are no numbered headings, the parser falls back to underlined headings (`Title` / `-----`) with ids `u1`, `u2`, ….

**Tech Stack:** Python 3.12 stdlib (`urllib`, `re`, `textwrap`, `dataclasses`), pydantic v2, PyYAML, pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-nettutor-v2-design.md` (session 2 = source Task 3 in `nettutor-claude-code-tasks.md`, unchanged; synthetic-id rule from "Eval metric definitions")

## Global Constraints

- New runtime dependency: `pyyaml` only; dev: `types-PyYAML`. Fetch with stdlib `urllib.request` (no `requests`/`httpx` at runtime).
- Source URL: `https://www.rfc-editor.org/rfc/rfc{n}.txt`; saved as `data/raw/rfc{n}.txt`. `data/raw/` stays git-ignored; `data/rfc_list.yaml` is committed.
- Polite: skip files already present, sleep 1.0 s between actual downloads, timeout 30 s, generic `User-Agent: NetTutor-fetch/0.1` (no personal details).
- Section ids: numbered RFCs use the RFC's own ids (`"4.1.2"`, appendices `"A"`, `"A.1"`). Text before section 1 is kept only if it has an `Abstract`, as section `"0"` titled `"Abstract"`. RFCs with no numbered sections: `"0"` (title `"Preamble"`) for text before the first heading, then `"u1"`, `"u2"`, … per heading in order. These ids must be stable: the same input file always gives the same ids.
- Status-of-memo, copyright, and table-of-contents text never appear in any section.
- Section text: dedented, trailing whitespace stripped, runs of blank lines collapsed to one, leading/trailing blank lines removed. Sections with empty text are kept (their id/title matter for subsection matching); the chunker (session 3) skips them.
- `mypy --strict` on `app/`; `make check` passes at the end of every task.
- Commits are authored solely by the owner: **no `Co-Authored-By` trailer**.

## Review Focus

1. **A numbered list item inside a section** (`   3.  Close the connection.`) → stays body text, not a new section 3. Test in Task 4 (`rfc_old_paged.txt`).
2. **A page that starts with a heading and has no running header** (RFC 826 style: form feed right before `Notes:` / `------`) → the heading is kept. Test in Task 3.
3. **A download that fails halfway, or a crash mid-write** → no `rfcNNNN.txt` is left behind, so a re-run fetches it again. Test in Task 2.
4. **One RFC returns an HTTP error or an HTML error page** → the other RFCs are still fetched, the failure is named in the summary, and the script exits 1. Test in Task 2.
5. **A running page header repeats the current heading** (RFC 768 puts `Fields` in the header after a page break) → no extra section, and the text continues in the current one. Test in Task 5.

---

### Task 1: RFC list and loader

**Files:**
- Create: `data/rfc_list.yaml`, `app/ingest/rfc_list.py`, `tests/ingest/__init__.py`, `tests/ingest/test_rfc_list.py`
- Modify: `pyproject.toml` (add `pyyaml`; dev `types-PyYAML`)

**Interfaces:**
- Produces:
  - `class RfcEntry(BaseModel)` (frozen): `number: int` (`gt=0`), `title: str` (`min_length=1`); properties `filename -> str` (`"rfc9293.txt"`), `txt_url -> str` (`"https://www.rfc-editor.org/rfc/rfc9293.txt"`), `html_url -> str` (`"https://www.rfc-editor.org/rfc/rfc9293"`).
  - `def load_rfc_list(path: Path = DEFAULT_RFC_LIST) -> list[RfcEntry]`, with `DEFAULT_RFC_LIST = Path("data/rfc_list.yaml")`. Raises `ValueError("duplicate RFC number: 768")` on duplicates; lets pydantic's `ValidationError` through for bad entries.

- [ ] **Step 1: Write failing tests** in `tests/ingest/test_rfc_list.py` (use `tmp_path` for bad files):
  - `test_committed_list_loads`: `load_rfc_list()` returns ≥30 entries, numbers include `9293`, `768`, `826`, `8446`; all numbers are unique.
  - `test_entry_urls`: `RfcEntry(number=768, title="UDP")` has `filename == "rfc768.txt"`, `txt_url == "https://www.rfc-editor.org/rfc/rfc768.txt"`, `html_url == "https://www.rfc-editor.org/rfc/rfc768"`.
  - `test_duplicate_number_rejected`: a YAML with 768 twice → `pytest.raises(ValueError, match="duplicate RFC number: 768")`.
  - `test_missing_title_rejected`: an entry without `title` → `pytest.raises(ValidationError)`.
- [ ] **Step 2:** Run `uv run pytest tests/ingest/test_rfc_list.py -v`. Expected: FAIL (module not found).
- [ ] **Step 3:** `uv add pyyaml && uv add --dev types-PyYAML`. Write `data/rfc_list.yaml` as a top-level `rfcs:` list of `{number, title}`, using the official titles, in this order: 9293 Transmission Control Protocol (TCP); 768 User Datagram Protocol; 791 Internet Protocol; 8200 Internet Protocol, Version 6 (IPv6) Specification; 792 Internet Control Message Protocol; 1034 Domain Names - Concepts and Facilities; 1035 Domain Names - Implementation and Specification; 4033 DNS Security Introduction and Requirements; 9110 HTTP Semantics; 9112 HTTP/1.1; 9113 HTTP/2; 9114 HTTP/3; 9000 QUIC: A UDP-Based Multiplexed and Secure Transport; 8446 The Transport Layer Security (TLS) Protocol Version 1.3; 5246 The Transport Layer Security (TLS) Protocol Version 1.2; 2131 Dynamic Host Configuration Protocol; 826 An Ethernet Address Resolution Protocol; 3022 Traditional IP Network Address Translator (Traditional NAT); 4271 A Border Gateway Protocol 4 (BGP-4); 2328 OSPF Version 2; 4301 Security Architecture for the Internet Protocol; 4303 IP Encapsulating Security Payload (ESP); 7296 Internet Key Exchange Protocol Version 2 (IKEv2); 4251 The Secure Shell (SSH) Protocol Architecture; 5321 Simple Mail Transfer Protocol; 6749 The OAuth 2.0 Authorization Framework; 5280 Internet X.509 Public Key Infrastructure Certificate and Certificate Revocation List (CRL) Profile; 4120 The Kerberos Network Authentication Service (V5); 3411 An Architecture for Describing Simple Network Management Protocol (SNMP) Management Frameworks; 1918 Address Allocation for Private Internets; 4632 Classless Inter-domain Routing (CIDR): The Internet Address Assignment and Aggregation Plan.
- [ ] **Step 4:** Implement `app/ingest/rfc_list.py` (`yaml.safe_load`, validate each item into `RfcEntry`, then check for duplicates).
- [ ] **Step 5:** Run `make check`. Expected: all pass.
- [ ] **Step 6:** Commit `feat: add RFC list and loader`.

### Task 2: Fetcher

**Files:**
- Create: `app/ingest/fetch.py`, `scripts/fetch_rfcs.py`, `tests/ingest/test_fetch.py`
- Modify: `Makefile` (add `fetch` target and to `.PHONY`)

**Interfaces:**
- Consumes: `RfcEntry`, `load_rfc_list` (Task 1).
- Produces:
  - `@dataclass class FetchResult`: `downloaded: list[int]`, `skipped: list[int]`, `failed: dict[int, str]` (RFC number → error message).
  - `def http_get(url: str) -> bytes`: urllib with the `User-Agent` and 30 s timeout from Global Constraints. Raises on HTTP errors.
  - `def fetch_rfcs(entries: Sequence[RfcEntry], dest: Path, *, get: Callable[[str], bytes] = http_get, sleep: Callable[[float], None] = time.sleep, delay: float = 1.0) -> FetchResult`.
  - `make fetch` → `uv run python -m scripts.fetch_rfcs`.

- [ ] **Step 1: Write failing tests** in `tests/ingest/test_fetch.py`. Inject a fake `get` (a dict of url → bytes, or raising) and a recording `sleep`; no network.
  - `test_downloads_missing_and_skips_present`: `rfc768.txt` already exists in `dest`; entries 768 and 791 → `downloaded == [791]`, `skipped == [768]`, `get` called only for the 791 URL, the existing 768 file is unchanged, and `dest / "rfc791.txt"` holds the fake bytes.
  - `test_sleeps_between_downloads_only`: three missing entries → `sleep` called with `1.0` exactly twice (not before the first download, and never for skipped files).
  - `test_failure_does_not_stop_others`: `get` raises `urllib.error.HTTPError` (404) for 791 → `failed` has key 791 with a message containing `"404"`; 768 and 9293 are still downloaded.
  - `test_html_error_page_rejected`: `get` returns `b"<!DOCTYPE html>..."` for 791 → 791 is in `failed`; `rfc791.txt` does not exist.
  - `test_no_partial_file_on_error`: `get` returns an empty body for 791 → 791 is in `failed`; no `rfc791.txt` and no stray temp files are left in `dest` (`list(dest.iterdir()) == []`).
  - `test_creates_dest_dir`: `dest` doesn't exist yet → it is created.
- [ ] **Step 2:** Run `uv run pytest tests/ingest/test_fetch.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `app/ingest/fetch.py`. Reject a body that is empty or whose first non-whitespace byte is `<`. Write to `dest/rfc{n}.txt.part`, then `os.replace` it to the final name. On any exception, remove the `.part` file and record `str(exc)` in `failed`. Catch `Exception` per RFC so that one failure doesn't stop the run.
- [ ] **Step 4:** Implement `scripts/fetch_rfcs.py`: `main() -> int` loads the list, calls `fetch_rfcs(entries, Path("data/raw"))`, prints `downloaded N, skipped N, failed N` and one line per failure (`rfc791: <message>`), and returns 1 if anything failed. Guard it with `if __name__ == "__main__": sys.exit(main())`. Add the `fetch` target to the Makefile.
- [ ] **Step 5:** Run `make check`. Expected: all pass.
- [ ] **Step 6:** Run `make fetch` (real network, ~30 s). Expected: `downloaded 31, skipped 0, failed 0`; a second `make fetch` prints `downloaded 0, skipped 31, failed 0`.
- [ ] **Step 7:** Commit `feat: fetch RFC text files`.

### Task 3: Strip pagination

**Files:**
- Create: `app/ingest/parse.py`, `tests/ingest/test_parse_pages.py`

**Interfaces:**
- Produces: `def strip_pagination(raw: str) -> list[str]`, which returns the document's lines with no form feeds, running headers, or footers. `\r\n` is normalized to `\n`.

Rules:
- Split on `\f`. For every page after the first, skip leading blank lines. Then, **if** the first non-blank line contains `RFC\s*\d+` or a year `\b(19|20)\d\d\b`, drop that line and the following non-blank lines up to the next blank line (this is the running-header block). Otherwise keep the page as is.
- Anywhere in the document, drop lines matching `\[page\s+[0-9ivxlc]+\]\s*$` (case-insensitive), the footer line.

- [ ] **Step 1: Write failing tests** in `tests/ingest/test_parse_pages.py` (inline strings):
  - `test_removes_form_feeds_headers_footers`: input `"Body one.\n\nAuthor   Informational   [Page 1]\n\fRFC 9999   Example   March 1999\n\nBody two.\n"` → `"\n".join(result)` contains `"Body one."` and `"Body two."` and does not contain `"[Page 1]"`, `"RFC 9999"`, or `"\f"`.
  - `test_multi_line_header_block`: page 2 starts `"\f\n   28 Aug 1980\nUser Datagram Protocol   RFC 768\nFields\n\nLength counts octets.\n"` → `"Fields"` is not among the lines and `"Length counts octets."` is.
  - `test_page_without_running_header_keeps_heading`: `"Intro text.\n\fNotes:\n------\n\nSome note.\n"` → the lines include `"Notes:"` and `"------"`.
  - `test_double_form_feed`: `"A.\n\f\f\n   September 1981\n\nB.\n"` → the lines contain `"A."` and `"B."` and not `"September 1981"`.
  - `test_lowercase_and_roman_page_numbers`: lines ending `[page 3]` and `[Page iii]` are removed.
  - `test_crlf_normalized`: `"a\r\nb\r\n"` → `["a", "b", ""]` or `["a", "b"]` (either is fine; assert that no line contains `"\r"`).
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `strip_pagination` in `app/ingest/parse.py` (module docstring: what the two passes are). Add the `@dataclass(frozen=True) class Section` with `section_id: str`, `section_title: str`, `text: str` here now; Task 4 uses it.
- [ ] **Step 4:** Run `make check`. Expected: all pass.
- [ ] **Step 5:** Commit `feat: strip RFC pagination`.

### Task 4: Numbered section parser

**Files:**
- Modify: `app/ingest/parse.py`
- Create: `tests/ingest/fixtures/rfc_old_paged.txt`, `tests/ingest/fixtures/rfc_new_unpaged.txt`, `tests/ingest/test_parse_numbered.py`

**Interfaces:**
- Consumes: `strip_pagination`, `Section` (Task 3).
- Produces: `def parse_numbered(lines: list[str]) -> list[Section]` (returns `[]` if no numbered heading is found); `def next_ids(current: tuple[str, ...] | None) -> set[tuple[str, ...]]`.

A line is a **heading** only if **all** of the following hold:
1. It matches one of these (leading whitespace allowed, because RFC 791 centers its top-level headings):
   - numbered: `^\s*(\d+(?:\.\d+)*)\.?\s+([A-Za-z"'].*?)\s*$`
   - appendix: `^\s*appendix\s+([A-Z])[.:]?\s+(\S.*?)\s*$` (the word `appendix` is case-insensitive, the letter must be uppercase)
   - appendix subsection: `^\s*([A-Z](?:\.\d+)+)\.?\s+([A-Za-z"'].*?)\s*$`
2. The title does not end with `.` and has no dot leader (`\.{3,}`). This rejects TOC lines and sentence-like list items.
3. The next line is blank, or it's the end of the file. This rejects TOC entries that sit on consecutive lines and wrapped list items.
4. Its id (split on `.`) is in `next_ids(current)`, where `current` is the id of the last accepted heading.

`next_ids` (the core rule; implement exactly this):
```python
def next_ids(current):
    if current is None:
        return {("1",)}
    allowed = {current + ("1",)}                 # first child: 3.2 -> 3.2.1
    for i in range(len(current)):                # next sibling at each level: 3.2.1 -> 3.2.2, 3.3, 4
        allowed.add(current[:i] + (bump(current[i]),))
    if current[0].isdigit():
        allowed.add(("A",))                      # appendices start after numbered sections
    return allowed
# bump("3") == "4"; bump("A") == "B"
```
Restrict `("A",)`-style ids (a single letter) to the appendix regex. Otherwise a sentence such as `A user interface should allow` would be read as Appendix A.

Front matter: if the text before the first heading has a line equal to `Abstract` (ignoring surrounding whitespace and case), emit `Section("0", "Abstract", …)`. Its text runs from the line after `Abstract` up to the next non-blank line that starts at column 0, or up to the first heading. All other front matter is dropped, including the status memo, copyright, and TOC. Each section's text is the lines between its heading and the next one, normalized as described in Global Constraints (`textwrap.dedent`).

- [ ] **Step 1: Create fixtures** (`\f` here means a literal form-feed character in the file).

`rfc_old_paged.txt`:
```
Network Working Group                                          A. Author
Request for Comments: 9999                                   Example Org
                                                              March 1999


                        Example Transfer Protocol

Abstract

   This memo defines the Example Transfer Protocol.

Status of this Memo

   Distribution of this memo is unlimited.

Table of Contents

   1.  Introduction ................................................  1
   2.  Operation ...................................................  2
   Appendix A.  Examples ...........................................  3



Author                       Informational                      [Page 1]
\f
RFC 9999                Example Transfer Protocol             March 1999


1.  Introduction

   The protocol moves examples between hosts.

1.1.  Terminology

   An example is a unit of data.

2.  Operation

   Hosts follow these steps:

   1.  Open a connection.

   2.  Send the example.

   3.  Close the connection.

   The steps repeat until done.



Author                       Informational                      [Page 2]
\f
RFC 9999                Example Transfer Protocol             March 1999


   The receiver acknowledges each example.

Appendix A.  Examples

   A sample exchange.

A.1.  Simple Exchange

   One host sends one example.
```

`rfc_new_unpaged.txt`:
```
Internet Engineering Task Force (IETF)                         A. Author
Request for Comments: 9998                                   Example Org
Category: Standards Track                                      June 2022


                         Example Sync Protocol

Abstract

   This document specifies the Example Sync Protocol.

Table of Contents

   1.  Introduction
   2.  Protocol
     2.1.  Messages
       2.1.1.  Hello
     2.2.  Errors
   3.  Security Considerations

1.  Introduction

   Sync keeps two hosts in step.

2.  Protocol

2.1.  Messages

   Each message has a type.

2.1.1.  Hello

   Hello opens a session.

2.2.  Errors

   Errors close a session.

3.  Security Considerations

   Sync has no security.
```

- [ ] **Step 2: Write failing tests** in `tests/ingest/test_parse_numbered.py` (a helper reads the fixture and calls `parse_numbered(strip_pagination(raw))`):
  - `test_old_paged_sections`: the result as `(id, title, text)` tuples equals
    ```python
    [("0", "Abstract", "This memo defines the Example Transfer Protocol."),
     ("1", "Introduction", "The protocol moves examples between hosts."),
     ("1.1", "Terminology", "An example is a unit of data."),
     ("2", "Operation", "Hosts follow these steps:\n\n1.  Open a connection.\n\n"
                        "2.  Send the example.\n\n3.  Close the connection.\n\n"
                        "The steps repeat until done.\n\nThe receiver acknowledges each example."),
     ("A", "Examples", "A sample exchange."),
     ("A.1", "Simple Exchange", "One host sends one example.")]
    ```
  - `test_old_paged_excludes_front_matter`: no section text contains `"Distribution of this memo"`, `"...."`, or `"Table of Contents"`.
  - `test_new_unpaged_ids_and_titles`: ids `== ["0", "1", "2", "2.1", "2.1.1", "2.2", "3"]`, titles of 2.1.1 `== "Hello"` and 3 `== "Security Considerations"`, and section `"2"` has text `""`.
  - `test_next_ids`: `next_ids(None) == {("1",)}`; `next_ids(("2", "1", "1")) == {("2","1","1","1"), ("2","1","2"), ("2","2"), ("3",), ("A",)}`; `next_ids(("A", "1")) == {("A","1","1"), ("A","2"), ("B",)}`.
  - `test_no_numbered_headings_returns_empty`: `parse_numbered(["Introduction", "------", "", "Text."]) == []`.
- [ ] **Step 3:** Run the tests. Expected: FAIL.
- [ ] **Step 4:** Implement `next_ids`, a `bump` helper, and `parse_numbered`.
- [ ] **Step 5:** Run `make check`. Expected: all pass.
- [ ] **Step 6:** Commit `feat: parse numbered RFC sections`.

### Task 5: Unnumbered fallback, `parse_rfc`, and checking against the real RFCs

**Files:**
- Modify: `app/ingest/parse.py`
- Create: `tests/ingest/fixtures/rfc_unnumbered.txt`, `tests/ingest/test_parse_rfc.py`, `scripts/parse_report.py`

**Interfaces:**
- Consumes: `strip_pagination`, `parse_numbered`, `Section` (Tasks 3–4); `load_rfc_list`, `RfcEntry.filename` (Task 1).
- Produces:
  - `def parse_unnumbered(lines: list[str]) -> list[Section]`: a heading is a non-blank line at column 0 whose next line is only `-` or `=` characters (at least 3, trailing spaces allowed). The title is stripped of a trailing `:`, and the underline is not part of any text. Text before the first heading becomes `Section("0", "Preamble", …)` if it's non-empty. Headings get `u1`, `u2`, … in order. Returns `[]` if no heading is found.
  - `def parse_rfc(raw: str) -> list[Section]`: `strip_pagination`, then `parse_numbered`. If that returns `[]`, try `parse_unnumbered`. If that also returns `[]`, return `[Section("0", "Full text", <normalized whole text>)]`. **This is the function sessions 3+ call.**
  - `uv run python -m scripts.parse_report` prints one line per RFC in the list: `rfc9293  sections=… top-level=1 2 3 … A B`, or `rfc9293  MISSING` if it hasn't been downloaded. It marks a line with `CHECK` when `sections <= 2`.

- [ ] **Step 1: Create `rfc_unnumbered.txt`** (in the style of RFC 768, plus an RFC 826-style page with no running header):
```
RFC 9997                                                       A. Author
                                                          1 January 1980

                        Example Datagram Protocol
                        -------------------------

Introduction
------------

This protocol sends datagrams.

Fields
------

Port is a 16-bit field.

Author                                                          [page 1]
\f
                                                           1 Jan 1980
Example Datagram Protocol                                     RFC 9997
Fields

Length counts octets.
\f
Notes:
------

Checksums are optional.
```
- [ ] **Step 2: Write failing tests** in `tests/ingest/test_parse_rfc.py`:
  - `test_unnumbered_sections`: `parse_rfc(fixture)` gives ids `["0", "u1", "u2", "u3"]` and titles `["Preamble", "Introduction", "Fields", "Notes"]`. The text of `u2` `== "Port is a 16-bit field.\n\nLength counts octets."` (the repeated `Fields` from the page header is gone), `u3` text `== "Checksums are optional."`, and `"Example Datagram Protocol"` is in the `"0"` text.
  - `test_ids_are_stable`: `parse_rfc(fixture) == parse_rfc(fixture)`.
  - `test_numbered_preferred`: `parse_rfc` on `rfc_old_paged.txt` returns the same ids as `test_old_paged_sections`.
  - `test_no_headings_at_all`: `parse_rfc("Just a note.\n\nMore.\n") == [Section("0", "Full text", "Just a note.\n\nMore.")]`.
  - `test_real_rfcs_parse` (marked `pytest.mark.skipif(not Path("data/raw/rfc9293.txt").exists(), reason="run make fetch")`): for every downloaded RFC in the list, `len(parse_rfc(...)) >= 3`. RFC 9293's top-level ids are `["0", "1", "2", "3", "4", "5", "6", "7", "8", "A", "B"]`. RFC 768's titles start `["Preamble", "Introduction", "Format", "Fields", "User Interface", "IP Interface", "Protocol Application", "Protocol Number", "References"]`.
- [ ] **Step 3:** Run the tests. Expected: FAIL.
- [ ] **Step 4:** Implement `parse_unnumbered`, `parse_rfc`, and `scripts/parse_report.py`.
- [ ] **Step 5:** Run `make check`, then `uv run python -m scripts.parse_report`. Expected: no `MISSING` and no `CHECK` lines, and each RFC's top-level ids run without gaps up to its last section (open the RFC's TOC to confirm any you are unsure about). For each RFC that comes out wrong, add a small fixture reproducing the layout and a failing test in `test_parse_rfc.py`, then fix the rule. Keep fixes to single rules with a comment saying which RFC needed them. **Do not special-case RFC numbers.**
- [ ] **Step 6:** Update `CLAUDE.md` Local runtime with `make fetch` and `uv run python -m scripts.parse_report`, and the README status line ("session 2: RFC fetch + parse"). Run `make check`.
- [ ] **Step 7:** Commit `feat: parse unnumbered RFCs and add parse report`.
