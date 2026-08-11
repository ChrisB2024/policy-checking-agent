"""Finding — the output of the comparison engine.

Findings are produced by deterministic rules only. The model never rules on whether a
change matters (spec invariant 1); it only fills `narrative`, last, in a separate pass.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from policycheck.contracts.field import BBox


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
    """

    # TODO(human): transcribe spec §5.2. All of it, including the ones you might be
    # tempted to skip — `notice_of_cancellation_reduced` and `retro_date_advanced` are
    # exactly the subtle findings the demo is built around.
    #
    # Two that carry design weight, worth reading the spec note on before you write them:
    #   FORM_EDITION_CHANGE      -> review_required, NEVER auto-classified as adverse or
    #                               favorable. Direction is form-specific and cannot be
    #                               inferred from the date.
    #   LOW_CONFIDENCE_FIELD     -> needs_review, and it OUTRANKS everything. A field
    #                               extracted at `low` on either side does not also
    #                               produce a substantive finding claiming a direction.


class FindingSide(BaseModel):
    """One side of a finding — the value plus the evidence a human follows to check it."""

    model_config = ConfigDict(frozen=True)

    # TODO(human): value, page, bbox (nullable), source_text.
    # Note this is deliberately NOT a Field[T]: by the time a finding exists the value is
    # normalized and the confidence question is already resolved into the severity.
    #
    # `source_text` is verbatim text lifted off an untrusted PDF. It has to be here —
    # spec invariant 7 needs it for 90-second verification — but it must not reach the
    # narrator. See `NarrationInput` below.


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


__all__ = ["BBox", "ComparisonResult", "Finding", "FindingSide", "FindingType", "Severity"]
