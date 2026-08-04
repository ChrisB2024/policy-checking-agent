# api

**Owner:** Claude · **Chunk:** C3.4 · **Spec:** §9, §10

## Purpose
FastAPI service that runs the pipeline for the demo UI. Synchronous run is fine at demo scale
(spec §10) — a 60-page pair takes ~40 seconds and the prospect watching it is the point.

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/runs` | Upload two PDFs, run the pipeline, return `run_id` |
| `GET` | `/runs/{id}` | Run status + stage (extracting / normalizing / comparing / narrating) |
| `GET` | `/runs/{id}/findings` | The findings list |
| `GET` | `/runs/{id}/report?format=internal\|client` | Rendered report |
| `GET` | `/runs/{id}/page/{side}/{page}.png` | Page raster for the split-pane view |
| `GET` | `/runs/{id}/citation/{finding_id}` | Both sides' page + bbox for the jump |

`side` is `prior` | `renewal`.

## Progress
Spec §9 calls for a progress indicator with **named stages**, not a spinner. Stream stage
transitions over SSE from `POST /runs` (or poll `GET /runs/{id}` — either is fine, SSE reads
better in the room). The named stages are the thing that makes 40 seconds feel like work rather
than a hang.

## Invariants
- **Demo mode retains nothing.** Uploaded PDFs are held in memory for the duration of the run
  and discarded. Page rasters go to a run-scoped cache that is deleted when the run ends —
  including on failure. This is stated to the prospect unprompted; the code has to actually do
  it.
- No auth, no multi-tenancy, no billing (spec §1 non-goals). Don't build them.
- The API orchestrates; it contains no comparison logic. Every stage it calls is independently
  runnable from `pc`.
- Runs offline. No calls to anything but the Anthropic API, and the two cached demo pairs work
  with no network at all.

## Event-day requirements (spec §9)
- Two pairs pre-run and cached for instant display — served from a fixture, not recomputed.
- The live path must work; someone will ask to see it actually run.
- Works on a phone hotspot. Do not depend on venue wifi.

## Failure modes
- A stage failing mid-run and leaving the raster cache on disk. Cleanup in a `finally`.
- Blocking the event loop on the synchronous PDF/model work — run it in a worker thread or
  it'll starve the progress stream, and the progress stream is half the demo.
- Adding ARQ before it's needed. Spec §10 defers it explicitly; add it only when batch
  processing 60-page documents actually demands it.
