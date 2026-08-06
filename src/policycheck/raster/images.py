"""Page rasters for the split-pane citation view.

Content-addressed and run-scoped. Spec invariant 5 says demo mode retains nothing, so the
cache lives under a directory the run owns and deletes when it ends — including on failure.
Caching by content hash rather than filename means the two cached demo pairs stay warm across
runs without the cache ever being keyed to a document identity we promised not to keep.
"""

import hashlib
from pathlib import Path

import pypdfium2 as pdfium

from policycheck.config import settings

DEFAULT_SCALE = 2.0
"""Roughly 144 DPI. Legible for reading a dec page on screen without making a 60-page
document stutter in front of a stranger."""


def document_key(pdf: Path) -> str:
    """Short content hash. Two identical uploads share cache entries; a changed byte does not."""
    return hashlib.sha256(pdf.read_bytes()).hexdigest()[:16]


def page_image(
    pdf: Path,
    page: int,
    scale: float = DEFAULT_SCALE,
    cache_dir: Path | None = None,
) -> bytes:
    """Render one page to PNG bytes. `page` is 1-indexed. Cached on disk.

    Rendering is the slow part of the UI path, and a user clicking between findings revisits
    the same handful of pages repeatedly — so the cache earns its place even within one run.
    """
    root = cache_dir or settings().raster_cache_dir
    dest = root / document_key(pdf) / f"p{page:04d}@{scale:g}.png"
    if dest.exists():
        return dest.read_bytes()

    doc = pdfium.PdfDocument(pdf)
    try:
        if not 1 <= page <= len(doc):
            raise IndexError(f"page {page} is outside this document (1-{len(doc)}).")
        # pypdfium2 types `scale` as int, but renders fine at fractional scales — verified
        # at 1.6 and 2.0. Keeping the float API so callers can tune resolution per surface.
        image = doc[page - 1].render(scale=scale).to_pil()  # pyright: ignore[reportArgumentType]
    finally:
        doc.close()

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Write via a temp file so a crashed render cannot leave a truncated PNG that later
    # reads as a cache hit.
    tmp = dest.with_suffix(".png.tmp")
    image.save(tmp, format="PNG")
    tmp.replace(dest)
    return dest.read_bytes()


def page_size(pdf: Path, page: int) -> tuple[float, float]:
    """Page dimensions in PDF user space. The web layer needs these to scale bboxes."""
    doc = pdfium.PdfDocument(pdf)
    try:
        return doc[page - 1].get_size()
    finally:
        doc.close()


def page_count(pdf: Path) -> int:
    doc = pdfium.PdfDocument(pdf)
    try:
        return len(doc)
    finally:
        doc.close()


def clear_cache(cache_dir: Path | None = None) -> None:
    """Delete the raster cache. Call in a `finally` at the end of every run.

    Spec invariant 5 is stated to prospects unprompted; leaving rasters on disk past the run
    makes that statement false.
    """
    root = cache_dir or settings().raster_cache_dir
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    root.rmdir()
