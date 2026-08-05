# extract

**Owner:** Claude scaffolds the API plumbing; Chris writes the prompt and the merge
**Chunks:** C1.4 (v0), C2.3 (v1) · **Spec:** §4.1, §10

## Purpose
Turn a PDF into a `PolicySnapshot`. This is the only place in the pipeline that sends a
document to a model.

## Approach
- `claude-opus-5`, PDF as a base64 `document` content block. No separate OCR layer — the model
  reads scanned pages directly.
- Structured output: the `PolicySnapshot` Pydantic model → JSON schema → `output_config.format`,
  via `client.messages.parse()`.
- **Dual pass** (spec §10): run the document through extraction twice independently, compare
  field by field, mark disagreements `low` confidence. ~2× cost on the cheapest part of the
  pipeline, and it is what makes the `needs_review` bucket honest.
- Prompt-cache the document block across the two passes — same prefix, so the second pass reads
  it back at ~0.1× input cost.
- Large documents: 60-page policies are near the practical limit for one call. If a document
  exceeds it, split by page classification (dec page / forms schedule / endorsements) and merge
  — do **not** truncate.

## The citation constraint
The API's native `citations` feature is **incompatible with `output_config.format`** (returns
400). So citations do not come from the API — they come from the schema. Every `Field[T]` the
model fills must carry:
- `page` — 1-indexed,
- `source_text` — **verbatim** from the page, not paraphrased,
- `raw` — the value exactly as printed.

`raster.find_text` then resolves `source_text` → `bbox`. A paraphrased snippet produces a
`bbox: None`, so verbatim quoting is a hard prompt requirement, not a nicety.

## Surface
`src/policycheck/extract/`
- `prompt.py` — system prompt + the per-section instructions. Version it; the eval harness
  records which prompt version produced a run.
- `client.py` — Anthropic call, retries, prompt caching, token accounting.
- `passes.py` — run N passes, merge field by field.
- `merge.py` — the confidence rule.
- `pc extract <pdf> [--passes 2]` → prints a `PolicySnapshot` as JSON.

## Merge rule
| Pass A | Pass B | Result |
|---|---|---|
| same normalized value | same | `high`, `extraction_passes_agreed: true` |
| value | different value | `low`, keep pass A's value + citation, `agreed: false` |
| value | `not_found` | `low` |
| `not_found` | `not_found` | `not_found` |

Comparison is on the **normalized** value (`normalize` runs before merge), so `$1,000,000` and
`1,000,000` agree. Comparing raw strings would flood the `low` bucket with formatting noise.

## Invariants
- The model extracts and cites. It never decides whether a change matters (spec invariant 1)
  and never sees the other side of the comparison.
- No field appears in output without `page` + `source_text` (spec invariant 2). A field the
  model can't cite is `not_found`, not a guess.
- Uncertainty surfaces as `needs_review`, never as a guess (spec invariant 3).
- Demo mode retains nothing: documents are processed in memory and discarded (spec invariant 5).
  Nothing here writes a PDF to disk outside the run-scoped raster cache.

## Layouts the extractor must survive
Real documents, not hypotheticals — see `.spec/fixtures.md` for the source case.

- **Forms schedules at more than one document level.** A cover note's "Special Conditions"
  box and a coverage part's "Item 3. Forms and Endorsements" can both exist and disagree, each
  listing forms the other omits. Find every schedule and union them; an extractor that finds
  one and stops is wrong in both directions.
- **Limits restated further in.** A front dec page may show one blended limit where the
  supplemental declarations break out all six. Reading only the front page yields five
  spurious `not_found`s, each of which becomes a phantom finding at renewal.
- **Documents that contradict themselves.** The same field can appear twice with different
  values, both verbatim and both citable. The dual-pass merge catches *extraction*
  disagreement; it does not catch *document* disagreement. A field with two conflicting
  in-document sources is `low` confidence with both citations retained — never a silent pick.
- **Values that do not reconcile.** Rate × exposure need not equal premium (minimum premium
  governs, flagged `MP`). Premium is extracted, never derived or validated arithmetically.

## Failure modes
- **Prompting the model to be confident.** The whole `needs_review` design depends on it
  reporting doubt. Any prompt language that discourages `not_found` breaks invariant 3.
- Paraphrased `source_text` → every bbox null → the demo's best moment (click-to-citation)
  stops working. Check the bbox-null rate as a first-class extraction metric, not just
  field accuracy.
- Two passes that aren't independent (same cache, same seed-ish conditions) agreeing on the
  same wrong answer. Vary nothing about the input; the value is in sampling variance.
- Silently downgrading the model to save cost. Extraction accuracy is the product.
