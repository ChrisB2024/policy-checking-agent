"""The finding taxonomy must not drift from spec §5.2.

Manifests address finding types by string (`expected_finding_type`, spec §3.2), so a member
whose value drifts is a fixture that silently never matches — and a type the spec names but
the enum lacks is a finding the engine can never emit. Both happened once already: four
members had drifted to past tense and seventeen were missing, including all four decoys.

This parses the spec rather than restating it, so the check cannot itself go stale.
"""

import re
from pathlib import Path

import pytest

from policycheck.contracts import FindingType, Severity

SPEC = Path(__file__).parents[2] / "spec.md"

# `| `type_name` | trigger text | severity |` — the severity column is what distinguishes
# the §5.2 taxonomy table from the other tables in the spec.
_ROW = re.compile(r"\|\s*`([a-z_]+)`\s*\|([^|]*)\|\s*\**([a-z_]+)\**\s*\|")


def _spec_rows() -> list[tuple[str, str]]:
    """(finding_type, severity) for every row of the §5.2 table."""
    rows = [
        (m.group(1), m.group(3))
        for line in SPEC.read_text().splitlines()
        if (m := _ROW.match(line))
    ]
    assert rows, "parsed no rows out of spec §5.2 — the table format changed"
    return rows


def test_spec_table_is_parseable() -> None:
    """Guards the other two tests: a silently-empty parse would make them vacuously pass."""
    assert len(_spec_rows()) >= 26


@pytest.mark.parametrize(("name", "severity"), _spec_rows(), ids=lambda v: str(v))
def test_spec_type_exists_in_enum(name: str, severity: str) -> None:
    """Every type spec §5.2 names is emittable."""
    assert name in {t.value for t in FindingType}, (
        f"spec §5.2 names `{name}` but FindingType has no member with that value — "
        f"`compare` cannot emit it and no manifest can assert it"
    )
    assert severity in {s.value for s in Severity}, (
        f"spec §5.2 gives `{name}` severity `{severity}`, which is not a Severity member"
    )


def test_enum_carries_nothing_the_spec_does_not_list() -> None:
    """The spec is the single source, not a Python set kept alongside it.

    A member here that §5.2 doesn't name is a finding the engine can emit and no manifest can
    assert — invisible to the eval harness by construction. Adding one is a spec edit first;
    this test is what makes that the path of least resistance rather than a habit to keep.
    """
    beyond = {t.value for t in FindingType} - {name for name, _ in _spec_rows()}
    assert not beyond, (
        f"FindingType has members spec §5.2 does not list: {sorted(beyond)}. Add the rows "
        f"to §5.2 with their severities rather than recording the exception here."
    )


def test_no_duplicate_rows() -> None:
    """A type listed twice can carry two severities, and which one `compare/rules.py` picks
    is then whichever the reader saw first."""
    names = [name for name, _ in _spec_rows()]
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates, f"spec §5.2 lists these more than once: {sorted(duplicates)}"
