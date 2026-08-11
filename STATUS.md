# STATUS

_Last rewritten: 2026-08-12_

## What works
- Toolchain green: `ruff check`, `ruff format`, `pyright` (0 errors), `pytest` 97 passing.
- **C0.1 scaffolding** — `claude.md`, `README.md`, `.spec/plan.md`, 13 module specs.
- **C1.1 corpus tooling** — `pc corpus search/fetch/screen/add/status/quota`. On-disk request
  ledger enforces the real CourtListener budget (5/min, 50/hr, 125/day), records *before* the
  request so a failure still counts, and fails closed on a corrupt ledger.
- **C1.2 `raster`** — `page_image` (content-addressed disk cache), `page_size`, `page_count`,
  `clear_cache`, and `find_text`, the `source_text → bbox` bridge. 18 tests over reportlab
  fixtures drawn at known coordinates.
- **C0.2 `contracts` — complete.** No `TODO(human)` in any of the five files, and 97 tests
  under `tests/`. `Field[T]`, the `INCLUDED` sentinel, the citation validator, `not_found()`,
  `needs_review`, `is_cited`, `agreement()`; every section of spec §4.2; and `field_at`,
  which resolves every one of spec §3.2's manifest paths — by position *and* by match key,
  with `Unresolved` separating a broken fixture from an absent row from an ambiguous one.
  `finding.py` carries `Finding`, `FindingSide`, `Unit`, `NarrationInput` / `NarrationSide`,
  and `ComparisonResult.sections()`; `manifest.py` parses spec §3.2's own example.
- **`config.py`** — `.env` via pydantic-settings, `SecretStr` credentials, `require_*` helpers
  that check the secret's *value* so a blank key fails with a useful message rather than a 401.

## What's half-built
Nothing in `contracts`. The next chunk (C1.3 `pairgen`) has not started.

## What's blocked on Chris
- **C1.1 corpus sourcing** — still the critical path, still at zero usable base documents.
  `cl-2742056.pdf` is downloaded but ruled out as a package fixture (monoline surplus-lines
  CGL, no property part); retained as a GL-only pair candidate and an extraction fixture
  (`.spec/fixtures.md`).
- **Phase 0 user research.** `.spec/policy-check-framework.md` names this as the project's
  largest open risk: two blanks in the pain sentence are assumptions, not observations. Its
  recommendation is three account-manager screen shares *before* C2 extraction starts.
  Contracts work is unaffected — the schema is what you'd bring to the screen share.

## Decisions made this session
- **`Unresolved` enum replaces a bare `None`** from `field_at`. `NO_SUCH_PATH` (broken
  fixture), `NO_SUCH_ROW` (document legitimately lacks it — what a manifest asserting
  `to: null` expects), `AMBIGUOUS` (document names one identity twice). Collapsing them makes
  the eval harness unable to tell a broken fixture from a passing one.
- **Collection members are addressed by match key, not position.** `forms_schedule.CG0001.edition`
  resolves by `form_family` — the same key spec §5.1 pairs forms on, because order differs
  between documents. Each element model declares it once as a `_match_key` ClassVar, read by
  both `compare` and `field_at`, and it stays out of `model_fields` so it never reaches the
  extraction schema.
- **`AMBIGUOUS` on duplicate keys rather than first-match-wins**, following `raster.find_text`:
  a wrong row is worse than no row. Not an edge case — `.spec/fixtures.md` records a document
  whose two schedules each omit forms the other lists.
- **A row miss is only `NO_SUCH_ROW` if the rest of the path could have resolved.**
  `_addressable` walks the remaining segments against `model_fields` rather than values, so a
  path that is broken twice over (`forms_schedule.CG9999.nonsense`) reports `NO_SUCH_PATH`
  instead of reading as a passing absence. That is the shape stale fixtures take after a form
  family is renamed or the canonicalizer's output drifts — they would all go quietly green.
  Wired into positional addressing too, since `property.locations[0].valuation` is a §3.2 path
  and the two modes must not disagree about the same absent row. Lists whose members carry no
  identity (`dba: list[Field[str]]`) have no type to check a tail against and report the
  absence unqualified.
- **`NarrationInput` is the narrator's only input type.** An uploaded PDF is untrusted input to
  a language model and `FindingSide.source_text` is a verbatim slice of one, so `narrate()` is
  typed to reject `Finding` outright. The limit is written down in `.spec/modules/narrate.md`:
  normalized values can still be document-derived strings, so this narrows exposure rather than
  eliminating it — the output contract is what contains an injection.
- **Findings about the run are their own category.** `low_confidence_field`,
  `field_not_found`, `ambiguous_path`, `normalizer_version_mismatch` describe what the tool
  could and could not do, not the policy. `TOOL_FINDINGS` declares the set once; `report`
  groups them apart and `narrate` skips them. Now a second table in §5.2.
- **Tool findings and suppressed findings are not narrated.** §7.1 gives neither a place where
  a narrative renders — the needs-review section is a fixed heading and a count, and suppressed
  has no section at all. Paying a model to phrase them buys prose nothing displays, and for
  tool findings it risks copy about the tool's own confusion reaching a client. `for_narration`
  returns `None` for both, so the rule lives beside the projection rather than in `narrate`.
- **Enum values are an interface.** Manifests address finding types by string, so members match
  §5.2 exactly (`limit_decrease`, not `limit_decreased`). Four had drifted and were renamed.
