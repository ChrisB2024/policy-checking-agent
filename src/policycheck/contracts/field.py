"""The universal value envelope.

Every extracted value in the pipeline is wrapped in `Field[T]`. There are no bare values
anywhere downstream of extraction (spec §4.1). The envelope is what makes spec invariant 2
enforceable: a value that cannot cite where it came from does not appear in output.

Target shape (spec §4.1):

    {
      "value": 1000000,
      "raw": "$1,000,000",
      "page": 3,
      "bbox": [122.4, 388.1, 244.9, 401.7],
      "source_text": "Each Occurrence Limit    $1,000,000",
      "confidence": "high",
      "extraction_passes_agreed": true
    }

NOTE: `pydantic.Field` and our `Field` collide. In this file pydantic's is imported as
`PydanticField`. Elsewhere, import ours as `from policycheck.contracts import Field`.
"""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic import Field as PydanticField  # noqa: F401  — used by the TODO(human) below

from policycheck.contracts.enums import Confidence, ValueBasis  # noqa: F401  — same

# PDF user space, origin bottom-left: [x0, y0, x1, y1]. See .spec/modules/raster.md —
# this is the only coordinate space in the pipeline; the web layer converts, nothing else.
type BBox = tuple[float, float, float, float]


class IncludedSentinel:
    """Marker for a limit printed as "Included" / "Incl." on the dec page.

    Deliberately NOT `0` and NOT `None`. "$0" and "Included" mean opposite things, and
    conflating them produces a phantom `limit_decrease` (spec §4.3).
    """

    # TODO(human): make this a proper singleton that survives Pydantic validation and
    # JSON round-tripping, and that pyright can narrow on.
    #   - `__repr__` returning "INCLUDED"
    #   - `__bool__` returning True (it IS coverage, unlike 0)
    #   - equality: only equal to itself
    #   - a `__get_pydantic_core_schema__` classmethod so Pydantic serializes it as the
    #     string "INCLUDED" and parses that string back into the singleton
    # Read: https://docs.pydantic.dev/latest/concepts/types/#customizing-validation-with-__get_pydantic_core_schema__


# TODO(human): instantiate the singleton, e.g. `INCLUDED = IncludedSentinel()`


class Field[T](BaseModel):
    """A single extracted value plus the evidence for it.

    Invariants this model must enforce (see the validator below):
      - `confidence != NOT_FOUND` implies `page` and `source_text` are both present.
        No uncited claims (spec invariant 2).
      - `confidence == NOT_FOUND` implies `value is None`.
      - `bbox` is nullable and stays that way. Scanned pages resolve no box, and a *wrong*
        box is far worse than none — it breaks spec invariant 7.
    """

    model_config = ConfigDict(frozen=True)

    # TODO(human): declare the envelope fields.
    #
    #   value: T | IncludedSentinel | None
    #   raw: str | None            — the value exactly as printed
    #   page: int | None           — 1-INDEXED (raster converts at the boundary)
    #   bbox: BBox | None
    #   source_text: str | None    — VERBATIM from the page, never paraphrased.
    #                                raster.find_text matches on this to produce bbox.
    #   confidence: Confidence
    #   extraction_passes_agreed: bool
    #   basis: ValueBasis | None   — why value is None, when it is (excluded vs absent)
    #
    # Use PydanticField(...) for defaults and descriptions. The descriptions are not
    # decoration: this model becomes the JSON schema the extractor is constrained to, so
    # each description is prompt surface the model actually reads. Say "verbatim" in the
    # source_text description.

    @model_validator(mode="after")
    def _citation_required(self) -> Self:
        """Reject any field that claims a value without evidence for it."""
        # TODO(human): implement the three invariants from the docstring above.
        # Raise ValueError with a message that names the field path being validated —
        # this fires during extraction parsing, and a bare "validation error" there is
        # painful to debug against a 60-page PDF.
        return self

    @classmethod
    def not_found(cls) -> "Field[T]":
        """The canonical absent field. Used when the extractor cannot locate a value."""
        # TODO(human): return a Field with confidence=NOT_FOUND, value=None,
        # basis=ValueBasis.ABSENT, extraction_passes_agreed=True (both passes agreed it
        # was absent — disagreement is set by the merge step, not here).
        raise NotImplementedError

    @property
    def needs_review(self) -> bool:
        """True when this field must surface as `needs_review` rather than as a value.

        Both LOW and NOT_FOUND qualify. `compare` uses this to decide whether a field is
        eligible to produce a substantive finding at all (spec §5.2, `low_confidence_field`).
        """
        # TODO(human)
        raise NotImplementedError

    @property
    def is_cited(self) -> bool:
        """True when a human could follow this field to its source in under 90 seconds."""
        # TODO(human): page present is the bar. bbox is a nice-to-have; its absence
        # degrades the UI jump, not the citation.
        raise NotImplementedError


def agreement(a: "Field[Any]", b: "Field[Any]") -> Confidence:
    """Confidence for a field extracted independently by two passes (spec §10).

    Comparison is on the NORMALIZED value, not the raw string — normalize runs before this,
    so "$1,000,000" and "1,000,000" agree. Comparing raw strings would flood the `low`
    bucket with formatting noise and make `needs_review` useless.

        both agree on a value        -> HIGH
        disagree                     -> LOW
        one has a value, one not_found -> LOW
        both not_found               -> NOT_FOUND
    """
    # TODO(human): implement. This is the rule that makes the needs_review bucket honest —
    # it is the entire justification for paying 2x on extraction.
    raise NotImplementedError
