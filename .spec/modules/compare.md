# compare

**Owner:** Chris · **Chunks:** C2.4 (matching), C2.5 (taxonomy + severity) · **Spec:** §5

## Purpose
Take two `PolicySnapshot`s and produce a list of `Finding`s. **Deterministic. No model calls
in this stage** (spec invariant 1 — materiality is decided by rules, never by a model).

## Surface
`src/policycheck/compare/`
- `matching.py` — pair up entities across the two sides before any comparison.
- `rules.py` — one function per finding type, each returning `Finding | None`.
- `engine.py` — run matching, run every rule, collect findings, count unchanged fields.
- `pc compare <prior.json> <renewal.json>` → findings JSON.

## Matching (spec §5.1)
| Entity | Match key | Unmatched |
|---|---|---|
| Coverage limits | Field path (fixed schema) | `not_found` on one side → finding |
| Forms | `form_family` | one side only → `form_added` / `form_removed` |
| Property locations | Normalized address, fallback to location number | `location_added` / `location_removed` |
| Scheduled AI parties | Normalized party name | `ai_party_added` / `ai_party_removed` |
| Exclusions | `form_family` | renewal only → `exclusion_added` |

Locations match by **address, not location number** — carriers renumber locations between
terms, and matching by number produces a phantom `location_removed` + `location_added` pair on
every renewal that reorders the schedule.

## Taxonomy and severity
The full table is spec §5.2 and is the conversation piece for Phase 4 — expect it to change
after account-manager conversations. Structure the rules so adding, removing, or re-severity-ing
a finding type is a one-place edit.

Two rules deserve their own note:
- **`form_edition_change` is `review_required`, never auto-classified.** Edition rollbacks
  frequently narrow coverage and advances frequently broaden it, but the direction is
  form-specific and cannot be inferred from the date. The finding says *"this changed, read
  it"* — which is the correct and defensible output.
- **`low_confidence_field` outranks everything.** If either side extracted a field at `low`,
  that field produces a `needs_review` finding and does not also produce a substantive finding
  claiming a direction of change.

## Invariants
- No model calls. If a rule needs judgment the rules can't express, it emits
  `review_required`, not a guess.
- Every finding carries both sides' `page` + `source_text` (spec §5.3) so a human can verify it
  in under 90 seconds. The one exception is a **derived** value — a premium delta, a
  structural observation like blanket-to-scheduled — which is computed rather than read and
  appears on no page. Those carry `derived_from`: the field paths they were computed from,
  each of which is itself cited. Invariant 7 survives one hop out, and the reader is never
  asked to take a number on trust. A derived side with an empty `derived_from` is a value
  with no provenance of either kind, and `FindingSide` rejects it.
- `narrative` is `None` when leaving this module.
- Decoy changes (premium, mailing address, agent of record, policy number, carrier name where
  coverage is unchanged) produce `informational` or `suppressed` findings — never adverse.
- **Count what didn't change.** The engine returns an `unchanged_verified` count alongside the
  findings. Spec §7.1: the difference between "the tool found four things" and "the tool checked
  ninety-one fields and four changed."

## Failure modes
- **A missed limit decrease is the failure mode that ends the product** (spec §8). Material
  recall is gated at 100%; a rule that returns `None` on an edge case is a silent miss.
- False positives are the second-order killer — a checker who finds two phantom findings stops
  trusting the other forty. Gate is ≤1 per pair.
- Comparing un-normalized values. `$1,000,000` vs `1000000` is not a limit change. The same
  trap with addresses: `address_change` fires on a difference in `Address.match_key`, never on
  the printed text, and the `FindingSide` carries the **normalized** rendering — `STE 200` vs
  `Suite 200` is not a change, and showing one is a false positive against a ≤1 per pair gate.
  The AM still sees what is printed, because `source_text` carries the verbatim line;
  normalized value plus verbatim snippet is how every other field works and an address is not
  an exception. An address that could not be normalized has `match_key = None`, which never
  matches anything including another `None` — so it produces no `address_change` at all and
  lands in `needs_review`, which is the right failure direction.
- Treating `not_found` on one side as a decrease to zero. That is a `needs_review`, not a
  `limit_decrease`.
