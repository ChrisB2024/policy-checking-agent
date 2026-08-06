"""Tests for `source_text` → `bbox` resolution.

This is the piece the demo's best moment depends on (click a finding, both panes jump to the
cited page with the box highlighted), and it is the one part of the pipeline where being
subtly wrong is worse than failing outright — a wrong box looks authoritative.

Fixtures are generated with reportlab so text sits at coordinates the test knows, which is
what makes the bbox assertions meaningful rather than self-confirming.
"""

from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from policycheck.raster import find_text, has_text_layer, page_text

FONT_SIZE = 11
LINE_X = 72.0


@pytest.fixture(scope="module")
def dec_page(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A page shaped like a dec page: labelled values, one value repeated."""
    path = tmp_path_factory.mktemp("raster") / "dec.pdf"
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    c.setFont("Helvetica", FONT_SIZE)
    c.drawString(LINE_X, 700, "Each Occurrence Limit     $1,000,000")
    c.drawString(LINE_X, 680, "General Aggregate         $2,000,000")
    c.drawString(LINE_X, 660, "Products/Completed Ops    $2,000,000")  # repeats $2,000,000
    c.showPage()
    c.save()
    return path


@pytest.fixture(scope="module")
def stamp_only(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A scanned page as RECAP delivers it: body is an image, only the ECF stamp is text."""
    path = tmp_path_factory.mktemp("raster") / "scanned.pdf"
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    c.setFont("Helvetica", 9)
    c.drawString(60, 760, "Case 1:06-cv-00157-PLF Document 41-2 Filed 05/31/2007 Page 1 of 39")
    c.showPage()
    c.save()
    return path


def test_bbox_lands_where_the_text_was_drawn(dec_page: Path) -> None:
    box = find_text(dec_page, 1, "Each Occurrence Limit     $1,000,000")
    assert box is not None
    x0, y0, x1, y1 = box
    assert x0 == pytest.approx(LINE_X, abs=2)
    # Drawn on the y=700 baseline: the box spans descender to ascender around it.
    assert y0 < 700 < y1
    assert (y1 - y0) == pytest.approx(FONT_SIZE, abs=3)
    assert x1 > x0


@pytest.mark.parametrize(
    "needle",
    [
        "Each Occurrence Limit     $1,000,000",  # as drawn
        "Each Occurrence Limit $1,000,000",  # collapsed whitespace
        "Each  Occurrence   Limit  $1,000,000",  # different whitespace runs
        "each occurrence limit $1,000,000",  # different case
        "EACH OCCURRENCE LIMIT $1,000,000",
    ],
)
def test_matching_survives_whitespace_and_case(dec_page: Path, needle: str) -> None:
    """The model's quoted snippet rarely matches the text layer byte-for-byte.

    Column layout and table padding make run lengths unpredictable, so matching normalizes
    both sides. Every variant here must resolve to the same box.
    """
    assert find_text(dec_page, 1, needle) == find_text(
        dec_page, 1, "Each Occurrence Limit     $1,000,000"
    )


def test_narrow_needle_returns_narrow_box(dec_page: Path) -> None:
    """A bare value box is tighter than its whole labelled line, and sits inside it."""
    line = find_text(dec_page, 1, "Each Occurrence Limit     $1,000,000")
    value = find_text(dec_page, 1, "$1,000,000")
    assert line is not None and value is not None
    assert value[0] > line[0]  # starts further right
    assert value[2] == pytest.approx(line[2], abs=1)  # shares the right edge
    assert (value[2] - value[0]) < (line[2] - line[0])


def test_ambiguous_needle_returns_none(dec_page: Path) -> None:
    """$2,000,000 appears on two rows. Returning either would be a coin flip.

    A wrong bbox is worse than no bbox: it looks authoritative and breaks spec invariant 7.
    """
    assert find_text(dec_page, 1, "$2,000,000") is None
    # The same value is resolvable once its label disambiguates it.
    assert find_text(dec_page, 1, "General Aggregate         $2,000,000") is not None


def test_absent_needle_returns_none(dec_page: Path) -> None:
    """Usually means the model paraphrased instead of quoting verbatim — a prompt bug."""
    assert find_text(dec_page, 1, "Personal and Advertising Injury") is None


@pytest.mark.parametrize("needle", ["", "   ", "\n"])
def test_empty_needle_returns_none(dec_page: Path, needle: str) -> None:
    assert find_text(dec_page, 1, needle) is None


def test_ecf_stamp_does_not_count_as_a_text_layer(stamp_only: Path) -> None:
    """Every RECAP PDF carries the court's stamp burned into each page.

    Counting it as text would classify every scanned document as machine-readable — hiding
    exactly the documents spec §3.2 requires and §14 names as the main technical risk.
    """
    pt = page_text(stamp_only, 1)
    assert len(pt.raw) > 0, "the stamp itself is real text"
    assert pt.body == "", "…but nothing survives stripping it"
    assert not has_text_layer(stamp_only, 1)


def test_scanned_page_yields_no_bbox_rather_than_a_wrong_one(stamp_only: Path) -> None:
    """The guaranteed degradation path: ≥2 corpus pairs are image-only by design."""
    assert find_text(stamp_only, 1, "General Aggregate") is None


def test_search_is_not_gated_on_page_density(dec_page: Path) -> None:
    """A sparse page still resolves boxes.

    `has_text_layer` classifies a page as scanned and is calibrated for whole-document
    screening. Gating search on it would refuse to resolve a snippet sitting in plain sight
    on a short page — a forms-schedule continuation, an endorsement title page.
    """
    assert not has_text_layer(dec_page, 1), "fixture is deliberately below the threshold"
    assert find_text(dec_page, 1, "General Aggregate") is not None


def test_pages_are_one_indexed(dec_page: Path) -> None:
    """pypdfium2 is 0-indexed; the pipeline is 1-indexed and converts here, once."""
    assert page_text(dec_page, 1).page == 1


def test_out_of_range_page_says_so(dec_page: Path) -> None:
    """Page numbers arrive from model output, so out-of-range is realistic input.

    A citation to page 47 of a 39-page document must produce a message naming the page and
    the document's range, not pdfium's bare "Failed to load page."
    """
    with pytest.raises(IndexError, match=r"page 2 .*\(1-1\)"):
        page_text(dec_page, 2)
    with pytest.raises(IndexError):
        page_text(dec_page, 0)


def test_out_of_range_page_yields_no_bbox_rather_than_raising(dec_page: Path) -> None:
    """find_text degrades instead of crashing — a bad citation is a needs_review, not a stop.

    Flagging the bad page itself belongs to extract; this module just declines to guess.
    """
    assert find_text(dec_page, 47, "Each Occurrence Limit") is None
