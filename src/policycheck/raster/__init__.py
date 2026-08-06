"""Everything that reads a PDF as pixels or coordinates.

The single place PDFs are opened. Coordinates leave here in PDF user space, origin
bottom-left; page numbers leave here 1-indexed.
"""

from policycheck.raster.images import (
    DEFAULT_SCALE,
    clear_cache,
    document_key,
    page_count,
    page_image,
    page_size,
)
from policycheck.raster.text import (
    ECF_STAMP,
    TEXT_LAYER_MIN_CHARS,
    PageText,
    find_text,
    has_text_layer,
    page_text,
)

__all__ = [
    "DEFAULT_SCALE",
    "ECF_STAMP",
    "TEXT_LAYER_MIN_CHARS",
    "PageText",
    "clear_cache",
    "document_key",
    "find_text",
    "has_text_layer",
    "page_count",
    "page_image",
    "page_size",
    "page_text",
]
