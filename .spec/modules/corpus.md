# corpus

**Owner:** Chris (sourcing is manual) · **Chunk:** C1.1 · **Spec:** §3.1

## Purpose
Assemble 15–20 complete, real, public commercial package policies — dec page, forms schedule,
and endorsements — with recorded provenance. No client dependency.

## Surface
- `corpus/raw/` — as-downloaded PDFs, untouched. Git-ignored.
- `corpus/base/<doc_id>.pdf` — the working copy used as a pair's expiring side.
- `corpus/ledger.json` — one entry per document: `doc_id`, `source` (courtlistener | gov |
  risk_pool | serff | specimen), `source_url`, `retrieved_at`, `carrier`, `page_count`,
  `has_scanned_pages`, `notes`.
- `pc corpus add <pdf> --source ... --url ...` — appends to the ledger, records page count and
  whether any page lacks a text layer.
- `pc corpus status` — prints coverage against the §3 targets.

## Targets (spec §3.2)
- 20 pairs minimum, 3–5 distinct carriers.
- ≥4 pairs where the only material finding is subtle (edition date, AI scope narrowing).
- ≥2 pairs with scanned/image-only pages.
- ≥2 pairs with zero material findings.

## Invariants
- Every document has a `source_url` that a stranger could follow. If it can't be re-fetched
  publicly, it doesn't belong in the corpus.
- **ISO forms are licensed by Verisk.** Processing individual ISO forms that appear inside
  these documents is fine; assembling a form catalog is not. Do not build sourcing around it.
- Raw PDFs are never committed. Only `ledger.json` and `corpus/pairs/*/manifest.json` are
  tracked.

## Failure modes
- Collecting dec pages only. A dec page without a forms schedule and endorsements cannot
  exercise most of the §5.2 taxonomy — half the findings live in the endorsements.
- Single-carrier corpus. Form numbering and dec-page layout vary enough by carrier that a
  normalizer tuned on one will fail on the next.
- Deferring the scanned pages. §14 names extraction on scanned carrier PDFs as *the* technical
  risk. Get those two into the corpus first, not last.
