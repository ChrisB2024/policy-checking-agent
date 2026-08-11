"""Finding — the output of the comparison engine.

Findings are produced by deterministic rules only. The model never rules on whether a
change matters (spec invariant 1); it only fills `narrative`, last, in a separate pass.
"""

from datetime import date
from enum import StrEnum
from typing import Literal, assert_never

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic import Field as PydanticField

from policycheck.contracts.enums import Confidence
from policycheck.contracts.field import BBox, IncludedSentinel
from policycheck.contracts.snapshot import Unresolved


class Severity(StrEnum):
    NEEDS_REVIEW = "needs_review"
    MATERIAL_ADVERSE = "material_adverse"
    REVIEW_REQUIRED = "review_required"
    FAVORABLE = "favorable"
    INFORMATIONAL = "informational"
    SUPPRESSED = "suppressed"


class FindingType(StrEnum):
    """The taxonomy from spec §5.2.

    Expect this to change after Phase 4 — the taxonomy is the conversation piece, and a
    working account manager will have items that aren't here. Keep the mapping from type
    to default severity in ONE place (`compare/rules.py`) so a revision is a single edit.

    **The values are an interface, not labels.** Manifests address them by string
    (`expected_finding_type` in spec §3.2), so a member whose value drifts from §5.2 is a
    fixture that silently never matches. Names read as nouns — `limit_decrease`, not
    `limit_decreased` — because that is how §5.2 writes them.

    Two carry design weight:
      - `FORM_EDITION_CHANGE` is review_required and is NEVER auto-classified adverse or
        favorable. Direction is form-specific and cannot be inferred from the date.
      - `LOW_CONFIDENCE_FIELD` is needs_review and OUTRANKS everything. A field extracted at
        `low` on either side does not also produce a finding claiming a direction.
    """

    # --- liability limits and retentions ---
    LIMIT_DECREASE = "limit_decrease"
    LIMIT_INCREASE = "limit_increase"
    SUBLIMIT_ADDED = "sublimit_added"
    AGGREGATE_BASIS_NARROWED = "aggregate_basis_narrowed"
    SIR_INTRODUCED = "sir_introduced"
    DEDUCTIBLE_INCREASE = "deductible_increase"
    DEDUCTIBLE_DECREASE = "deductible_decrease"
    DEDUCTIBLE_BASIS_CHANGED = "deductible_basis_changed"  # per-occurrence -> per-claim

    # --- property ---
    VALUATION_DOWNGRADE = "valuation_downgrade"
    CAUSES_OF_LOSS_NARROWED = "causes_of_loss_narrowed"
    COINSURANCE_INCREASE = "coinsurance_increase"
    BLANKET_TO_SCHEDULED = "blanket_to_scheduled"
    BUSINESS_INCOME_REDUCED = "business_income_reduced"
    LOCATION_REMOVED = "location_removed"

    # --- forms, endorsements, exclusions ---
    FORM_EDITION_CHANGE = "form_edition_change"
    FORM_ADDED_UNCLASSIFIED = "form_added_unclassified"
    ENDORSEMENT_ADDED = "endorsement_added"
    ENDORSEMENT_REMOVED = "endorsement_removed"
    EXCLUSION_ADDED = "exclusion_added"
    EXCLUSION_REMOVED = "exclusion_removed"

    # --- risk transfer ---
    AI_BASIS_NARROWED = "ai_basis_narrowed"
    AI_SCOPE_NARROWED = "ai_scope_narrowed"

    # --- dates, triggers, notice ---
    RETRO_DATE_ADVANCED = "retro_date_advanced"
    RETRO_DATE_RECEDED = "retro_date_receded"
    NOTICE_OF_CANCELLATION_REDUCED = "notice_of_cancellation_reduced"
    NOTICE_OF_CANCELLATION_INCREASED = "notice_of_cancellation_increased"

    # --- decoys (spec §3.2). These exist so the engine can rank a real change as
    # informational or suppressed rather than staying silent. A decoy the engine never
    # emits is a decoy the eval harness cannot score.
    CARRIER_CHANGE = "carrier_change"
    PREMIUM_CHANGE = "premium_change"
    ADDRESS_CHANGE = "address_change"
    POLICY_NUMBER_CHANGE = "policy_number_change"

    # --- about the tool, not the policy. `report` groups these separately: an AM reading
    # "normalizer version mismatch" is being told something about the run, not about their
    # client's coverage. Not in spec §5.2 — recorded as an addition in STATUS.md.
    LOW_CONFIDENCE_FIELD = "low_confidence_field"
    FIELD_NOT_FOUND = "field_not_found"
    AMBIGUOUS_PATH = "ambiguous_path"
    NORMALIZER_VERSION_MISMATCH = "normalizer_version_mismatch"


