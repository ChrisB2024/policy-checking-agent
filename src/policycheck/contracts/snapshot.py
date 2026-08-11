"""PolicySnapshot — one per document.

This is the object the comparison engine operates on. It never sees raw text (spec §4.2).

Every section of spec §4.2, plus `field_at` — the string-path resolver that manifests,
findings, and the eval harness all address fields through.
"""

import re
from collections.abc import Sequence
from enum import Enum
from types import UnionType
from typing import Any, ClassVar, TypeIs, Union, cast, get_args, get_origin

from pydantic import BaseModel, ConfigDict

from policycheck.contracts.enums import (
    AggregateBasis,
    AIBasis,
    AIScope,
    AuditBasis,
    BusinessIncomeBasis,
    CausesOfLoss,
    CoverageTrigger,
    DeductibleBasis,
    PageClassification,
    ValuationBasis,
)
from policycheck.contracts.field import Field, Money

# Every model here is frozen: the pipeline builds new objects rather than mutating.
_FROZEN = ConfigDict(frozen=True)


class Address(BaseModel):
    """USPS-normalized components. Used as the match key for property locations.

    Locations match by address, not by location number — carriers renumber locations
    between terms, and matching by number produces a phantom removed/added pair on every
    renewal that reorders the schedule (spec §5.1).
    """

    model_config = _FROZEN

    raw: str
    street: str | None
    unit: str | None
    city: str | None
    state: str | None
    zip5: str | None
    match_key: str | None


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
# Worked example 2 — every limit and deductible is `Field[Money]`, never a bare int:
# a dec page can print "Included" where a number would go, and that is neither $0 nor
# absent (spec §4.3). Non-amount fields stay on their own type, which keeps the sentinel
# out of their JSON schema. "No deductible" is a Field with value=None plus a basis, not
# an absent attribute.
# ---------------------------------------------------------------------------


class GeneralLiability(BaseModel):
    model_config = _FROZEN

    each_occurrence: Field[Money]
    general_aggregate: Field[Money]
    aggregate_applies_per: Field[AggregateBasis]
    products_completed_ops_agg: Field[Money]
    personal_advertising_injury: Field[Money]
    damage_to_rented_premises: Field[Money]
    medical_expense: Field[Money]
    deductible_amount: Field[Money]
    deductible_basis: Field[DeductibleBasis]
    sir_amount: Field[Money]


class PropertyLocation(BaseModel):
    """One scheduled location. spec §4.2 -> property.locations[]"""

    model_config = _FROZEN

    # Dotted because the key lives inside the Address that the Field wraps: `address` is a
    # Field, so resolving this hops through `.value` before reading `.match_key`.
    _match_key: ClassVar[str] = "address.match_key"

    location_number: Field[str]
    address: Field[Address]
    building_limit: Field[Money]
    bpp_limit: Field[Money]
    valuation: Field[ValuationBasis]
    coinsurance_pct: Field[int]
    deductible: Field[Money]


class Property(BaseModel):
    model_config = _FROZEN
    blanket_coverage: Field[bool]
    blanket_limit: Field[Money]
    causes_of_loss_form: Field[CausesOfLoss]
    locations: list[PropertyLocation]
    business_income_limit: Field[Money]
    business_income_basis: Field[BusinessIncomeBasis]
    period_of_indemnity_months: Field[int]


class FormRef(BaseModel):
    """One row of the forms schedule.

    `form_family` is the match key for forms, exclusions, and endorsements — which makes
    the canonicalizer in `normalize` the highest-leverage code in the build (spec §4.3).
    A form number the canonicalizer cannot parse must still appear here with its
    `raw_form_number`, so `compare` can emit `form_added_unclassified` rather than
    silently dropping it.
    """

    model_config = _FROZEN

    # spec §5.1 matches forms by family, so family is also how a manifest addresses one:
    # `forms_schedule.CG0001.edition`. Declared once, read by both `compare` and `field_at`.
    _match_key: ClassVar[str] = "form_family"

    form_family: Field[str]
    edition: Field[str]
    title: Field[str]
    raw_form_number: Field[str]


