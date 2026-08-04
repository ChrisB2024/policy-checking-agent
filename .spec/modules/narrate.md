# narrate

**Owner:** Chris (the prompt is a scope-guard surface) · **Chunk:** C3.1 · **Spec:** §6, §11

## Purpose
Populate `Finding.narrative` — plain-language restatement of what changed. One `claude-opus-5`
call, run last, receiving the **ruled findings list only**. Never the raw documents.

## Surface
`src/policycheck/narrate/`
- `prompt.py` — versioned, recorded with each eval run.
- `run.py` — `narrate(findings) -> findings_with_narratives`.

## Prompt constraints (spec §6)
The model **may**:
- restate what changed in plain language,
- explain what a term means in general (e.g. what ACV means as a valuation basis).

The model **may not**:
- assess adequacy, recommend action, characterize risk, or say whether a change is acceptable,
- introduce findings not present in the input list,
- reorder or re-rank by its own judgment.

## Invariants
- **Every sentence traces to a finding object.** If the model produces a sentence that doesn't,
  the prompt is wrong — fix the prompt, don't filter the output.
- Structured output: the model returns `{finding_id: narrative}`, validated against the input
  finding IDs. An unknown ID, or a missing one, fails the run rather than being dropped.
- Ordering is fixed by the comparison engine. Narration returns a mapping, not a list, so it
  structurally cannot reorder.
- The model never sees the source PDFs. It receives findings — which already carry both sides'
  values and citations — and nothing else.

## Scope guards (spec §11)
Hard-banned from generated narrative text: "gap", "deficient", "inadequate", "exposed",
"at risk", "should", "recommend", "we suggest", and any claim about whether coverage would
respond to a loss. Assert this in a test over the narration output, not just in the prompt.

This isn't defensive boilerplate — the checker keeping the judgment call is the part they're
licensed and paid for, and saying so explicitly in the demo converts an objection into a
differentiator.

## Failure modes
- Narration that reads as advice. This is the single most likely way the product boundary
  leaks, and it leaks through tone, not through explicit recommendations.
- The model helpfully "clarifying" a finding by adding context it inferred — that's a new
  finding with no citation behind it.
- Running narration before the rules have finished. Narration is last, always.
