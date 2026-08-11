"""A `FindingSide` must survive JSON without changing meaning.

Findings are persisted (`.spec/modules/persistence.md`), served over the API, and read back
by the eval harness, so every one of those paths is a JSON round-trip. `value` is a union
resolved by guessing from a JSON scalar, and JSON has fewer types than Python — which is
where the meaning gets lost.

In-memory construction is not the same test and passes today; these all go through JSON on
purpose.
"""

from typing import Any, get_args

import pytest

from policycheck.contracts import (
    INCLUDED,
    FindingSide,
    IncludedSentinel,
    Scalar,
    Unresolved,
)


def _cited(value: Any) -> FindingSide:
    return FindingSide(value=value, page=3, source_text="Each Occurrence Limit  $1,000,000")


def _roundtrip(side: FindingSide) -> FindingSide:
    return FindingSide.model_validate_json(side.model_dump_json())


@pytest.mark.parametrize(
    ("label", "value"),
    [
        # Strings that look like other types. These are real schema values, and the type
        # they land as is the type the report renders.
        ("policy_number", "12345"),
        ("naic_code", "23035"),
        ("zip5", "02134"),  # a leading zero is data, not formatting
        ("iso_date", "2025-01-01"),  # snapshot stores dates as ISO strings, not `date`
        ("form_edition", "04/13"),
        ("form_family", "CG0001"),
        ("enum_value", "acv"),
        # Genuine non-strings.
        ("money", 1_000_000),
        ("bool_true", True),
        ("bool_false", False),
        ("zero", 0),  # must not become False
    ],
)
def test_value_keeps_its_type_through_json(label: str, value: object) -> None:
    assert type(_roundtrip(_cited(value)).value) is type(value), (
        f"{label}: a {type(value).__name__} came back as something else. `value` is a union "
        f"and JSON cannot tell its members apart — narrow the union rather than reordering it"
    )


def test_included_sentinel_survives() -> None:
    """A limit printed "Included" is neither $0 nor absent (spec §4.3).

    The sentinel exists to stop `Included -> $50,000` reading as a phantom `limit_decrease`.
    If it cannot cross into a finding, `compare` has to coerce it — and the only coercions
    available are the two the sentinel was built to prevent.
    """
    assert _roundtrip(_cited(INCLUDED)).value is INCLUDED


@pytest.mark.parametrize("reason", list(Unresolved))
def test_absent_side_survives(reason: Unresolved) -> None:
    """An absent side is half of every added/removed finding, so this is not an edge case.

    `prior` and `current` are both required even when one side is not there — the report
    renders "absent" explicitly rather than omitting the row (spec §5.3).
    """
    back = _roundtrip(FindingSide(absent=reason))
    assert back.is_present is False
    assert back.absent is reason
    assert back.value is None


def test_a_side_is_present_or_absent_never_both_and_never_neither() -> None:
    """The two fields are one decision expressed as two attributes, so the type system
    cannot enforce it — the validator has to."""
    with pytest.raises(ValueError, match="exactly one of value/absent"):
        FindingSide(value=1, absent=Unresolved.NO_SUCH_ROW, page=1, source_text="x")
    with pytest.raises(ValueError, match="says nothing"):
        FindingSide()


def test_present_side_keeps_its_citation() -> None:
    side = _roundtrip(_cited(1_000_000))
    assert side.is_present is True
    assert side.page == 3
    assert side.source_text is not None


def test_derived_value_carries_provenance_instead_of_a_citation() -> None:
    """A premium delta is real, appears on no page, and must still be checkable.

    `derived_from` keeps spec invariant 7 one hop out — the reader follows the delta to the
    two totals it came from, each of which is cited. A derived side may therefore carry no
    citation at all, `raw` included: it was never printed.
    """
    side = _roundtrip(
        FindingSide(value=4650, derived_from=("premium.total", "premium.taxes_fees"))
    )
    assert side.derived is True
    assert side.derived_from == ("premium.total", "premium.taxes_fees")

    provenance = ("premium.total",)
    with pytest.raises(ValueError, match="derived value"):
        FindingSide(value=4650, derived_from=provenance, page=3)
    with pytest.raises(ValueError, match="derived value"):
        FindingSide(value=4650, derived_from=provenance, source_text="Total Premium $4,650")
    with pytest.raises(ValueError, match="derived value"):
        FindingSide(value=4650, derived_from=provenance, raw="$4,650")


def test_derived_is_not_a_flag_that_can_be_set_on_its_own() -> None:
    """`derived` reads off `derived_from`, so the citation requirement cannot be switched
    off without naming what the value came from."""
    assert "derived" not in FindingSide.model_fields
    assert FindingSide(value=1, page=1, source_text="x").derived is False


def test_scalar_stays_narrow() -> None:
    """Each member of `Scalar` is another type the union guesses between from a JSON scalar.

    `Decimal` and `date` were both members and both corrupted real values on the way back —
    a ZIP lost its leading zero, an ISO date became a `date`. Neither had a producer. Growing
    this union is how those come back, so it is worth failing loudly on.
    """
    assert set(get_args(Scalar.__value__)) == {IncludedSentinel, bool, int, str}