class AdditionalInsured(BaseModel):
    model_config = _FROZEN
    present: Field[bool]
    basis: Field[AIBasis]
    scope: Field[AIScope]
    scheduled_parties: list[Field[str]]
    governing_forms: list[Field[str]]


class WaiverOfSubrogation(BaseModel):
    model_config = _FROZEN
    present: Field[bool]
    basis: Field[AIBasis]


class PrimaryNoncontributory(BaseModel):
    model_config = _FROZEN
    present: Field[bool]


class RiskTransfer(BaseModel):
    """Extracted separately, at the highest scrutiny (spec §4.2).

    This section carries the findings an account manager gets burned by — AI scope
    narrowing, a dropped waiver, P&NC quietly removed. Nothing here may be inferred:
    if the endorsement isn't on the page, it isn't present.
    """

    model_config = _FROZEN
    additional_insured: AdditionalInsured
    waiver_of_subrogation: WaiverOfSubrogation
    primary_noncontributory: PrimaryNoncontributory
    notice_of_cancellation_days: Field[int]


class Exclusion(BaseModel):
    """An endorsement identified as coverage-restricting."""

    model_config = _FROZEN

    _match_key: ClassVar[str] = "form_family"

    form_family: Field[str]
    title: Field[str]
    subject: Field[str]


class Premium(BaseModel):
    model_config = _FROZEN
    total: Field[Money]
    taxes_fees: Field[Money]
    audit_basis: Field[AuditBasis]


# ---------------------------------------------------------------------------
# Addressing collection members by match key (spec §5.1, §3.2).
#
# `forms_schedule.CG0001.edition` addresses a form by its family, not its position, for the
# same reason §5.1 matches forms by family: order differs between documents. The key each
# collection uses is declared once on the element model as `_match_key` and read by both
# `compare` and `field_at`, so adding a collection cannot leave the two disagreeing.
# ---------------------------------------------------------------------------

def _unwrap(obj: object, path: str) -> object | None:
    """Follow a dotted path through models, stepping through any `Field` on the way.

    `Field` is transparent here — `"address.match_key"` means the Address inside the
    `address` Field, then its `match_key`. This is the one place that reaches inside a
    Field on purpose; `field_at` must not.

    Returns None for anything unresolvable rather than raising: a model declaring a stale
    `_match_key` should surface as an unaddressable path, not a crash inside the eval
    harness. Membership is tested against `model_fields`, not `hasattr`, so a stale key
    cannot resolve to a method or a ClassVar.
    """
    current: object = obj
    for segment in path.split("."):
        if isinstance(current, Field):
            current = current.value

        if not isinstance(current, BaseModel) or segment not in type(current).model_fields:
            return None

        current = getattr(current, segment)

    if isinstance(current, Field):
        current = current.value

    return current


class Unresolved(Enum):
    """Why a path did not resolve to a Field.

    Three outcomes the eval harness must tell apart (spec §3.2): a broken fixture, a row the
    document legitimately does not contain, and a document that names one identity twice.
    Collapsing them onto a single `None` makes the harness unable to distinguish a fixture
    it should report from one it should pass.
    """

    NO_SUCH_PATH = "no_such_path"
    NO_SUCH_ROW = "no_such_row"
    AMBIGUOUS = "ambiguous"


_SEGMENT = re.compile(r"(?P<name>[A-Za-z_]\w*)(?P<indexes>(?:\[\d+\])*)")
"""One path segment: an attribute name plus any positional indexes. Shared by both walks —
two copies of this pattern is how the type walk and the value walk start disagreeing."""

_INDEX = re.compile(r"\[(\d+)\]")


def _strip_optional(annotation: Any) -> Any:
    """`X | None` -> `X`. Anything else passes through untouched.

    `Identity.retroactive_date` is `Field[str] | None`, and the walk cares about the `Field`,
    not the nullability — an optional section is still addressable.
    """
    if get_origin(annotation) not in (Union, UnionType):
        return annotation
    args = [a for a in get_args(annotation) if a is not type(None)]
    return args[0] if len(args) == 1 else annotation


