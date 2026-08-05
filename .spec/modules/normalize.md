# normalize

**Owner:** Chris · **Chunks:** C2.1 (forms), C2.2 (everything else) · **Spec:** §4.3

## Purpose
Convert extracted raw strings into canonical values. Runs after extraction, before comparison.
**This step produces most of the accuracy.**

## Surface
`src/policycheck/normalize/`
- `forms.py` — `canonicalize_form(raw) -> FormRef | None`, returning
  `{family: "CG0001", edition: "04/13"}`.
- `money.py` — `"$1,000,000"`, `"1,000,000"`, `"1000M"`, `"1 Mil"` → `1000000`;
  `"Included"` / `"Incl."` → `INCLUDED` sentinel; `"Excluded"` / `"None"` / `"N/A"` → `None`
  with `basis: excluded`.
- `dates.py` — `"04/01/2025"`, `"April 1, 2025"`, `"1 Apr 25"` → `date(2025, 4, 1)`.
- `enums.py` — `"Repl Cost"` / `"RC"` / `"Replacement Cost"` → `replacement_cost`;
  `"Spec"` / `"Special Form"` / `"Causes of Loss – Special"` → `special`.
- `address.py` — USPS-style component normalization, for location matching.

## Form family canonicalization
Spec §4.3: *"the single highest-leverage piece of code in the build."* Build it first in Phase 2
and test it against **every raw form number in the corpus** before writing the comparison
engine — the whole forms/exclusions/endorsements half of the taxonomy matches on `form_family`.

Real-world shapes to handle:
`CG 00 01 04 13` · `CG0001 (04/13)` · `CG 00 01 (Ed. 04 13)` · `CG0001 0413` ·
`CG 00 01 04 13 A` (carrier suffix) · `IL 00 17 11 98` · carrier-proprietary numbers with no
ISO shape at all.

The last case matters: a form the regex cannot parse must fall through to
`form_added_unclassified` (review_required), not be dropped and not be guessed at.

Real examples from `.spec/fixtures.md` (`cl-2742056`), in one document: `CG0001 (1-96)`,
`CG2136 (11/85)`, `CG 2160 (4-98)`, `CG2175 (12-02)`, `IL0017 (11-85)` — ISO, parseable —
alongside `TAPCO1998`, `CL150-EX`, `ALEA-GL-01 (01/04)`, `EZ-EXCL-01 (06/03)`,
`UTS-128g (10-94)`, `GU 276a (11-85)` — proprietary, MGA, and Lloyd's, which are not.
Note the edition formats vary within the same schedule line: `(1-96)`, `(11/85)`, `(4-98)`,
`(01/04)`. Same document, four separators.

That document also carries a *Commercial Property* Total Mold Exclusion on a policy with no
property coverage part — a form that is genuinely unclassifiable against the coverage it is
attached to, and the reason the fall-through has to exist.

## Invariants
- Normalization is **total and pure**: same input, same output, no I/O, no model calls.
- Every function returns `None` (or a typed failure) rather than a best guess. An unparseable
  form number is a `review_required` finding, not a silent drop.
- `INCLUDED` is a distinct sentinel — not `0`, not `None`. `$0` and "Included" mean opposite
  things and conflating them produces a phantom `limit_decrease`.
- `"Excluded"` → `None` **with** `basis: excluded`, so downstream can tell "excluded" apart
  from "we couldn't find it".
- Normalization runs before the dual-pass merge, so passes agree on values rather than on
  formatting.

## Testing
This is the one module worth a real test suite from day one, table-driven from the corpus.
`tests/normalize/test_forms.py` should assert against a fixture file listing every raw form
number found across all 20 pairs. When the corpus grows, the fixture grows.

## Failure modes
- A regex tuned on one carrier's dec page. Test across all 3–5 carriers before trusting it.
- Silently coercing `"1 Mil"` → `1` (parsed as a bare number, suffix dropped). A limit off by
  six orders of magnitude produces a confident, catastrophic finding.
- Two-digit years: `"1 Apr 25"` is 2025, not 1925. Pin a pivot and document it.
- Over-eager address normalization collapsing two genuinely different locations into one match
  (spec §5.1 matches locations by normalized address specifically because carriers renumber
  them between terms).