TOOL_FINDINGS: frozenset[FindingType] = frozenset(
    {
        FindingType.LOW_CONFIDENCE_FIELD,
        FindingType.FIELD_NOT_FOUND,
        FindingType.AMBIGUOUS_PATH,
        FindingType.NORMALIZER_VERSION_MISMATCH,
    }
)
"""Findings about the run rather than about the policy.

The category already existed as a comment on the enum; declared here because two things need
it and a second copy is the one that goes stale. `report` groups these apart, and `narrate`
skips them — "we could not read this field" is a task for the account manager, and §7.1
already words it as a section heading. Handing it to a model to phrase invites prose about
the tool's own confusion in a document a client reads.
"""


type Scalar = IncludedSentinel | bool | int | str
"""Normalized value types. Deliberately narrow.

Findings are persisted, served over the API, and read back by the eval harness, so every
path out of this model is a JSON round-trip — and JSON has fewer types than Python. Each
member added here is another type the union has to guess between from a bare JSON scalar,
and a wrong guess silently rewrites a value. `Decimal` and `date` used to be members: they
made `"12345"` come back as `Decimal('12345')`, `"02134"` as `Decimal('2134')` with the
leading zero gone, and `"2025-01-01"` as a `date`. Every one of those is a real schema value
— a policy number, a ZIP, a period start.

Neither had a producer. `Field[Money]` is `int | IncludedSentinel`, and snapshot stores dates
as ISO strings ("normalize parses, contracts stays dumb"). **If money ever needs cents,
`Money` is what changes and this follows** — re-adding `Decimal` here alone reintroduces the
ambiguity without fixing the layer that actually holds the value.

`IncludedSentinel` is here because a limit printed "Included" is neither `$0` nor absent
(spec §4.3), and it is the finding layer where conflating them would manufacture a phantom
`limit_decrease`. It survives the round-trip: its core schema is a literal, which smart union
scores as an exact match ahead of `str`. A plain `Enum` does not get that treatment, which is
why `Unresolved` lives on its own field below rather than in this union.

`bool` sits ahead of `int` defensively. Smart union matches exact types first, so the order
makes no difference under the default mode — verified both ways. It would matter under
`union_mode="left_to_right"`, where `bool` after `int` lets `True` land as `1`.
"""


class Unit(StrEnum):
    """What a normalized value measures. `compare` reads it off the field's schema entry.

    Required, not defaulted. A default is what gets left in place, and a limit rendered
    `1,000,000` instead of `$1,000,000` is wrong quietly.
    """

    MONEY = "money"
    DAYS = "days"
    PERCENT = "percent"
    DATE = "date"  # ISO 8601 str; without this, a retro date is a policy number
    FLAG = "flag"
    TEXT = "text"


_UNIT_VALUE_TYPES: dict[Unit, type] = {
    Unit.MONEY: int,
    Unit.DAYS: int,
    Unit.PERCENT: int,
    Unit.DATE: str,
    Unit.FLAG: bool,
    Unit.TEXT: str,
}
"""Coverage is asserted in `tests/contracts/test_display.py`, not by a module-level `assert`
— `python -O` strips those, and a missing entry is a KeyError raised while building a report."""