def _is_field(annotation: Any) -> bool:
    """True for `Field[...]`. Pydantic builds a concrete class per parametrization, so this
    is an ordinary subclass test rather than an origin check."""
    return isinstance(annotation, type) and issubclass(annotation, Field)


def _is_model(annotation: Any) -> TypeIs[type[BaseModel]]:
    """True for a model the walk may descend into.

    `Field` is excluded deliberately. It *is* a `BaseModel` subclass, so a plain subclass test
    would let the type walk step inside one — which `field_at` refuses to do. These two walks
    are only worth having while they agree, and agreeing by construction beats agreeing by
    coincidence.
    """
    return (
        isinstance(annotation, type)
        and issubclass(annotation, BaseModel)
        and not issubclass(annotation, Field)
    )


def _keyed_element_of(annotation: Any) -> type[BaseModel] | None:
    """Element type of a `list[...]` annotation whose elements declare `_match_key`."""
    if get_origin(annotation) is not list:
        return None
    args = get_args(annotation)
    if len(args) != 1:
        return None
    element = args[0]
    if not (isinstance(element, type) and issubclass(element, BaseModel)):
        return None
    return element if isinstance(getattr(element, "_match_key", None), str) else None


def _keyed_element(owner: type[BaseModel], name: str) -> type[BaseModel] | None:
    """Element type of `owner.name` when it is a list of models declaring `_match_key`.

    Type-level, not value-level: this is what lets `field_at` know a segment is addressing a
    keyed collection before it has an element in hand.
    """
    info = owner.model_fields.get(name)
    return None if info is None else _keyed_element_of(_strip_optional(info.annotation))


def _addressable(element: type[BaseModel], segments: Sequence[str]) -> bool:
    """Whether `segments` could resolve to a Field on `element`, had the row existed.

    The `field_at` walk run against `model_fields` instead of values. It answers "can this
    path ever resolve", never "does this document contain it" — which is what lets a row miss
    be told apart from a fixture naming a field that cannot exist (spec §3.2).
    """
    current: Any = element

    for segment in segments:
        keyed = _keyed_element_of(current)
        if keyed is not None:
            # The segment IS a match key: consume it and drop to the element type.
            current = keyed
            continue

        # A Field, an unkeyed list, or a leaf: the value walk stops here too.
        if not _is_model(current):
            return False

        match = _SEGMENT.fullmatch(segment)
        if match is None:
            return False

        info = current.model_fields.get(match["name"])
        if info is None:
            return False
        current = _strip_optional(info.annotation)

        for _ in _INDEX.findall(match["indexes"]):
            if get_origin(current) is not list:
                return False
            args = get_args(current)
            if len(args) != 1:
                return False
            current = _strip_optional(args[0])

    # An empty tail lands here: a row is not a Field, so addressing one is not addressing
    # a value.
    return _is_field(current)


def _match_in(items: list[Any], key: str) -> BaseModel | Unresolved:
    """The element of `items` whose declared match key equals `key`.

    Returns `AMBIGUOUS` when two rows claim the same key — a forms schedule carrying CG2010
    at two editions must not silently resolve to whichever sorted first, for the same reason
    `raster.find_text` refuses an ambiguous needle: a wrong row is worse than no row. This is
    not an edge case; `.spec/fixtures.md` records a document whose two schedules each omit
    forms the other lists, so merging them duplicates families by construction.

    Returns `NO_SUCH_ROW` when the collection is keyed but holds no such row — including when
    it is empty. That is what a manifest asserting `to: null` expects to see, so it must not
    read as a broken fixture.

    Returns `NO_SUCH_PATH` only when the collection cannot be keyed at all: elements that
    declare no `_match_key`, or that are not models — a `list[Field[str]]` such as
    `scheduled_parties` has no identity to key on and is addressed by position instead.

    An element whose resolved key is None never matches, not even another None. `_unwrap`
    collapses three situations into None (no such attribute, key present but null, wrapping
    Field had no value) and all three mean "this element has no identity". Letting them
    compare equal pairs two unidentifiable rows with each other — the phantom match §5.1
    exists to prevent. Comparison is exact and uncoerced: keys are normalized upstream, and
    casefolding here would make `field_at` disagree with how `compare` pairs the same
    objects.
    """
    matches: list[BaseModel] = []
    keyed = False
    for item in items:
        if not isinstance(item, BaseModel) or isinstance(item, Field):
            continue
        match_path = getattr(type(item), "_match_key", None)
        if not isinstance(match_path, str):
            continue

        keyed = True

        resolved_key = _unwrap(item, match_path)
        if resolved_key is None:
            continue
        if resolved_key == key:
            matches.append(item)

    if len(matches) > 1:
        return Unresolved.AMBIGUOUS
    if matches:
        return matches[0]
    if items and not keyed:
        return Unresolved.NO_SUCH_PATH
    return Unresolved.NO_SUCH_ROW


