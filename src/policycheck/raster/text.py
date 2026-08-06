"""Text layer access and `source_text` → `bbox` resolution.

This module exists because **the Claude API returns no bounding boxes for PDF content**, but
spec §4.1 requires one per field and §9 requires bbox highlighting in the split-pane view.
The bridge is:

    the model returns verbatim `source_text` + `page`
      → find_text() locates that string in the page's text layer
        → bbox

The hard part is not the search, it is that the model's quoted snippet and the PDF's text
layer rarely agree byte-for-byte. Column layout inserts newlines, ligatures collapse two
glyphs into one codepoint, soft hyphens appear mid-word, and run lengths of spaces vary. So
matching happens in a normalized space, with an index map back to the original characters so
the bbox can still be built from real glyph boxes.

Coordinates are **PDF user space, origin bottom-left, `[x0, y0, x1, y1]`** — what pypdfium2
reports natively. The web layer converts to pdf.js viewport space; nothing upstream of the UI
does coordinate math.

Pages are **1-indexed** throughout the pipeline (they appear in reports, and users count from
one). pypdfium2 is 0-indexed; the conversion happens here, once.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

from policycheck.contracts import BBox

# Every PDF in RECAP carries the court's ECF stamp burned into each page, e.g.
#   "Case 1:06-cv-00157-PLF Document 41-2 Filed 05/31/2007 Page 1 of 39"
# It is real text even when the page body is a scan. Left in, every scanned document looks
# like it has a text layer — which would hide exactly the documents spec §3.2 most needs.
ECF_STAMP = re.compile(
    r"^.*\bCase\b.*\bDoc(?:ument)?\b.*\bFiled\b.*$", re.IGNORECASE | re.MULTILINE
)

# Body characters (stamp removed) before a page counts as having a text layer. A real policy
# page runs to hundreds; a watermark or page number does not.
TEXT_LAYER_MIN_CHARS = 100

# Codepoints that carry no meaning for matching and should vanish entirely.
_INVISIBLE = {
    "­",  # soft hyphen
    "​",  # zero-width space
    "‌",
    "‍",
    "﻿",
}


def _normalize_char(ch: str) -> str:
    """Fold one source character to its match form. May return 0, 1, or several characters.

    NFKD decomposition expands ligatures (ﬁ → fi) and normalizes the various dash and space
    codepoints that PDF producers emit interchangeably.
    """
    if ch in _INVISIBLE:
        return ""
    folded = unicodedata.normalize("NFKD", ch)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return folded.casefold()


def _normalize(text: str) -> tuple[str, list[int]]:
    """Normalize for matching, returning the folded text and a map back to source indices.

    `index_map[i]` is the index in `text` of the character that produced `normalized[i]`.
    That map is what lets a match in normalized space be turned back into real glyph boxes.

    Whitespace runs collapse to a single space so that a snippet quoted with one space still
    matches a table cell padded with twelve.
    """
    out: list[str] = []
    index_map: list[int] = []
    prev_space = True  # leading whitespace is dropped

    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                index_map.append(i)
                prev_space = True
            continue
        for folded in _normalize_char(ch):
            out.append(folded)
            index_map.append(i)
            prev_space = False

    while out and out[-1] == " ":
        out.pop()
        index_map.pop()

    return "".join(out), index_map


@dataclass(frozen=True)
class PageText:
    """One page's text layer, with everything needed to locate a snippet within it."""

    page: int
    """1-indexed."""
    raw: str
    """Characters as pdfium reports them, index-aligned with glyph boxes."""
    normalized: str
    index_map: list[int]

    @property
    def body(self) -> str:
        """Raw text with the court's ECF stamp removed."""
        return ECF_STAMP.sub("", self.raw).strip()

    @property
    def has_text_layer(self) -> bool:
        return len(self.body) >= TEXT_LAYER_MIN_CHARS