class FindingSide(BaseModel):
    """One side of a finding — the value plus the evidence a human follows to check it.

    Deliberately NOT a `Field[T]`: by the time a finding exists the value is normalized and
    the confidence question is already resolved into the severity.

    `source_text` is verbatim text lifted off an untrusted PDF. It has to be here — spec
    invariant 7 needs it for 90-second verification — but it must not reach the narrator.
    See `NarrationInput` below.

    Exactly one of `value` / `absent` is set. A side either has a value or has a reason it
    doesn't; neither set says nothing, and both set is a contradiction. `absent` is a field
    of its own rather than a member of `value`'s union because `Unresolved` serializes to a
    plain string and would be read back as one — an absent side that cannot survive JSON is
    an absent side that cannot be persisted, and half of every added/removed finding is an
    absent side.
    """

    model_config = ConfigDict(frozen=True)

    value: Scalar | None = None
    absent: Unresolved | None = None
    unit: Unit
    """What the value measures. Required on an absent side too — the unit belongs to the
    field path, not to whether this document happened to carry a value for it."""
    raw: str | None = PydanticField(default=None, min_length=1)
    page: int | None = PydanticField(default=None, ge=1)
    bbox: BBox | None = None
    source_text: str | None = PydanticField(default=None, min_length=1)
    derived_from: tuple[str, ...] = ()
    """Field paths this value was computed from, when it was computed rather than read.

    Some values are real but appear on no page — a premium delta, or a structural observation
    like blanket-to-scheduled. Those cannot carry a citation, which would otherwise make them
    an unverifiable exception to spec invariant 2.

    Naming the inputs keeps invariant 7 intact one hop out: the reader cannot follow a delta
    to a page, but can follow it to the two totals it came from, and each of those is cited.
    That is why this is a tuple of paths and not a `derived: bool` — a boolean that switches
    the citation requirement off is the thing that gets set to make a validation error go
    away, and it tells a reviewer nothing. Empty means "read off the page", and the only way
    to claim otherwise is to say what from.

    Not validated against a snapshot; `FindingSide` has none. `compare` populates it and the
    eval harness can check the paths resolve.
    """

    @property
    def is_present(self) -> bool:
        return self.absent is None

    @property
    def derived(self) -> bool:
        return bool(self.derived_from)

    @model_validator(mode="after")
    def _evidence_matches_presence(self) -> "FindingSide":
        """Citation and presence co-vary. A present value without a citation violates spec
        invariant 2; an absent value with one is a rules-engine bug."""
        if self.absent is not None and self.value is not None:
            raise ValueError(
                f"side is both present ({self.value!r}) and absent ({self.absent}); "
                f"exactly one of value/absent is set"
            )

        if not self.is_present:
            if any((self.page, self.bbox, self.source_text, self.raw)):
                raise ValueError(f"absent side ({self.absent}) carries evidence")
            if self.derived:
                raise ValueError(f"absent side ({self.absent}) cannot be derived")
            return self

        if self.value is None:
            raise ValueError(
                "side has neither a value nor a reason it is absent; a side that says "
                "nothing cannot be rendered or verified"
            )

        if self.derived:
            if any((self.page, self.bbox, self.source_text, self.raw)):
                raise ValueError(
                    f"derived value {self.value!r} carries a citation; "
                    "a derived value is not on a page, so it has no `raw` printed form "
                    "either"
                )
            return self

        missing = [n for n in ("page", "source_text") if getattr(self, n) is None]
        if missing:
            raise ValueError(f"cited value {self.value!r} is missing {', '.join(missing)}")
        return self

    @model_validator(mode="after")
    def _value_matches_unit(self) -> "FindingSide":
        """A mis-set unit is a `compare` bug, caught at construction — not a "$1" in the
        report where `True` should have been."""
        if self.value is None or isinstance(self.value, IncludedSentinel):
            return self
        expected = _UNIT_VALUE_TYPES[self.unit]
        if type(self.value) is not expected:
            raise ValueError(
                f"unit {self.unit} expects {expected.__name__}, got "
                f"{type(self.value).__name__} ({self.value!r})"
            )
        if self.unit is Unit.DATE and isinstance(self.value, str):
            try:
                date.fromisoformat(self.value)
            except ValueError:
                raise ValueError(f"unit date expects ISO 8601, got {self.value!r}") from None
        return self

    def display(self) -> str | None:
        """The one place a normalized value becomes text. `report` and `for_narration`
        both call it, so the AM's report and the client summary can't disagree.

        `Scalar` has no `Address` member and should not grow one: `compare` renders an
        address to its normalized form before it gets here (see .spec/modules/compare.md).
        """
        v = self.value
        if v is None:
            return None

        match v:
            case IncludedSentinel():
                # Not an amount - renders the same whatever the unit
                return "Included"
            case bool():
                return "Yes" if v else "No"
            case int():
                match self.unit:
                    case Unit.MONEY:
                        return f"${v:,}"
                    case Unit.PERCENT:
                        return f"{v}%"
                    case Unit.DAYS:
                        return f"{v} day{'' if v == 1 else 's'}"
                    case _:
                        return f"{v:,}"
            case str():
                if self.unit is Unit.DATE:
                    d = date.fromisoformat(v)
                    return f"{d:%b} {d.day}, {d.year}"  # %-d isn't portable
                return v
            case _:
                # `Scalar` is a closed union and the cases above cover it. This makes
                # growing it a type error here rather than a value that renders as nothing.
                assert_never(v)

    def for_narration(self) -> "NarrationSide | None":
        """This side as the narrator may see it, or `None` if it may not be shown at all.

        Absence for a reason that is a fact about the *run* — `NO_SUCH_PATH`, `AMBIGUOUS` —
        has no client-facing sentence. Those only arise on `TOOL_FINDINGS`, which
        `Finding.for_narration` already drops, so this is the second lock: it makes the
        guarantee something the code enforces rather than something the caller remembers.
        """
        if self.absent is None:
            return NarrationSide(display=self.display())
        if self.absent is Unresolved.NO_SUCH_ROW:
            return NarrationSide(absent=Unresolved.NO_SUCH_ROW)
        return None


