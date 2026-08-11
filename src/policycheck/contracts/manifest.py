"""Manifest — ground truth for one synthetic renewal pair (spec §3.2).

Authored BEFORE the extractor is written (spec invariant 4). `pairgen` reads a manifest to
produce the renewal PDF; `evals` reads the same manifest to score what the pipeline found.
Neither writes back to it.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from policycheck.contracts.finding import FindingType, Severity

# `populate_by_name` because two fields alias to `from` and `to`: JSON uses the spec's keys,
# Python uses `from_value` / `to_value`. Without it these models are unconstructible in
# Python — `from=` is a keyword, so even the alias spelling is a syntax error.
_FROZEN = ConfigDict(frozen=True, populate_by_name=True)


class InjectedChange(BaseModel):
    """A change deliberately applied to the renewal, with the finding it must produce."""

    model_config = _FROZEN

    change_id: str
    field_path: str
    # Loosely typed on purpose: a change can target an int limit, a string edition, or an
    # enum valuation. Narrowing this would mean duplicating `Scalar` here and keeping the
    # two in step, and a manifest is hand-authored ground truth rather than pipeline output.
    from_value: object | None = Field(alias="from")
    to_value: object | None = Field(alias="to")
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
    from_value: object | None = Field(alias="from")
    to_value: object | None = Field(alias="to")
    expected_severity: Literal[Severity.INFORMATIONAL, Severity.SUPPRESSED]
    """Narrowed to the two legal outcomes, not `Severity`.

    A decoy expecting `material_adverse` is a manifest asserting the opposite of what makes
    it a decoy, and the harness would score against it faithfully — the 100% suppression gate
    would still read as passing while measuring nothing. The type is the enforcement because
    manifests are hand-authored.
    """


class Manifest(BaseModel):
    model_config = _FROZEN

    pair_id: str
    base_document: str
    renewal_document: str
    line_of_business: str
    # Tuples, not lists: `frozen=True` stops attribute assignment but not mutation in place,
    # and a list would let `manifest.injected_changes.append(...)` succeed on ground truth
    # the module docstring says is never written back to — accepting objects that were never
    # validated, since validation ran at construction.
    injected_changes: tuple[InjectedChange, ...]
    decoy_changes: tuple[DecoyChange, ...] = ()

    @property
    def material_changes(self) -> tuple[InjectedChange, ...]:
        """Injected changes that must be found - the 100% recall gate"""
        return tuple(
            c for c in self.injected_changes if c.expected_severity is Severity.MATERIAL_ADVERSE
        )
