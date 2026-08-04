# Build plan — modules and chunks

Derived from `spec.md`. Modules are the code units; chunks are the ordered units of work.
Per-module detail lives in `.spec/modules/<name>.md`.

## Module map

```
                     contracts  ← the spine; everything imports it
                         │
        ┌────────────────┼──────────────────┬──────────────┐
        │                │                  │              │
     corpus          extract            normalize       raster
   (real PDFs)   (Claude, 2 passes)   (form regex,    (page images,
        │                │              money, dates)   bbox resolve)
        │                │                  │              │
     pairgen ───────────►│◄─────────────────┘              │
  (renewal variants,     │                                 │
   ground truth)      compare  ← deterministic; no model   │
        │            (match + taxonomy + severity)         │
        │                │                                 │
        │        ┌───────┴────────┐                        │
        │     narrate          report                      │
        │   (1 LLM call)   (internal + client)             │
        │                        │                         │
     evals ◄────────────────────┘                          │
   (scorecard, gates)                                      │
                                 persistence ─── api ──── web
                                  (Postgres)   (FastAPI)  (split-pane)
```

## Module ownership

| Module | Owner | Why |
|---|---|---|
| `contracts` | Chris | The data contract is the spine. Worth building by hand. |
| `corpus` | Chris | Manual sourcing work + a small ledger script. |
| `pairgen` | Claude | PDF surgery tooling. Not learning-budget code. |
| `raster` | Claude | pypdfium2 plumbing + bbox resolution. |
| `normalize` | Chris | Highest-leverage code in the build (spec §4.3). |
| `extract` | Split | Claude scaffolds API plumbing; Chris writes the prompt + merge. |
| `compare` | Chris | The heart of the product. |
| `narrate` | Chris | Prompt is a scope-guard surface; Chris writes it. |
| `report` | Chris | Copy invariants are the product. |
| `evals` | Split | Claude writes the runner; Chris writes the metrics. |
| `persistence` | Claude | Models + migrations. |
| `api` | Claude | Orchestration plumbing. |
| `web` | Split | Claude scaffolds; Chris builds the citation jump. |

## Chunks

### Phase 0 — Foundation
- **C0.1** Repo skeleton, `pyproject.toml`, tooling, `.spec/` docs. *(done)*
- **C0.2** `contracts` — `Field[T]`, `PolicySnapshot`, `Finding`, `Manifest`. Frozen before
  the extractor is written (invariant 4).
- **Exit:** `uv run pyright` clean; a `PolicySnapshot` round-trips through JSON.

### Phase 1 — Ground truth
- **C1.1** `corpus` — source 15–20 real commercial package PDFs (CourtListener/RECAP first).
  Record provenance per document. **This is the critical path and it is manual.**
- **C1.2** `raster` — page rasters, text layer extraction, `source_text → bbox` resolution.
- **C1.3** `pairgen` — bbox-patch renewal generator + 20 manifests.
- **C1.4** `extract` v0 — single pass, dec page only, GL limits, with page + snippet citations.
- **Exit:** 20 manifests complete, schema stable, one real document extracts with citations
  that resolve to correct pages.

### Phase 2 — Engine
- **C2.1** `normalize` — form family canonicalizer, tested against every raw form number in
  the corpus. Build this before anything that consumes forms.
- **C2.2** `normalize` — money, dates, enums, addresses; `INCLUDED` / `excluded` sentinels.
- **C2.3** `extract` v1 — dual-pass, full schema, confidence merge → `needs_review`.
- **C2.4** `compare` — entity matching (forms, locations, AI parties).
- **C2.5** `compare` — findings taxonomy + severity rules.
- **C2.6** `evals` — harness, scorecard, run-over-run diff.
- **Exit:** material recall 100% across the manifest set (spec §8).

### Phase 3 — Surface
- **C3.1** `narrate` — single call over ruled findings; every sentence traces to a finding.
- **C3.2** `report` — internal findings report (including `UNCHANGED — VERIFIED` count).
- **C3.3** `report` — client-facing renewal difference summary. Print it.
- **C3.4** `persistence` + `api` — runs, findings, eval results; sync run endpoint.
- **C3.5** `web` — split-pane PDF, click-finding → both sides jump to cited page with bbox
  highlighted. **Build before anything cosmetic** (spec §9).
- **C3.6** Two cached demo pairs + offline check.
- **Exit:** a stranger can be handed the laptop and understand the output without narration.

### Phase 4 — Correction (starts during Phase 2, does not wait for Phase 3)
- **C4.1** Take the §5.2 taxonomy to 10 LinkedIn conversations framed as critique requests.
- **C4.2** One state association event.
- **C4.3** Revise taxonomy against what comes back.
- **Exit:** a working account manager says the checklist matches their job.

## Open technical decisions

1. **bbox is not free.** The Claude API returns no bounding boxes for PDF content. Spec §4.1
   requires one per field and §9 requires bbox highlighting. Plan: the model returns verbatim
   `source_text` + `page`, and `raster` resolves that string to a bbox against the page's text
   layer. Scanned pages have no text layer — those degrade to a page-level highlight with
   `bbox: null`. See `.spec/modules/raster.md`. **This is the biggest technical unknown in
   Phase 1 and should be proven on a real scanned PDF early.**
2. **Citations feature vs structured output.** The API's native `citations` feature is
   incompatible with `output_config.format` (returns 400). Citations therefore come from the
   extraction schema itself, not the API feature. See `.spec/modules/extract.md`.
3. **Real renewal pairs.** Synthetic pairs are a correctness harness, not a realism claim
   (spec §14). Replace with real pairs as soon as an agency shares them.
