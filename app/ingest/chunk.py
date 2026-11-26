"""Split RFC sections into chunks of at most ~`max_tokens` tokens, with overlap.

Three steps:
1. Units: the section's paragraphs. A paragraph over the limit is replaced by its lines,
   and a line over the limit by its words. (A single word over the limit stays one unit.)
2. Pack units greedily into a chunk while their token counts sum to at most `max_tokens`.
3. Overlap: the next chunk starts by repeating the previous chunk's trailing units, as many
   as fit in `overlap_tokens` and still leave room for the next new unit (none otherwise).
   An exact duplicate of an earlier chunk in the same section is dropped.

A chunk's text is an exact slice of the section text (first unit's start to last unit's
end), so the RFC's own formatting, such as indentation in diagrams, is kept for citations.
Chunks never cross sections because each section is chunked on its own.
"""

import hashlib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.ingest.parse import Section

TokenCounter = Callable[[str], int]


@dataclass(frozen=True)
class Chunk:
    rfc_number: int
    section_id: str
    section_title: str
    text: str
    token_count: int

    @property
    def embed_text(self) -> str:
        """What the embedder sees: a locating header line, then the chunk text."""
        return f"RFC {self.rfc_number} §{self.section_id} {self.section_title}\n{self.text}"

    @property
    def content_hash(self) -> str:
        """Hash of exactly what gets embedded, so any change to it (title too) re-embeds."""
        return hashlib.sha256(self.embed_text.encode()).hexdigest()


@dataclass(frozen=True)
class _Unit:
    start: int
    end: int
    tokens: int


def _line_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """(start, end) of each non-blank line in text[start:end], without trailing spaces."""
    spans = []
    pos = start
    for line in text[start:end].split("\n"):
        stripped = line.rstrip()
        if stripped.strip():
            spans.append((pos, pos + len(stripped)))
        pos += len(line) + 1
    return spans


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    """Group consecutive non-blank lines; a blank line ends a paragraph."""
    paragraphs: list[tuple[int, int]] = []
    for start, end in _line_spans(text, 0, len(text)):
        previous_end = paragraphs[-1][1] if paragraphs else None
        if previous_end is not None and text[previous_end:start].count("\n") == 1:
            paragraphs[-1] = (paragraphs[-1][0], end)  # the very next line: same paragraph
        else:
            paragraphs.append((start, end))
    return paragraphs


def _units(text: str, count_tokens: TokenCounter, max_tokens: int) -> list[_Unit]:
    units: list[_Unit] = []
    for p_start, p_end in _paragraph_spans(text):
        tokens = count_tokens(text[p_start:p_end])
        if tokens <= max_tokens:
            units.append(_Unit(p_start, p_end, tokens))
            continue
        for l_start, l_end in _line_spans(text, p_start, p_end):
            tokens = count_tokens(text[l_start:l_end])
            if tokens <= max_tokens:
                units.append(_Unit(l_start, l_end, tokens))
                continue
            for word in re.finditer(r"\S+", text[l_start:l_end]):
                w_start, w_end = l_start + word.start(), l_start + word.end()
                units.append(_Unit(w_start, w_end, count_tokens(text[w_start:w_end])))
    return units


def chunk_text(
    text: str, *, count_tokens: TokenCounter, max_tokens: int, overlap_tokens: int
) -> list[str]:
    units = _units(text, count_tokens, max_tokens)
    chunks: list[str] = []
    first = 0
    while first < len(units):
        last, total = first, units[first].tokens
        while last + 1 < len(units) and total + units[last + 1].tokens <= max_tokens:
            last += 1
            total += units[last].tokens
        chunks.append(text[units[first].start : units[last].end])
        if last == len(units) - 1:
            break
        # Walk back from the last unit while the repeated units still fit in the overlap and
        # still leave room for the next new unit (otherwise the next chunk would be only a
        # repeat of this one's tail). Never back to `first`, so every chunk makes progress.
        next_first, overlap = last + 1, 0
        room = max_tokens - units[last + 1].tokens
        for j in range(last, first, -1):
            overlap += units[j].tokens
            if overlap > min(overlap_tokens, room):
                break
            next_first = j
        first = next_first
    return chunks


def chunk_document(
    rfc_number: int,
    sections: Sequence[Section],
    *,
    count_tokens: TokenCounter,
    max_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in sections:
        pieces = chunk_text(
            section.text,
            count_tokens=count_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        seen: set[str] = set()
        for piece in pieces:
            if piece in seen:
                continue  # a repeated passage; storing it twice adds nothing (and hash is UNIQUE)
            seen.add(piece)
            chunks.append(
                Chunk(
                    rfc_number=rfc_number,
                    section_id=section.section_id,
                    section_title=section.section_title,
                    text=piece,
                    token_count=count_tokens(piece),
                )
            )
    return chunks
