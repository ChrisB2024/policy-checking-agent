"""The data contract. Imports nothing from the rest of the codebase.

Import our envelope as `from policycheck.contracts import Field` — it shadows
`pydantic.Field`, so in files needing both, alias pydantic's as `PydanticField`.
"""

from policycheck.contracts.enums import (
    AggregateBasis,
    AIBasis,
    AIScope,
    AuditBasis,
    BusinessIncomeBasis,
    CausesOfLoss,
    Confidence,
    CoverageTrigger,
    DeductibleBasis,
    PageClassification,
    ValuationBasis,
    ValueBasis,
)
from policycheck.contracts.field import BBox, Field, IncludedSentinel, agreement
from policycheck.contracts.finding import (
    ComparisonResult,
    Finding,
    FindingSide,
    FindingType,
    Severity,
)
from policycheck.contracts.manifest import DecoyChange, InjectedChange, Manifest
from policycheck.contracts.snapshot import (
    Address,
    DocumentMeta,
    GeneralLiability,
    Identity,
    PolicySnapshot,
)

__all__ = [
    "AIBasis",
    "AIScope",
    "Address",
    "AggregateBasis",
    "AuditBasis",
    "BBox",
    "BusinessIncomeBasis",
    "CausesOfLoss",
    "ComparisonResult",
    "Confidence",
    "CoverageTrigger",
    "DecoyChange",
    "DeductibleBasis",
    "DocumentMeta",
    "Field",
    "Finding",
    "FindingSide",
    "FindingType",
    "GeneralLiability",
    "Identity",
    "IncludedSentinel",
    "InjectedChange",
    "Manifest",
    "PageClassification",
    "PolicySnapshot",
    "Severity",
    "ValuationBasis",
    "ValueBasis",
    "agreement",
]
