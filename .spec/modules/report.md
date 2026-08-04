# report

**Owner:** Chris (the copy is the product) · **Chunks:** C3.2, C3.3 · **Spec:** §7, §11

## Purpose
Two artifacts per run, for two different audiences.

## 7.1 — Internal findings report
**Audience:** the account manager / checker. **Purpose:** verification.

Sections, in this order:
```
NEEDS REVIEW — LOW CONFIDENCE EXTRACTION   [n]
MATERIAL CHANGES — COVERAGE REDUCED        [n]
REVIEW REQUIRED                            [n]
MATERIAL CHANGES — COVERAGE BROADENED      [n]
INFORMATIONAL                              [n]
UNCHANGED — VERIFIED                       [n]   (collapsed by default)
```

`NEEDS REVIEW` comes first deliberately — visible doubt on 5% of fields beats confident error
on 2% (spec invariant 3), and a checker needs to know what the tool didn't handle before they
read what it did.

**The `UNCHANGED — VERIFIED` count matters more than it looks.** It's the difference between
"the tool found four things" and "the tool checked ninety-one fields and four changed." Do not
drop it because it's not a finding.

Every line carries both sides' page numbers and a link to the citation view.

## 7.2 — Client-facing renewal difference summary
**Audience:** the insured. **Purpose:** the broker forwards it without editing.

One page. No jargon without a plain-language gloss. No branding from the tool. Sections:
1. Policy identification and term
2. What changed in your coverage — plain language, **adverse changes first**
3. What stayed the same — summarized, not enumerated
4. Premium
5. Items your broker is reviewing — the `review_required` set, framed as *in progress*, not
   *unresolved*

### Copy invariants
- Never uses "gap", "deficient", "inadequate", "exposed", or "at risk".
- Never recommends an action.
- Never states or implies whether coverage would respond to a hypothetical claim.
- Attributes nothing to the tool — it reads as the broker's document.

Assert these in a test over rendered output. They're easier to violate in a template than in a
prompt.

## Surface
`src/policycheck/report/`
- `internal.py` — terminal + HTML renderers.
- `client.py` — one-page HTML, print stylesheet, PDF via the browser print dialog (no extra
  dependency).
- `pc report <run.json> --internal | --client`

## Invariants
- Reports render from `Finding` objects only. No re-derivation, no recomputation, no second
  opinion on severity.
- A finding with `bbox: None` still renders with its page citation. Missing bbox degrades the
  jump-to-highlight, not the citation.

## Failure modes
- The client summary drifting into advice. It describes; it never interprets (spec invariant 6).
- Enumerating "what stayed the same" — it's a summary line, not a 91-row table. The detail
  belongs in the internal report.
- Tool branding on the client artifact. **This artifact is the thing to print and carry. It is
  more persuasive than the software** — and it only works if it reads as the broker's own.