class PolicySnapshot(BaseModel):
    """One document, fully extracted. The unit the comparison engine consumes."""

    model_config = _FROZEN

    document: DocumentMeta
    identity: Identity
    general_liability: GeneralLiability
    property: Property
    forms_schedule: list[FormRef]
    risk_transfer: RiskTransfer
    exclusions: list[Exclusion]
    premium: Premium

    def field_at(self, path: str) -> Field[object] | Unresolved:
        """Resolve a dotted `field_path` (e.g. "general_liability.each_occurrence") to its Field.

        Manifests, findings, and the eval harness all address fields by string path
        (spec §3.2, §5.3). Deriving that from the model — rather than maintaining a
        hand-written path table — is what stops a newly added field from being silently
        skipped by the eval harness (see .spec/modules/contracts.md, failure modes).

        Collection members are addressed two ways: by position
        (`property.locations[0].valuation`) or by match key
        (`forms_schedule.CG0001.edition`). Prefer the key — §5.1 pairs forms and locations by
        key precisely because position is unstable between documents.

        Never raises. An unaddressable path is a data error the harness reports per pair, not
        a crash that kills the run; see `Unresolved` for how the three failure shapes differ.
        """
        current: object = self
        element: type[BaseModel] | None = None
        segments = path.split(".")

        for i, segment in enumerate(segments):
            if isinstance(current, list):
                if element is None:
                    return Unresolved.NO_SUCH_PATH
                found = _match_in(current, segment)
                # A missing row only means "this document lacks it" if the rest of the path
                # could have resolved. `forms_schedule.CG9999.nonsense` is broken twice over,
                # and without this check it reads as a passing absence — the silent-pass in
                # the measurement layer that `Unresolved` exists to prevent.
                if found is Unresolved.NO_SUCH_ROW and not _addressable(
                    element, segments[i + 1 :]
                ):
                    return Unresolved.NO_SUCH_PATH
                if isinstance(found, Unresolved):
                    return found
                current, element = found, None
                continue

            match = _SEGMENT.fullmatch(segment)
            if match is None:
                return Unresolved.NO_SUCH_PATH

            name = match["name"]
            if (
                not isinstance(current, BaseModel)
                or isinstance(current, Field)
                or name not in type(current).model_fields
            ):
                return Unresolved.NO_SUCH_PATH

            owner = type(current)
            current = getattr(current, name)
            element = _keyed_element(owner, name)

            for index_text in _INDEX.findall(match["indexes"]):
                if not isinstance(current, list):
                    return Unresolved.NO_SUCH_PATH

                index = int(index_text)
                if index >= len(current):
                    # Well-formed address into a real list, row not there — structurally the
                    # same as a keyed miss, so it answers the same way, including the tail
                    # check. A positional and a keyed address of the same absent row must not
                    # disagree. `element` is None for a list whose members carry no identity
                    # (`dba: list[Field[str]]`); there is no type to check the tail against,
                    # so those report the absence unqualified.
                    if element is not None and not _addressable(element, segments[i + 1 :]):
                        return Unresolved.NO_SUCH_PATH
                    return Unresolved.NO_SUCH_ROW

                current, element = current[index], None

        if not isinstance(current, Field):
            return Unresolved.NO_SUCH_PATH
        return cast(Field[object], current)
