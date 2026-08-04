# web

**Owner:** Claude scaffolds; Chris builds the citation jump · **Chunk:** C3.5 · **Spec:** §9

## Purpose
The demo surface. Drop two PDFs → named-stage progress → findings list → click a finding →
split-pane PDF view, both sides scrolled to the cited page with the bbox highlighted.

> **The click-to-citation jump is the moment that earns a follow-up meeting. Build it before
> building anything cosmetic.** (spec §9)

## Stack
React 19 + TypeScript + Vite + `pdfjs-dist` used directly (not a wrapper component — the bbox
overlay needs control of the canvas and viewport transform).

## Layout
```
┌─────────────────────────────┬──────────────────────────────┐
│  Findings                   │  Prior p.3    │  Renewal p.3 │
│  ─────────────────────────  │  ┌─────────┐  │ ┌─────────┐  │
│  ▸ Each Occurrence          │  │ ▓▓▓▓▓   │  │ │ ▓▓▓▓▓   │  │
│    $1,000,000 → $500,000    │  │         │  │ │         │  │
│  ▸ CG0001 edition 04/13→…   │  └─────────┘  │ └─────────┘  │
└─────────────────────────────┴──────────────────────────────┘
```

## Coordinate conversion
The one piece of real logic here. `raster` emits **PDF user space, origin bottom-left**.
pdf.js renders in viewport space, origin top-left, with a scale factor. Convert with
`viewport.convertToViewportRectangle(bbox)` — do not hand-roll the flip, and do not do any
coordinate math outside this layer.

## Degradation
- `bbox: null` (scanned page or unresolved snippet) → scroll to the page and highlight the
  whole page edge rather than a region. Never guess a rectangle.
- Both sides jump together even when only one side has a bbox.

## Invariants
- The UI renders findings; it never re-derives or re-ranks them. Severity ordering comes from
  the API.
- No copy in the UI that violates spec §11 — the interface is as much a scope-guard surface as
  the narration prompt.
- Works offline against the two cached demo pairs.

## Build order
1. Split-pane pdf.js render at a fixed page. *(prove rendering works)*
2. Findings list from `GET /runs/{id}/findings`.
3. **Click → both panes jump to cited pages.** *(the moment)*
4. bbox overlay.
5. Upload + progress stages.
6. Everything cosmetic, last.

## Failure modes
- Building the upload flow and progress animation first, then running out of time for the jump.
  The jump is the demo; the upload is scaffolding around it.
- Rendering both PDFs at full resolution and making the laptop stutter in front of a stranger.
  Render at viewport scale, cache the rasters.
- A highlight that lands on the wrong region. A wrong bbox is worse than no bbox — it breaks
  invariant 7 (verify any finding in under 90 seconds) in the most damaging possible way,
  because it looks authoritative.
