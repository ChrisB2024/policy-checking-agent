# persistence

**Owner:** Claude · **Chunk:** C3.4 · **Spec:** §10, invariant 5

## Purpose
Postgres storage for runs, findings, and eval results. **Not** for documents — demo mode
retains nothing (spec invariant 5), and that statement is delivered to prospects unprompted.

## What is stored
| Table | Contents |
|---|---|
| `runs` | run id, created_at, model id, prompt versions, git sha, timings, token usage, status |
| `findings` | the `Finding` objects for a run, as JSONB + a few queryable columns (type, severity, field_path) |
| `snapshots` | the two `PolicySnapshot`s for a run, as JSONB — the *extracted values*, not the source PDFs |
| `eval_runs` | scorecard per harness run, as JSONB + queryable gate pass/fail columns |

## What is never stored
- Source PDF bytes.
- Page rasters (those live in the run-scoped on-disk cache and are cleared with the run).
- Anything from which a document could be reconstructed.

`snapshots` stores extracted field values and verbatim `source_text` snippets. That is a
deliberate line: it's what makes a run reproducible and re-renderable without the document.
If it turns out even that is too much for the retention claim, drop `snapshots` to
demo-mode-off only — but decide it explicitly and record it in `STATUS.md` rather than
letting it drift.

## Approach
- SQLAlchemy 2.0 async models + Alembic migrations. `asyncpg` driver.
- JSONB for the object payloads, real columns only for what's actually queried. The schema is
  still moving; a fully normalized findings table would need a migration on every taxonomy
  change, and the taxonomy is explicitly expected to change in Phase 4.
- Railway for the hosted instance; local Postgres 16 for development.

## Surface
`src/policycheck/persistence/`
- `models.py` — SQLAlchemy models.
- `repo.py` — the handful of queries the API actually needs. No generic ORM surface.
- `migrations/` — Alembic.

## Invariants
- `uv run alembic check` stays clean after any model change.
- Demo mode is the default. A run in demo mode writes findings and snapshots but never touches
  a document on disk beyond the run-scoped raster cache, and that cache is deleted when the run
  completes or fails.
- The pipeline does not depend on the database. `pc extract` / `pc compare` / `pc eval` all run
  with no Postgres available — persistence is for the API and the demo cache, not for the
  engine.

## Failure modes
- Storage creeping into the engine, so the eval harness needs a database to run.
- Retaining rasters "just for the cache" past the run and quietly falsifying the retention
  statement. Expect senior prospects to ask about retention first.
