# evals

**Owner:** Claude writes the runner; Chris writes the metrics · **Chunk:** C2.6 · **Spec:** §8

## Purpose
Score the pipeline against the manifest set. Every extraction or prompt change re-runs the full
suite. **The eval set is authored before the extractor is written** (spec invariant 4) — the
manifests from C1.3 are the ground truth.

## Metrics and gates

| Metric | Definition | Gate |
|---|---|---|
| Material recall | Injected `material_adverse` changes detected | **100%** |
| Overall recall | All injected changes detected at any severity | ≥ 95% |
| Severity accuracy | Detected findings assigned expected severity | ≥ 95% |
| False positive rate | Findings not in manifest and not decoy-explained | ≤ 1 per pair |
| Decoy suppression | Decoy changes not classified adverse | 100% |
| Citation page accuracy | Cited page contains the cited value | 100% |
| Clean-pair precision | Zero-change pairs producing zero material findings | 100% |

**Material recall at 100% is non-negotiable.** A missed limit decrease is the failure mode that
ends the product. False positives are the second-order killer — a checker who finds two phantom
findings stops trusting the other forty.

Worth adding beyond §8, because it gates the demo's best moment:
- **bbox resolution rate** — fraction of findings whose `source_text` resolved to a bbox on a
  text-layer page. Not a pass/fail gate, but a regression here means click-to-citation quietly
  stopped working.

## Surface
`src/policycheck/evals/`
- `runner.py` — for each pair: extract both sides → normalize → compare → score against
  manifest.
- `metrics.py` — one function per metric above. **Chris writes these**; the definitions encode
  what "detected" means, which is a judgment call (does a finding of the right type but wrong
  severity count as detected for recall? — yes, that's what severity accuracy is for).
- `scorecard.py` — writes `evals/runs/<timestamp>.json` plus a diff against the previous run.
- `pc eval run [--pairs pkg-001,pkg-004]`
- `pc eval diff <run-a> <run-b>`

## Scorecard contents
Per run: timestamp, git sha, extraction prompt version, narration prompt version, model id,
per-pair results, aggregate metrics, and pass/fail against each gate. Prompt versions matter —
without them a regression is unattributable.

The diff against the previous run is the point. A run that only prints absolute numbers makes
regressions invisible; the diff makes them the first thing you see.

## Invariants
- The harness compares against the manifest, never against a previous run's output. Snapshot
  testing an extractor makes yesterday's bugs today's expected behavior.
- Decoys count. A pair where every injected change is found but a decoy is flagged adverse is a
  **failed** pair, not a partially passing one.
- The runner never mutates manifests.

## Failure modes
- Running evals on a subset "for speed" and shipping on the subset's numbers. Full suite or it
  didn't happen.
- Recall computed over findings the pipeline produced rather than changes the manifest injected
  — that measures precision and calls it recall.
- Letting a gate slip "temporarily." The gates are the product's credibility claim.