- **`FindingSide.value` is a narrow union, and absence is its own field.** Findings round-trip
  through JSON on every path out (persistence, API, eval harness), and JSON has fewer types
  than Python. `Decimal` and `date` had no producer and were rewriting real values on reload —
  a ZIP lost its leading zero, a policy number became a number. `Unresolved` could not survive
  a union containing `str` at all, so it moved to `absent`.
- **A derived value carries `derived_from`, not a boolean.** A premium delta appears on no page
  and cannot cite one, but it can name the paths it was computed from, each of which is cited —
  invariant 7 survives one hop out instead of being waived. A bare `derived: bool` switched the
  citation requirement off and told a reviewer nothing.
- **`Finding.confidence` is display-only** — the weaker of the two source fields, set by
  `compare`, no rule branching on it. Nearly redundant, since a field low on either side
  becomes `low_confidence_field` and never claims a direction; kept because §5.3 names it and
  `not_found` gives it a third state. Per-side confidence is deliberately *not* on
  `FindingSide` — that's a report-design question for after the screen shares.
- **Suppressed findings are built and filtered at render**, not skipped. A decoy expecting
  `suppressed` must be emitted to be scored, or the harness cannot tell "correctly suppressed"
  from "never noticed" — and that is a 100% gate (spec §8). It is also the diligence record an
  E&O defence rests on. `sections()` returns five groups; `SUPPRESSED` appears in none and is
  reachable via `ComparisonResult.suppressed`.
- **`extra="forbid"` on every contracts model.** Pydantic silently drops an unknown key, so a
  field renamed in code turns every persisted record and hand-authored manifest into one that
  loads with a default and no complaint. A typo'd `feild_path` now fails at construction.
- **`address_change` fires on `match_key`, and the side carries the normalized rendering.**
  `STE 200` vs `Suite 200` is not a change, and rendering `raw` would show one — a false
  positive against a ≤1 per pair gate. `source_text` still carries the printed line.
- Earlier and unchanged: Python 3.13 + uv with a committed lockfile, Pydantic v2, ruff +
  pyright, SQLAlchemy 2.0 async + Alembic, pikepdf/reportlab/Pillow for `pairgen`,
  `claude-opus-5` for extraction and narration. Deferred per spec §10: ARQ, pgvector.

## Spec edits done
The spec and the models had drifted apart; the spec is now the single source and a test
enforces it (`tests/contracts/test_taxonomy.py` parses §5.2 rather than restating it).

1. **§3.2's example `field_path`s now resolve.** `gl.each_occurrence_limit` →
   `general_liability.each_occurrence`, `forms.CG0001.edition` → `forms_schedule.CG0001.edition`.
   §4.2 is the schema authority and §3.2 was loose.
2. **`endorsements.CG2010` → `risk_transfer.additional_insured.basis`** (`blanket` → `none`).
   §5.2 defines `endorsement_removed` on AI/WOS/P&NC, so the assertion is about
   `risk_transfer`, and pointing it there makes it a real stored `Field`.
3. **§5.1's five unmapped names resolved.** Three were never finding types — a form present on
   one side is *classified* by what it is (`exclusion_added`, `endorsement_removed`, else
   `form_added_unclassified`), so §5.1 now says that. Two were genuinely missing and are now
   types with severities: `ai_party_removed` (material_adverse — a scheduled party losing AI
   status is exactly the §5.2 kind of harm) and `ai_party_added` (informational). Same for
   `location_added` (informational), which §5.1 named and §5.2 omitted.
4. **The 8 additions are recorded in §5.2**, including a second table for findings about the
   run rather than the policy. §5.2 now has 37 rows and `FindingType` has 37 members, with no
   drift in either direction.

## Open problems
- **`Address` still asks the extractor for `match_key`.** All seven fields are in the JSON
  schema's `required` list, including the one `normalize` owns — the same bug class as
  `confidence` on `Field`, already fixed there. Also needs an explicit *unnormalized* marker
  rather than a bare null, per the framework doc's Phase 2 note.
- **`WaiverOfSubrogation.basis` is typed `AIBasis`.** Correct vocabulary (spec gives waivers the
  same `blanket|scheduled|none`), wrong name. Rename to something shared.
- **`normalizer_version` doesn't exist.** The framework doc asserts it's already on
  `DocumentMeta`; it isn't. The field is the easy half — the point is the comparator refusing
  to compare snapshots normalized under different versions.
- **Bounding boxes (unchanged).** The Claude API returns none, so `find_text` resolves
  `source_text` against the page text layer. Settled empirically: text at a known position
  resolves to within a point; an ambiguous needle returns `None`; a real scanned RECAP page has
  66 raw chars and no text layer. For the ≥2 image-only pairs spec §3.2 requires, page-level
  highlighting is the guaranteed path, not a fallback. The API's native `citations` feature is
  incompatible with structured output (400), so citations come from the schema.

## Next
1. **C1.1 corpus.** The long pole, still at zero usable base documents, and now the only thing
   between here and C1.3 — `pairgen` needs real PDFs to patch, and `extract` needs pairs.
2. **Three screen shares before C2 extraction**, per `.spec/policy-check-framework.md`. The
   schema is finished, which is what you'd bring to one.
3. **C1.3 `pairgen`** (Claude's to write, per `.spec/plan.md`) once documents exist.

Schema freeze: the extractor doesn't exist yet, so `contracts` is still cheap to change. After
C1.4 a change means re-running the full eval suite and noting it here.
