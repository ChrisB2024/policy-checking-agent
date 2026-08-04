"""PolicySnapshot — one per document.

This is the object the comparison engine operates on. It never sees raw text (spec §4.2).

Two sections below are written out as a worked example (`Identity`, `GeneralLiability`).
The rest are `TODO(human)` — transcribe them from spec §4.2 following the same pattern.
Watch for the shape of each: some are flat, `Property` has a list of sub-models, and
`RiskTransfer` nests two levels.
"""

from pydantic import BaseModel, ConfigDict

from policycheck.contracts.enums import (
    AggregateBasis,
    CoverageTrigger,
    DeductibleBasis,
    PageClassification,
)
from policycheck.contracts.field import Field

# Every model here is frozen: the pipeline builds new objects rather than mutating.
_FROZEN = ConfigDict(frozen=True)


class Address(BaseModel):
    """USPS-normalized components. Used as the match key for property locations.

    Locations match by address, not by location number — carriers renumber locations
    between terms, and matching by number produces a phantom removed/added pair on every
    renewal that reorders the schedule (spec §5.1).
    """

    model_config = _FROZEN

    # TODO(human): street, unit, city, state, zip5 — plus a `normalized` key used for
    # matching. Decide whether `normalized` is stored or computed; whichever you pick,
    # matching must be stable across "STE 200" / "Suite 200" / "#200".


class DocumentMeta(BaseModel):
    model_config = _FROZEN

    source_filename: str
    page_count: int
    page_classifications: list[PageClassification]


# ---------------------------------------------------------------------------
# Worked example 1 — flat section, every value wrapped in Field[T].
# ---------------------------------------------------------------------------


class Identity(BaseModel):
    model_config = _FROZEN

    named_insured: Field[str]
    dba: list[Field[str]]
    mailing_address: Field[Address]
    policy_number: Field[str]
    carrier_name: Field[str]
    naic_code: Field[str]
    policy_period_start: Field[str]  # ISO date; normalize parses, contracts stays dumb
    policy_period_end: Field[str]
    coverage_trigger: Field[CoverageTrigger]
    retroactive_date: Field[str] | None


# ---------------------------------------------------------------------------
# Worked example 2 — note that every limit is Field[int], never bare int, and that
# "no deductible" is a Field with value=None + basis, not an absent attribute.
# ---------------------------------------------------------------------------


class GeneralLiability(BaseModel):
    model_config = _FROZEN

    each_occurrence: Field[int]
    general_aggregate: Field[int]
    aggregate_applies_per: Field[AggregateBasis]
    products_completed_ops_agg: Field[int]
    personal_advertising_injury: Field[int]
    damage_to_rented_premises: Field[int]
    medical_expense: Field[int]
    deductible_amount: Field[int]
    deductible_basis: Field[DeductibleBasis]
    sir_amount: Field[int]


# ---------------------------------------------------------------------------
# TODO(human): the rest of spec §4.2, same pattern.
# ---------------------------------------------------------------------------


class PropertyLocation(BaseModel):
    """One scheduled location. spec §4.2 -> property.locations[]"""

    model_config = _FROZEN
    # TODO(human): location_number, address, building_limit, bpp_limit, valuation,
    # coinsurance_pct, deductible


class Property(BaseModel):
    model_config = _FROZEN
    # TODO(human): blanket_coverage, blanket_limit, causes_of_loss_form, locations[],
    # business_income_limit, business_income_basis, period_of_indemnity_months


class FormRef(BaseModel):
    """One row of the forms schedule.

    `form_family` is the match key for forms, exclusions, and endorsements — which makes
    the canonicalizer in `normalize` the highest-leverage code in the build (spec §4.3).
    A form number the canonicalizer cannot parse must still appear here with its
    `raw_form_number`, so `compare` can emit `form_added_unclassified` rather than
    silently dropping it.
    """

    model_config = _FROZEN
    # TODO(human): form_family, edition, title, raw_form_number


class AdditionalInsured(BaseModel):
    model_config = _FROZEN
    # TODO(human): present, basis, scope, scheduled_parties[], governing_forms[]


class WaiverOfSubrogation(BaseModel):
    model_config = _FROZEN
    # TODO(human): present, basis


class PrimaryNoncontributory(BaseModel):
    model_config = _FROZEN
    # TODO(human): present


class RiskTransfer(BaseModel):
    """Extracted separately, at the highest scrutiny (spec §4.2).

    This section carries the findings an account manager gets burned by — AI scope
    narrowing, a dropped waiver, P&NC quietly removed. Nothing here may be inferred:
    if the endorsement isn't on the page, it isn't present.
    """

    model_config = _FROZEN
    # TODO(human): additional_insured, waiver_of_subrogation, primary_noncontributory,
    # notice_of_cancellation_days


class Exclusion(BaseModel):
    """An endorsement identified as coverage-restricting."""

    model_config = _FROZEN
    # TODO(human): form_family, title, subject (short normalized tag, e.g. "habitability")


class Premium(BaseModel):
    model_config = _FROZEN
    # TODO(human): total, taxes_fees, audit_basis


class PolicySnapshot(BaseModel):
    """One document, fully extracted. The unit the comparison engine consumes."""

    model_config = _FROZEN

    document: DocumentMeta
    identity: Identity
    general_liability: GeneralLiability
    # TODO(human): property, forms_schedule: list[FormRef], risk_transfer,
    # exclusions: list[Exclusion], premium

    def field_at(self, path: str) -> Field[object] | None:
        """Resolve a dotted `field_path` (e.g. "gl.each_occurrence_limit") to its Field.

        Manifests, findings, and the eval harness all address fields by string path
        (spec §3.2, §5.3). Deriving that from the model — rather than maintaining a
        hand-written path table — is what stops a newly added field from being silently
        skipped by the eval harness (see .spec/modules/contracts.md, failure modes).
        """
        # TODO(human): walk the model by attribute, supporting list indexing for
        # `property.locations[0].valuation`. Return None for an unknown path rather than
        # raising — an unknown path in a manifest is a data error the eval harness should
        # report per-pair, not a crash that kills the whole run.
        raise NotImplementedError
