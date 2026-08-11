# STATUS

_Last rewritten: 2026-08-11_

## What works
- Toolchain green: `ruff check`, `ruff format`, `pyright` (0 errors), `pytest` 18 passing.
- **C0.1 scaffolding** — `claude.md`, `README.md`, `.spec/plan.md`, 13 module specs.
- **C1.1 corpus tooling** — `pc corpus search/fetch/screen/add/status/quota`. On-disk request
  ledger enforces the real CourtListener budget (5/min, 50/hr, 125/day), records *before* the
  request so a failure still counts, and fails closed on a corrupt ledger.
- **C1.2 `raster`** — `page_image` (content-addressed disk cache), `page_size`, `page_count`,
  `clear_cache`, and `find_text`, the `source_text → bbox` bridge. 18 tests over reportlab
  fixtures drawn at known coordinates.
- **`contracts/enums.py`**, **`contracts/field.py`**, **`contracts/snapshot.py`** — done, no
  TODOs. `Field[T]`, the `INCLUDED` sentinel, the citation validator, `not_found()`,
  `needs_review`, `is_cited`, `agreement()`; every section of spec §4.2; and `field_at`,
  which resolves all six of spec §3.2's manifest paths once they're corrected to §4.2's
  names — by position *and* by match key, with `Unresolved` separating a broken fixture from
  an absent row from an ambiguous one.
- **`config.py`** — `.env` via pydantic-settings, `SecretStr` credentials, `require_*` helpers
  that check the secret's *value* so a blank key fails with a useful message rather than a 401.

## What's half-built
**C0.2 `contracts`** — two files left, 8 TODOs.

| File | State |
|---|---|
| `enums.py` | Done. |
| `field.py` | Done. |
| `snapshot.py` | Done. |
| `finding.py` | `Severity`, `FindingType` (34 members), `FindingSide` done. **5 TODOs:** `Finding` fields, `for_narration()`, `NarrationInput` fields, `FindingSide.display()`, report section grouping. |
| `manifest.py` | Scaffold. **3 TODOs:** `from`/`to` aliasing (`from` is a keyword), `material_changes`. |

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
- **`FindingType` carries 8 members beyond spec §5.2.** Two favorable counterparts the spec
  never listed despite having a `favorable` severity (`retro_date_receded`,
  `notice_of_cancellation_increased`); two neutral (`sublimit_added`,
  `deductible_basis_changed`, `endorsement_added`); and four *about the tool, not the policy*
  (`low_confidence_field`, `field_not_found`, `ambiguous_path`, `normalizer_version_mismatch`).
  That last group is a category §5.2 doesn't have, and `report` should group it separately — an
  AM reading "normalizer version mismatch" is being told something about the run, not about
  their client's coverage.
- **Enum values are an interface.** Manifests address finding types by string, so members match
  §5.2 exactly (`limit_decrease`, not `limit_decreased`). Four had drifted and were renamed.
- Earlier and unchanged: Python 3.13 + uv with a committed lockfile, Pydantic v2, ruff +
  pyright, SQLAlchemy 2.0 async + Alembic, pikepdf/reportlab/Pillow for `pairgen`,
  `claude-opus-5` for extraction and narration. Deferred per spec §10: ARQ, pgvector.

## Spec edits owed
Found by diffing the spec against the models. None are §2 invariants; all are §3.2/§5.1/§5.2
detail that the code has since outgrown.

1. **§3.2's example `field_path`s don't resolve.** §4.2 (the schema authority) says
   `general_liability.each_occurrence` and `forms_schedule`; §3.2's manifest says
   `gl.each_occurrence_limit` and `forms`. Fix §3.2 — three of its six paths are wrong.
2. **`endorsements.CG2010`** should be `risk_transfer.additional_insured.present`. §5.2 defines
   `endorsement_removed` as "AI, WOS, or P&NC present prior, absent now", so the assertion is
   about `risk_transfer`, and pointing it there makes it a real stored `Field`.
3. **§5.1 names five types §5.2 gives no severity to:** `form_added`, `form_removed`,
   `location_added`, `ai_party_added`, `ai_party_removed`. `compare` is told to emit them and
   `FindingType` has no members for them. Resolve before writing `compare/rules.py`.
4. **Record the 8 `FindingType` additions** in §5.2.

## Open problems
- **`derived` on `FindingSide` contradicts `compare.md`.** A derived value (a premium delta, a
  structural observation like blanket-to-scheduled) carries no page and no snippet, but
  `compare.md` says every finding carries both sides' `page` + `source_text` so a human can
  verify in 90 seconds. Worth considering `derived_from: tuple[str, ...]` of field paths, which
  keeps invariant 7 intact transitively and makes the flag self-documenting.
- **`Address` still asks the extractor for `match_key`.** All seven fields are in the JSON
  schema's `required` list, including the one `normalize` owns — the same bug class as
  `confidence` on `Field`, already fixed there. Also needs an explicit *unnormalized* marker
  rather than a bare null, per the framework doc's Phase 2 note.
- **`WaiverOfSubrogation.basis` is typed `AIBasis`.** Correct vocabulary (spec gives waivers the
  same `blanket|scheduled|none`), wrong name. Rename to something shared.
- **`normalizer_version` doesn't exist.** The framework doc asserts it's already on
  `DocumentMeta`; it isn't. The field is the easy half — the point is the comparator refusing
  to compare snapshots normalized under different versions.
- **`contracts` has no tests.** `tests/contracts/` is an empty package. `agreement()` is the
  rule the entire dual-pass cost is justified by and depends on `IncludedSentinel.__eq__`
  three hundred lines away. A test parsing §5.2 out of `spec.md` and asserting `FindingType`
  covers it would have caught the drift above mechanically.
- **Bounding boxes (unchanged).** The Claude API returns none, so `find_text` resolves
  `source_text` against the page text layer. Settled empirically: text at a known position
  resolves to within a point; an ambiguous needle returns `None`; a real scanned RECAP page has
  66 raw chars and no text layer. For the ≥2 image-only pairs spec §3.2 requires, page-level
  highlighting is the guaranteed path, not a fallback. The API's native `citations` feature is
  incompatible with structured output (400), so citations come from the schema.

## Next
1. **Chris — `finding.py` and `manifest.py`.** 8 TODOs, then C0.2 closes. Three decisions are
   tangled in `finding.py` and want settling before `Finding` gets its fields: whether
   `derived` carries `derived_from` paths, whether `Unresolved` is the right vocabulary for
   side-absence, and what `NarrationInput` withholds.
2. **Spec edits owed**, above. Item 3 blocks `compare/rules.py`.
3. **C1.1 corpus, in parallel.** The long pole; nothing downstream can be validated without it.
4. **Three screen shares before C2 extraction**, per the framework doc.

Finishing contracts does not unblock much on its own — `pairgen` and `extract` both need real
documents, and there are none. Of the four above, the corpus is the one that has been at zero
longest and gates the most.

Schema freeze: once the extractor exists (C1.4), a change to `contracts` means re-running the
full eval suite and noting it here.
