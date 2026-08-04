# raster

**Owner:** Claude · **Chunk:** C1.2 · **Spec:** §4.1 (`bbox`), §9, §10

## Purpose
Everything that touches the PDF as pixels and coordinates: page images for the UI, the text
layer, and — the load-bearing part — resolving an extracted `source_text` string to a bounding
box on a page.

## Why this module exists
**The Claude API does not return bounding boxes for PDF content.** Spec §4.1 requires a `bbox`
per field and §9 requires bbox highlighting in the split-pane view. The bridge is:

> the model returns verbatim `source_text` + `page` → `raster` locates that string in the
> page's text layer → bbox.

This is the biggest technical unknown in Phase 1. Prove it on a real scanned PDF before
building anything on top of it.

## Surface
`src/policycheck/raster/`
- `page_image(pdf, page, scale) -> PNG bytes` — pypdfium2 render, cached on disk by
  `(sha256(pdf), page, scale)`.
- `page_text(pdf, page) -> PageText` — characters with their individual boxes, plus the
  reconstructed string and an index mapping string offsets back to characters.
- `find_text(pdf, page, needle) -> BBox | None` — normalizes whitespace on both sides, locates
  the needle, unions the character boxes. Returns `None` rather than guessing.
- `has_text_layer(pdf, page) -> bool` — drives the `scanned` path everywhere else.

## Coordinate contract
- One coordinate space: **PDF user space, origin bottom-left, `[x0, y0, x1, y1]`** — what
  pypdfium2 reports natively. The web layer converts to pdf.js viewport coordinates; nothing
  upstream of the UI does coordinate math.
- Page numbers are **1-indexed** everywhere in the pipeline (they appear in the report and the
  user counts from 1). pypdfium2 is 0-indexed — convert at the boundary, once, here.

## Degradation
| Case | Behavior |
|---|---|
| Text layer present, needle found | Real bbox |
| Text layer present, needle not found | `bbox: None`, log the miss — this usually means the model paraphrased instead of quoting verbatim, which is an extraction prompt bug |
| No text layer (scanned page) | `bbox: None`, page-level highlight in the UI |

`bbox: None` is acceptable. A *wrong* bbox is not — it breaks invariant 7 (a human verifies a
finding in under 90 seconds by following the citation).

## Invariants
- `find_text` never returns a best-effort or fuzzy match. Exact, whitespace-normalized, or
  nothing.
- The raster cache is content-addressed. Demo mode retains no documents (spec invariant 5), so
  the cache is scoped to the run and cleared with it.

## Failure modes
- Ligatures, soft hyphens, and multi-column layouts making the reconstructed page string differ
  from what the model quoted. Normalize aggressively on both sides before matching.
- A needle that occurs more than once on the page (e.g. `$1,000,000` in three rows). Prefer the
  longest verbatim snippet the model gives; if still ambiguous, return `None` rather than the
  first hit.