class Finding(BaseModel):
    """A single ruled difference between two snapshots (spec §5.3)."""

    model_config = ConfigDict(frozen=True)

    finding_id: str = PydanticField(min_length=1)
    """Narration's output contract keys on this (`{finding_id: narrative}` validated against
    known IDs), so an empty one is a merge that silently matches nothing."""
    type: FindingType
    severity: Severity
    """Not cross-checked against `type` here. The type -> default severity map lives in
    `compare/rules.py` and a second copy in a validator is the copy that goes stale."""
    field_path: str = PydanticField(min_length=1)
    prior: FindingSide
    current: FindingSide
    """Both required even when one side is absent — the report renders "absent" explicitly
    rather than omitting the row (spec §5.3)."""
    confidence: Confidence
    """The weaker of the two source fields' confidence, set by `compare`, carried for display.
    **No rule branches on it.** Nearly redundant — a field low on either side becomes
    `low_confidence_field` and never claims a direction, so every substantive finding is
    `high` by construction — but §5.3 names it and `not_found` gives it a third state.

    Deliberately not per-side. Which side was low is real utility and a report-design
    question; settle it after the screen shares rather than guessing now."""
    narrative: str | None = PydanticField(default=None, min_length=1)
    """`min_length=1` keeps the two states distinct: None is "not narrated yet", and "" would
    otherwise be a third state meaning "narrated to nothing"."""

    @model_validator(mode="after")
    def _sides_agree_on_unit(self) -> "Finding":
        if self.prior.unit is not self.current.unit:
            raise ValueError(
                f"{self.field_path}: sides disagree on unit "
                f"(prior={self.prior.unit}, current={self.current.unit})"
            )
        return self

    def with_narrative(self, narrative: str) -> "Finding":
        """The merge back in. `model_copy(update=...)` skips validation entirely, so the one
        field a model writes would be the one field nothing checks — including `min_length`
        and any later rule about which severities may carry narration."""
        return self.model_validate({**self.model_dump(), "narrative": narrative})

    def for_narration(self) -> "NarrationInput | None":
        """The projection that decides what the narrator sees. `None` means "do not narrate".

        Constructed field by field on purpose. `model_dump(exclude=...)` inverts the default:
        a field added to `Finding` or `FindingSide` would reach the narrator unless someone
        remembered to exclude it, and forgetting is silent.

        `TOOL_FINDINGS` return `None`. Their sides can be absent for reasons that are facts
        about the run — a path that resolves nowhere, a document naming one identity twice —
        and those have no client-facing sentence. Deciding it here rather than at the call
        site keeps "what may be narrated" in the same place as "what the narrator sees";
        `narrate()` would otherwise re-derive it, and the two would drift.
        """
        if self.type in TOOL_FINDINGS:
            return None
        prior = self.prior.for_narration()
        current = self.current.for_narration()
        if prior is None or current is None:
            return None
        return NarrationInput(
            finding_id=self.finding_id,
            type=self.type,
            field_path=self.field_path,
            prior=prior,
            current=current,
        )


