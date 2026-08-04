"""Manifest — ground truth for one synthetic renewal pair (spec §3.2).

Authored BEFORE the extractor is written (spec invariant 4). `pairgen` reads a manifest to
produce the renewal PDF; `evals` reads the same manifest to score what the pipeline found.
Neither writes back to it.
"""

from pydantic import BaseModel, ConfigDict

from policycheck.contracts.finding import FindingType, Severity

_FROZEN = ConfigDict(frozen=True)


class InjectedChange(BaseModel):
    """A change deliberately applied to the renewal, with the finding it must produce."""

    model_config = _FROZEN

    change_id: str
    field_path: str
    # TODO(human): from_value / to_value. Note the JSON keys in spec §3.2 are "from" and
    # "to" — `from` is a Python keyword, so alias them (`alias="from"`) and enable
    # populate_by_name. Type them loosely (object | None): a manifest change can target an
    # int limit, a string edition, or an enum valuation.
    expected_severity: Severity
    expected_finding_type: FindingType


class DecoyChange(BaseModel):
    """A change that must NOT be flagged adverse.

    Premium, mailing address, agent of record, policy number, carrier name where coverage
    is unchanged. Decoy suppression is a 100% gate (spec §8) — a pair where every injected
    change is found but one decoy is flagged adverse is a FAILED pair, not a partial pass.
    """

    model_config = _FROZEN

    field_path: str
    # TODO(human): from_value / to_value (same aliasing as above), expected_severity
    # (informational or suppressed)


class Manifest(BaseModel):
    model_config = _FROZEN

    pair_id: str
    base_document: str
    renewal_document: str
    line_of_business: str
    injected_changes: list[InjectedChange]
    decoy_changes: list[DecoyChange] = []

    # TODO(human): a `material_changes` property returning only the injected changes with
    # expected_severity == MATERIAL_ADVERSE. Material recall is the 100% gate and the
    # metric that decides whether the product lives — give it its own accessor rather than
    # filtering inline at each call site.
