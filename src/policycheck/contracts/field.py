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

from typing import Any, ClassVar, Self, final

from pydantic import BaseModel, ConfigDict, GetCoreSchemaHandler, model_validator
from pydantic import Field as PydanticField
from pydantic_core import core_schema

from policycheck.contracts.enums import Confidence, ValueBasis

# PDF user space, origin bottom-left: [x0, y0, x1, y1]. See .spec/modules/raster.md —
# this is the only coordinate space in the pipeline; the web layer converts, nothing else.
type BBox = tuple[float, float, float, float]


@final
class IncludedSentinel:
    """Marker for a limit printed as "Included" / "Incl." on the dec page.

    Deliberately NOT `0` and NOT `None`. "$0" and "Included" mean opposite things, and
    conflating them produces a phantom `limit_decrease` (spec §4.3).
    """

    _instance: ClassVar["IncludedSentinel | None"] = None

    def __new__(cls) -> "IncludedSentinel":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "INCLUDED"

    def __bool__(self) -> bool:
        return True

    def __eq__(self, other: object) -> bool:
        return other is self

    def __hash__(self) -> int:
        # Required: defining __eq__ sets __hash__ = None, and Field is frozen (hashable).
        return hash(IncludedSentinel)

    def __copy__(self) -> "IncludedSentinel":
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> "IncludedSentinel":
        return self

    def __reduce__(self) -> str:
        return "INCLUDED"  # pickle resolves the module-level name, preserving identity

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        def _serialize(value: Any) -> str:
            # MUST reject non-sentinels
            if not isinstance(value, IncludedSentinel):
                raise ValueError("not the INCLUDED sentinel")
            return "INCLUDED"

        from_str = core_schema.chain_schema([
            core_schema.literal_schema(["INCLUDED"]),
            core_schema.no_info_plain_validator_function(lambda _: INCLUDED),
        ])
        return core_schema.json_or_python_schema(
            json_schema=from_str,
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(cls),
                from_str,
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                _serialize,
                return_schema=core_schema.str_schema(),
                when_used="json"
            )
        )

INCLUDED = IncludedSentinel()
"""The single instance. Compare with `is`, not `==`."""


type Money = int | IncludedSentinel
"""A limit or amount, which may be printed as "Included" rather than a number.

Use `Field[Money]` for anything that appears in a limit or deductible column, and plain
`Field[int]` / `Field[str]` everywhere else. The sentinel rides on the *type parameter*, not
on `Field` itself, for two reasons:

  - `Field[str]` would otherwise carry a `{"const": "INCLUDED"}` branch in its JSON schema.
    That schema is the extractor's prompt surface, and offering "INCLUDED" as a legal value
    for `named_insured` is noise the model has to reason past.
  - With the sentinel in `Field`'s own union, a `Field[str]` given the literal string
    "INCLUDED" resolves to a plain `str` in Python mode and to the sentinel in JSON mode.
    Scoping it to `Money` makes both modes agree.
"""


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
    #   value: T | None            — NOT `T | IncludedSentinel | None`. The sentinel rides
    #                                on the type parameter: use `Field[Money]` for limits and
    #                                deductibles, `Field[int]` / `Field[str]` elsewhere.
    #                                See the `Money` docstring above for why.
    #   raw: str | None            — the value exactly as printed
    #   page: int | None           — 1-INDEXED (raster converts at the boundary)
    #   bbox: BBox | None
    #   source_text: str | None    — VERBATIM from the page, never paraphrased.
    #                                raster.find_text matches on this to produce bbox.
    #   confidence: Confidence
    #   extraction_passes_agreed: bool
    #   basis: ValueBasis | None   — why value is None, when it is (excluded vs absent)
    #
    # Use PydanticField(...) for defaults and descriptions. The d escriptions are not
    # decoration: this model becomes the JSON schema the extractor is constrained to, so
    # each description is prompt surface the model actually reads. Say "verbatim" in the
    # source_text description.

    value: T | None = PydanticField(
        default=None,
        description=(
            "The normalized value. Null when the coverage does not appear in the "
            "document or is affirmatively excluded — set `basis` to say which. Never "
            "guess: a null with a basis is correct, an inferred value is not."
        )
    )
    raw: str | None = PydanticField(
        default=None,
        description=(
            "The value exactly as printed on the page — currency symbols, thousands "
            "separators, and wording such as 'Included' or 'Incl.' preserved. Do not "
            "reformat or normalize."
        ),
    )
    page: int | None = PydanticField(
        default=None,
        ge=1,
        description=(
            "1-indexed page number of the page this value was read from. The first "
            "page of the document is page 1."
        ),
    )
    bbox: BBox | None = PydanticField(
        default=None,
        description=(
            "Bounding box in PDF user space, origin bottom-left, [x0, y0, x1, y1]. "
            "Leave null — this is resolved downstream by matching `source_text` "
            "against the page. A wrong box is worse than no box."
        )
    )
    source_text: str | None = PydanticField(
        default=None,
        description=(
            "The line of text on the page containing this value, copied verbatim — "
            "character for character, including internal spacing and punctuation. "
            "Never paraphrase, reorder, or summarize. This exact string is matched "
            "back against the page to locate the value; a paraphrase matches nothing "
            "and the citation is lost."
        ),
    )
    # These two default rather than being required, so the extraction schema does not
    # demand the very fields its descriptions tell the model not to set. LOW/False is the
    # fail-safe pair: a Field that never went through the merge step has not earned
    # confidence, and LOW routes it to needs_review — visible doubt rather than a claim of
    # agreement that never happened (spec invariant 3).
    confidence: Confidence = PydanticField(
        default=Confidence.LOW,
        description=(
            "Set by the merge step from cross-pass agreement, not self-reported. "
            "`not_found` means no value was located anywhere in the document."
        ),
    )
    extraction_passes_agreed: bool = PydanticField(
        default=False,
        description=(
            "True when both independent extraction passes produced the same "
            "normalized value. Set by the merge step."
        ),
    )
    basis: ValueBasis | None = PydanticField(
        default=None,
        description=(
            "Why `value` is null. `excluded` when the document affirmatively shows "
            "the coverage removed or excluded; `absent` when it simply does not "
            "appear. Meaningless when `value` is present."
        ),
    )


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