class NarrationSide(BaseModel):
    """One side as the narrator sees it: the rendered value, or the reason there isn't one.

    `absent` is carried because `display() -> None` says a side is missing but not why, and
    "no longer on the policy" and "we could not read it" are different sentences to a client
    — one of which is false. It is safe to pass: `Unresolved` is a closed enum we define, not
    text off the document.

    Narrowed to `NO_SUCH_ROW`, the only member that describes the *policy*. `NO_SUCH_PATH` and
    `AMBIGUOUS` describe the run — a fixture naming a field that cannot exist, a document
    naming one identity twice — and a narrator handed those can write about the tool's own
    confusion in client-facing copy. They only ever appear on `TOOL_FINDINGS`, which
    `for_narration` drops; this annotation is what makes that structural rather than a
    convention `narrate` has to remember.
    """

    model_config = ConfigDict(frozen=True)

    display: str | None = PydanticField(default=None, min_length=1)
    absent: Literal[Unresolved.NO_SUCH_ROW] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "NarrationSide":
        """Holds by construction — `display()` returns None iff `absent` is set — so this
        pins the biconditional rather than discovering it."""
        if (self.display is None) == (self.absent is None):
            raise ValueError(
                f"exactly one of display/absent is set "
                f"(display={self.display!r}, absent={self.absent})"
            )
        return self


class NarrationInput(BaseModel):
    """What the narrator is allowed to see. The only thing `narrate()` accepts.

    An uploaded PDF is untrusted input to a language model, and `Finding` carries verbatim
    regions of it in `FindingSide.source_text`. Passing findings straight to narration hands
    the model attacker-controlled text from the document it is describing. This model is the
    boundary: `narrate()` is typed to take these, so the narrator is structurally incapable of
    receiving a page snippet rather than merely conventionally denied one.

    Note the honest limit. A normalized value can still be document-derived text — a
    `named_insured`, a form title, a scheduled party name are all strings copied off the page.
    This narrows the model's exposure to short normalized values; it does not eliminate it.
    What actually contains an injection is the output contract: narration returns
    `{finding_id: narrative}` validated against known IDs, so a manipulated narrator can
    corrupt wording but cannot add a finding, drop one, or change a severity.
    """

    model_config = ConfigDict(frozen=True)

    finding_id: str
    type: FindingType
    field_path: str
    prior: NarrationSide
    current: NarrationSide

    # `severity` is absent deliberately, not by oversight. The narrator restates what
    # changed; severity is what `report` renders. Handing the model a field labelled
    # `material_adverse` invites exactly the tone spec §11 bans — the boundary leaks through
    # tone, not through explicit recommendations (.spec/modules/narrate.md, failure modes).


SECTION_ORDER: tuple[tuple[Severity, str], ...] = (
    (Severity.NEEDS_REVIEW, "NEEDS REVIEW — LOW CONFIDENCE EXTRACTION"),
    (Severity.MATERIAL_ADVERSE, "MATERIAL CHANGES — COVERAGE REDUCED"),
    (Severity.REVIEW_REQUIRED, "REVIEW REQUIRED"),
    (Severity.FAVORABLE, "MATERIAL CHANGES — COVERAGE BROADENED"),
    (Severity.INFORMATIONAL, "INFORMATIONAL"),
)
"""§7.1's five sections, in §7.1's order. `SUPPRESSED` is absent and that is the whole of
its handling — see `ComparisonResult.suppressed`.

Explicit rather than derived from `Severity`'s declaration order, which agrees today: a
reader reordering the enum for tidiness would otherwise reorder an AM's report.
"""


