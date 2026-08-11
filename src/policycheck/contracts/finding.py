"""Finding — the output of the comparison engine.

Findings are produced by deterministic rules only. The model never rules on whether a
change matters (spec invariant 1); it only fills `narrative`, last, in a separate pass.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic import Field as PydanticField

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
            raise ValueError(
                f"cited value {self.value!r} is missing {', '.join(missing)}"
            )
        return self

    def display(self) -> str | None:
        """The one place a normalized value becomes text. `report` and `for_narration`
        both call it, so the AM's report and the client summary can't disagree."""


class Finding(BaseModel):
    """A single ruled difference between two snapshots (spec §5.3)."""

    model_config = ConfigDict(frozen=True)

    finding_id: str
    # TODO(human): type, severity, field_path, prior: FindingSide, current: FindingSide,
    # narrative: str | None = None, confidence
    #
    # `narrative` is the ONLY model-generated field on this object and starts None.
    # `prior` / `current` are both required even when one side is not_found — the report
    # renders "absent" explicitly rather than omitting the row.

    # TODO(human): `for_narration(self) -> NarrationInput` — the projection that drops the
    # citation fields. One method, so there is exactly one place that decides what the
    # narrator sees and it can be tested directly.


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

    # TODO(human): finding_id, type, field_path, and the two normalized values — prior and
    # current. Nothing else off `FindingSide`: no page, no bbox, no source_text, no raw.
    # `raw` is as-printed document text and belongs in the same excluded category as
    # source_text, even though it looks like a harmless display string.
    #
    # Leave `severity` out too, and make that a deliberate call rather than an oversight.
    # The narrator's job is to restate what changed; severity is what `report` renders.
    # Handing the model a field labelled `material_adverse` invites exactly the tone that
    # spec §11 bans — the boundary leaks through tone, not through explicit recommendations
    # (see .spec/modules/narrate.md, failure modes).


class ComparisonResult(BaseModel):
    """Everything one comparison run produces."""

    model_config = ConfigDict(frozen=True)

    findings: list[Finding]
    unchanged_verified: int
    """Count of fields compared and found identical.

    Not decoration. Spec §7.1: this is the difference between "the tool found four things"
    and "the tool checked ninety-one fields and four changed." Do not drop it because it
    isn't a finding.
    """

    # TODO(human): a helper that groups findings into the six report sections in the
    # order spec §7.1 prescribes (needs_review FIRST — a checker needs to know what the
    # tool didn't handle before reading what it did).


__all__ = [
    "BBox",
    "ComparisonResult",
    "Finding",
    "FindingSide",
    "FindingType",
    "NarrationInput",
    "Scalar",
    "Severity",
]
