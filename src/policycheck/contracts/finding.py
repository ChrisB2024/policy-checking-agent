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