def _open(pdf: Path | pdfium.PdfDocument) -> tuple[pdfium.PdfDocument, bool]:
    """Accept either a path or an already-open document. Returns (doc, we_opened_it)."""
    if isinstance(pdf, pdfium.PdfDocument):
        return pdf, False
    return pdfium.PdfDocument(pdf), True


def page_text(pdf: Path | pdfium.PdfDocument, page: int) -> PageText:
    """Extract one page's text layer. `page` is 1-indexed.

    Raises IndexError for a page outside the document. Page numbers reach this module from
    model output, so an out-of-range citation is a realistic input, not a programming error —
    it deserves a message that says which page and how many exist rather than pdfium's
    "Failed to load page."
    """
    doc, owned = _open(pdf)
    try:
        if not 1 <= page <= len(doc):
            raise IndexError(
                f"page {page} is outside this document (1-{len(doc)}). "
                f"Page numbers are 1-indexed."
            )
        textpage = doc[page - 1].get_textpage()
        # get_text_range over the full char count keeps string indices aligned with glyph
        # indices. get_text_bounded() inserts layout newlines and breaks that alignment.
        raw = textpage.get_text_range(0, textpage.count_chars())
        normalized, index_map = _normalize(raw)
        return PageText(page=page, raw=raw, normalized=normalized, index_map=index_map)
    finally:
        if owned:
            doc.close()


def has_text_layer(pdf: Path | pdfium.PdfDocument, page: int) -> bool:
    """True when the page carries real body text rather than a scan (or just an ECF stamp)."""
    return page_text(pdf, page).has_text_layer


def find_text(pdf: Path | pdfium.PdfDocument, page: int, needle: str) -> BBox | None:
    """Locate `needle` on `page` and return its bounding box, or None.

    Returns None rather than guessing when:
      - the needle is not present (on a scanned page nothing is; on a text page it usually
        means the model paraphrased instead of quoting verbatim, which is an extraction
        prompt bug worth logging), or
      - the needle appears more than once (`$1,000,000` may occur in three rows; the caller
        cannot tell which was meant).

    Deliberately does NOT gate on `has_text_layer`. That check classifies a page as scanned
    and is calibrated for whole-document screening; a sparse page — a forms-schedule
    continuation, an endorsement title page — can fall below its threshold while still
    containing the exact string being looked for. If the text is there, resolve it.

    A `None` bbox is acceptable — it degrades the UI jump to a page-level highlight. A
    *wrong* bbox is not: it looks authoritative and breaks spec invariant 7, a human being
    able to verify any single finding in under 90 seconds.
    """
    if not needle or not needle.strip():
        return None

    doc, owned = _open(pdf)
    try:
        # A hallucinated page number degrades to "no bbox", the same as a scanned page.
        # Surfacing the bad citation itself is extract's job, not this module's.
        if not 1 <= page <= len(doc):
            return None

        pt = page_text(doc, page)
        target, _ = _normalize(needle)
        if not target:
            return None

        # Ambiguity is a None, so find the second occurrence before committing to the first.
        first = pt.normalized.find(target)
        if first == -1:
            return None
        if pt.normalized.find(target, first + 1) != -1:
            return None

        start = pt.index_map[first]
        end = pt.index_map[first + len(target) - 1]
        return _union_charboxes(doc[page - 1].get_textpage(), start, end)
    finally:
        if owned:
            doc.close()


def _union_charboxes(textpage: pdfium.PdfTextPage, start: int, end: int) -> BBox | None:
    """Union the glyph boxes for source indices [start, end] inclusive.

    A snippet spanning a line break produces a box covering both lines and the gap between —
    correct for highlighting a labelled value, which is what these snippets are.
    """
    boxes: list[tuple[float, float, float, float]] = []
    for i in range(start, end + 1):
        try:
            boxes.append(textpage.get_charbox(i))
        except Exception:
            # Whitespace and control characters legitimately have no glyph box.
            continue
    if not boxes:
        return None

    # pdfium reports (left, bottom, right, top) in PDF user space.
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )
