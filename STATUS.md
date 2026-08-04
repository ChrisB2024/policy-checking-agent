# STATUS

_Last rewritten: 2026-08-03_

## What works
Nothing runs yet. This session set up the repo, chose the stack, and broke `spec.md` into
modules and chunks.

- Git initialized (no commits yet).
- `pyproject.toml` with the full dependency set. **Not yet installed** — `uv sync` hasn't run.
- `claude.md` filled in: working mode, the "use the thing" gate, repo specifics, scope guards.
- `.spec/plan.md` — module map, ownership, and the C0–C4 chunk sequence.
- `.spec/modules/*.md` — 13 module specs (contracts, corpus, pairgen, raster, extract,
  normalize, compare, narrate, report, evals, persistence, api, web).

## What's half-built
Nothing. No `src/` yet.

## What's blocked on Chris
- **C1.1 corpus sourcing** is the critical path and it's manual. 15–20 real commercial package
  policies from CourtListener/RECAP, public entity procurement, and state risk pools. Nothing
  downstream can be validated without them.
- Confirming the persistence line in `.spec/modules/persistence.md`: storing extracted
  `source_text` snippets in Postgres while claiming "documents are processed in memory and
  discarded." That's defensible but it should be a decision, not a drift.

## Decisions made this session
- **Python 3.13 + uv.** One tool for venv, lockfile, and running. The committed lockfile is
  what makes "runs offline on a laptop" (spec §9) true.
- **Pydantic v2** for the data contract. The `Field<T>` envelope in spec §4.1 is a generic
  model, and validation at the LLM boundary is exactly where the "no bare values" invariant
  needs enforcing. Also gives the JSON schema for structured extraction for free.
- **ruff** (lint + format) and **pyright** (types). Pyright because VS Code already runs it via
  Pylance — the editor and the CLI gate agree instead of showing two different error sets.
- **SQLAlchemy 2.0 async + Alembic.** Migrations are a real backend skill, and `alembic check`
  is the "must stay clean" gate in `claude.md`.
- **pikepdf + reportlab + Pillow** for `pairgen`: patch the real PDF in place rather than
  regenerate a synthetic one, so renewals keep real carrier layout and scan artifacts.
- **`claude-opus-5`** for extraction and narration.
- Deferred, per spec §10: ARQ, pgvector/embeddings.

## Open problem worth reading before Phase 1
**The Claude API returns no bounding boxes for PDF content**, but spec §4.1 requires a `bbox`
per field and §9 requires bbox highlighting. Plan: the model returns verbatim `source_text` +
`page`, and `raster.find_text` resolves that string against the page's text layer. Scanned
pages have no text layer and degrade to `bbox: null` + page-level highlight.

Related: the API's native `citations` feature is incompatible with structured output (returns
400), so citations come from the extraction schema, not the API feature.

Both are written up in `.spec/modules/raster.md` and `.spec/modules/extract.md`. The bbox path
should be proven on a real scanned PDF early in Phase 1 rather than discovered at an event.

## Next
1. `uv sync` and confirm `uv run ruff check .` / `uv run pyright` run clean on an empty tree.
2. **C0.2 — `contracts`.** Claude scaffolds `Field[T]`, `PolicySnapshot`, `Finding`, `Manifest`
   with `TODO(human)` recipes; Chris implements. This is the spine — everything imports it.
3. **C1.1 — corpus.** Start sourcing in parallel; it's the long pole.

Phase 4 (the LinkedIn conversations) does not wait for Phase 3, and per spec §14 it needs a
date or it doesn't happen.
