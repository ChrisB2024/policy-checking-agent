"""`Unit` decides how a value renders, and rendering is what the AM actually reads.

`Scalar` is deliberately narrow — `bool | int | str` plus the sentinel — which means a money
limit, a coinsurance percent and a notice-days count are all bare `int` by the time they reach
a finding. `Unit` is what puts the semantics back for display, and a mis-set one is a `compare`
bug that surfaces as a wrong number in front of a client rather than as an exception.
"""

from typing import Any

import pytest

from policycheck.contracts import INCLUDED, FindingSide, Unit, Unresolved
from policycheck.contracts.finding import _UNIT_VALUE_TYPES


def _side(value: Any, unit: Unit) -> FindingSide:
    return FindingSide(value=value, unit=unit, page=1, source_text="x")


def test_every_unit_has_a_value_type() -> None:
    """Guards the lookup `_value_matches_unit` does — a missing entry is a KeyError at
    construction, on the object being built for a report.

    A test rather than a module-level `assert`, which `python -O` strips.
    """
    assert set(_UNIT_VALUE_TYPES) == set(Unit)


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (1_000_000, Unit.MONEY, "$1,000,000"),
        (0, Unit.MONEY, "$0"),  # $0 is a real limit, not an absence
        (INCLUDED, Unit.MONEY, "Included"),  # spec §4.3: not $0, not absent
        (90, Unit.PERCENT, "90%"),
        (30, Unit.DAYS, "30 days"),
        (1, Unit.DAYS, "1 day"),
        (True, Unit.FLAG, "Yes"),
        (False, Unit.FLAG, "No"),
        ("2025-04-01", Unit.DATE, "Apr 1, 2025"),
        ("CG0001", Unit.TEXT, "CG0001"),
    ],
)
def test_display_renders_by_unit(value: object, unit: Unit, expected: str) -> None:
    assert _side(value, unit).display() == expected


@pytest.mark.parametrize(
    ("label", "value", "unit"),
    [
        # `bool` subclasses `int`, so an isinstance check here would let True through as
        # money and render it "$1". The validator compares exact types for this reason.
        ("bool as money", True, Unit.MONEY),
        ("int as flag", 1, Unit.FLAG),
        ("str as money", "1000", Unit.MONEY),
        ("int as date", 20250401, Unit.DATE),
    ],
)
def test_unit_must_match_the_value_type(label: str, value: object, unit: Unit) -> None:
    with pytest.raises(ValueError, match="expects"):
        _side(value, unit)


def test_date_unit_requires_iso_8601() -> None:
    """`retro_date_advanced` compares dates. A `04/13` that validated as a date would order
    wrongly against a real one, and edition strings look exactly like that."""
    with pytest.raises(ValueError, match="ISO 8601"):
        _side("04/13", Unit.DATE)


def test_absent_side_renders_nothing() -> None:
    """`report` supplies the "absent" wording — `display()` speaks for values only, so the
    two sides of a removed endorsement are worded in one place rather than two."""
    assert FindingSide(absent=Unresolved.NO_SUCH_ROW, unit=Unit.MONEY).display() is None