class Section(BaseModel):
    """One §7.1 heading and the findings under it.

    The heading travels with its findings so `report` iterates rather than pairs. A separate
    `severity -> heading` map in `report` is a map that can be one row out of step and still
    render a full-looking report.
    """

    model_config = ConfigDict(frozen=True)

    severity: Severity
    heading: str
    findings: tuple[Finding, ...]

    @model_validator(mode="after")
    def _homogeneous(self) -> "Section":
        wrong = [f.finding_id for f in self.findings if f.severity is not self.severity]
        if wrong:
            raise ValueError(f"{self.heading}: findings of another severity ({wrong})")
        return self


class ComparisonResult(BaseModel):
    """Everything one comparison run produces."""

    model_config = ConfigDict(frozen=True)

    findings: tuple[Finding, ...]
    """`tuple`, not `list`: `frozen=True` stops reassignment but not `result.findings.append`.

    Holds every finding the engine built, `suppressed` included. Filtering happens at render:
    a decoy expecting `suppressed` has to be emitted to be scored, and one that never reaches
    this object cannot be told from one the engine never noticed (spec §8).
    """
    unchanged_verified: int
    """Count of fields compared and found identical.

    Not decoration. Spec §7.1: this is the difference between "the tool found four things"
    and "the tool checked ninety-one fields and four changed." Do not drop it because it
    isn't a finding.
    """

    def sections(self) -> tuple[Section, ...]:
        """Findings grouped under §7.1's headings, in §7.1's order, empty ones included.

        Empty sections are emitted, never skipped. "MATERIAL CHANGES — COVERAGE REDUCED" with
        nothing under it says the tool looked and found none; drop the heading and that report
        is indistinguishable from one where the section was never checked. The distinction is
        the diligence record.

        Within a section, `findings` order is preserved — so determinism here is `compare`'s
        to guarantee, not this method's. Sorting on `field_path` would make it self-sufficient
        at the cost of scrambling coverage-part order into alphabetical, which is worse to
        read and no more correct.

        Sections hold fresh tuples rather than slices of `findings`; nothing here aliases.
        """
        # Pre-seeded from SECTION_ORDER, and deliberately NOT a defaultdict: a defaultdict
        # invents a bucket for an unmapped severity, which is then never emitted, which turns
        # the raise below back into the silent drop it exists to prevent.
        grouped: dict[Severity, list[Finding]] = {sev: [] for sev, _ in SECTION_ORDER}

        for f in self.findings:
            if f.severity is Severity.SUPPRESSED:
                continue
            bucket = grouped.get(f.severity)
            if bucket is None:
                raise ValueError(
                    f"{f.finding_id}: severity {f.severity} has no report section; "
                    f"add it to SECTION_ORDER"
                )
            bucket.append(f)

        return tuple(
            Section(severity=sev, heading=heading, findings=tuple(grouped[sev]))
            for sev, heading in SECTION_ORDER
        )

    @property
    def suppressed(self) -> tuple[Finding, ...]:
        """Changes seen and ruled immaterial. §7.1 gives them no section, so the report shows
        them as a count — the same shape of diligence as `unchanged_verified`: that one is
        "checked, identical", this is "checked, changed, immaterial".

        Reachable because the eval harness scores it. A decoy has to be emitted to be marked
        correctly suppressed, and a decoy that never reaches this object cannot be told from
        one the engine never noticed (spec §8).
        """
        return tuple(f for f in self.findings if f.severity is Severity.SUPPRESSED)


__all__ = [
    "SECTION_ORDER",
    "TOOL_FINDINGS",
    "BBox",
    "ComparisonResult",
    "Finding",
    "FindingSide",
    "FindingType",
    "NarrationInput",
    "NarrationSide",
    "Scalar",
    "Section",
    "Severity",
    "Unit",
]
