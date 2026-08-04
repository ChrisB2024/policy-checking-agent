"""Closed vocabularies shared across the pipeline.

Every enum here is a normalization target: the `normalize` module maps carrier-specific
strings onto these members, and `compare` reasons about the members rather than the strings.
Adding a member is a schema change — see `.spec/modules/contracts.md` (Freeze rule).
"""

from enum import StrEnum


class Confidence(StrEnum):
    """How much to trust an extracted value.

    `LOW` and `NOT_FOUND` both route to `needs_review` downstream. The comparison engine
    must never treat either as a value (spec invariant 3).
    """

    HIGH = "high"  # both extraction passes agreed
    LOW = "low"  # passes disagreed, or the value was inferred rather than read
    NOT_FOUND = "not_found"  # field absent from the document


class PageClassification(StrEnum):
    DEC_PAGE = "dec_page"
    FORMS_SCHEDULE = "forms_schedule"
    ENDORSEMENT = "endorsement"
    JACKET = "jacket"
    OTHER = "other"


class CoverageTrigger(StrEnum):
    OCCURRENCE = "occurrence"
    CLAIMS_MADE = "claims_made"


class AggregateBasis(StrEnum):
    """What the general aggregate applies per. Narrowing is per-project/location -> per-policy."""

    POLICY = "policy"
    PROJECT = "project"
    LOCATION = "location"


class DeductibleBasis(StrEnum):
    PER_CLAIM = "per_claim"
    PER_OCCURRENCE = "per_occurrence"


class CausesOfLoss(StrEnum):
    """Breadth of the property causes-of-loss form. Narrowing is special -> broad -> basic."""

    SPECIAL = "special"
    BROAD = "broad"
    BASIC = "basic"


class ValuationBasis(StrEnum):
    """Downgrade is replacement_cost -> acv or functional."""

    REPLACEMENT_COST = "replacement_cost"
    ACV = "acv"
    FUNCTIONAL = "functional"


class BusinessIncomeBasis(StrEnum):
    ACTUAL_LOSS = "actual_loss"
    COINSURANCE = "coinsurance"
    MONTHLY_LIMIT = "monthly_limit"


class AIBasis(StrEnum):
    """Additional insured grant basis. Narrowing is blanket -> scheduled."""

    BLANKET = "blanket"
    SCHEDULED = "scheduled"
    NONE = "none"


class AIScope(StrEnum):
    """Additional insured operations scope. Narrowing is both -> ongoing_ops."""

    ONGOING_OPS = "ongoing_ops"
    COMPLETED_OPS = "completed_ops"
    BOTH = "both"
    NONE = "none"


class AuditBasis(StrEnum):
    AUDITABLE = "auditable"
    NON_AUDITABLE = "non_auditable"


class ValueBasis(StrEnum):
    """Why a value is absent, when it is.

    Distinguishes "the document says this is excluded" from "we could not find it".
    Set alongside `value=None`; see spec §4.3.
    """

    EXCLUDED = "excluded"  # document said Excluded / None / N/A
    ABSENT = "absent"  # field simply not present
