# contracts

**Owner:** Chris · **Chunk:** C0.2 · **Spec:** §4.1, §4.2, §5.3, §3.2

## Purpose
Pydantic v2 models for every object that crosses a module boundary. Nothing in the pipeline
passes raw dicts or bare values. This module imports nothing from the rest of the codebase.

## Surface
`src/policycheck/contracts/`
- `field.py` — `Field[T]`, the universal envelope: `value`, `raw`, `page`, `bbox`,
  `source_text`, `confidence`, `extraction_passes_agreed`.
- `snapshot.py` — `PolicySnapshot` and its sub-models (identity, general_liability, property,
  forms_schedule, risk_transfer, exclusions, premium) exactly as laid out in spec §4.2.
- `finding.py` — `Finding`, `FindingType`, `Severity`.
- `manifest.py` — `Manifest`, `InjectedChange`, `DecoyChange` (spec §3.2 JSON shape).
- `enums.py` — `Confidence`, `ValuationBasis`, `CausesOfLoss`, `AggregateBasis`, `AIBasis`,
  `AIScope`, `DeductibleBasis`, `BusinessIncomeBasis`, `AuditBasis`, `PageClassification`.

## Invariants
- `Field[T]` is generic and used for **every** extracted value. A bare `int` on a snapshot
  model is a bug.
- `confidence` ∈ `high | low | not_found`. `low` and `not_found` both route to `needs_review`
  downstream — the comparison engine must never silently treat them as a value.
- `INCLUDED` is a distinct sentinel, not `0` and not `None` (spec §4.3). Model it as a typed
  sentinel the type checker can see, not a magic number.
- `bbox` is `list[float] | None` — nullable, because scanned pages can't resolve one.
  `page` and `source_text` are **not** nullable when `value is not None`.
- The citation invariant is gated on what the field **asserts**, not on `confidence`. Two
  shapes assert something and must cite: a present `value`, and `basis = excluded` — "the
  document affirmatively shows this coverage removed" is a claim `compare` can turn into a
  substantive finding, so it needs a page to point at. `basis = absent` claims nothing and is
  exempt; it is also the shape the extractor returns when it cannot find a value — no value,
  no citation, and `confidence` left at its `LOW` default because the model is told not to
  set it.
- `agreement()` compares the pair `(value, basis)`. Two fields that both have `value = None`
  are not necessarily agreeing: one `absent` and one `excluded` is a real disagreement about
  what the document says, and it routes to `low`.
- `confidence` and `extraction_passes_agreed` default to `LOW` / `False` rather than being
  required, so the extraction schema does not demand the two fields its own descriptions tell
  the model not to set. An un-merged field has not earned confidence.
- `Finding.narrative` is the only model-generated field on a finding and starts `None`.
- Models are frozen (`model_config = ConfigDict(frozen=True)`). The pipeline builds new
  objects rather than mutating.

## Failure modes
- A field added to `PolicySnapshot` without a matching `field_path` string used by the
  manifest and comparison engine → the eval harness silently never checks it. Keep field
  paths derivable from the model, not hand-written in two places.
- Loosening `bbox` or `page` to optional everywhere to make the type checker quiet — that
  defeats invariant 2 (no uncited claims).

## Freeze rule
Spec §13 Phase 1 exit says the schema is stable before the extractor is written. After C1.4,
a schema change means re-running the full eval suite and noting it in `STATUS.md`.
