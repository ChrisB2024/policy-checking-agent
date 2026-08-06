"""Deciding which candidates are worth spending a download on, and which downloads are keepers.

The corpus needs 15–20 *complete* commercial package policies — dec page, forms schedule, and
the endorsements themselves. A full-text search for "commercial general liability" returns
mostly complaints, motions, and certificates of insurance that merely mention one. At 125
requests/day, downloading blind wastes the entire budget on junk.

So there are two gates:

  1. `rank()`      — metadata only, before any download. Free.
  2. `screen()`    — the downloaded PDF. Costs nothing further; the request is already spent.

Neither gate decides anything on its own. They produce a ranked shortlist a human confirms
(`pc corpus add`). Whether a PDF is genuinely a complete policy is a judgment call, and
getting it wrong poisons every eval run downstream.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

from policycheck.corpus.courtlistener import Candidate
from policycheck.raster import page_text

# A complete commercial package policy runs long. Below ~25 pages it is almost certainly a
# certificate, a dec page on its own, or an excerpt; above ~400 it is usually a merged
# exhibit bundle containing several unrelated documents.
IDEAL_PAGES = range(40, 200)
PLAUSIBLE_PAGES = range(25, 400)

# Docket descriptions that suggest an exhibit rather than a brief.
PROMISING = re.compile(
    r"\b(polic|exhibit|declaration|endorsement|coverage\s+(?:part|form)|insuring)", re.I
)
# Descriptions that are almost never the policy itself.
UNPROMISING = re.compile(
    r"\b(motion|order|brief|memorand|complaint|answer|summons|notice\s+of|transcript|"
    r"affidavit|certificate\s+of\s+service|proposed|stipulation|scheduling)",
    re.I,
)

# Screening-only heuristic for "does this look like a forms schedule". Deliberately NOT the
# canonicalizer — that lives in `normalize` (spec §4.3) and is the highest-leverage code in
# the build. This one only needs to answer "are there a lot of form numbers here"; keep the
# two separate so nobody tunes the real one against screening results.
FORM_NUMBER = re.compile(r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?(?:\d{2}\s?\d{2})?\b")

DEC_MARKERS = ("DECLARATIONS", "DECLARATION PAGE", "COMMON POLICY DECLARATIONS")
SCHEDULE_MARKERS = (
    "FORMS AND ENDORSEMENTS",
    "SCHEDULE OF FORMS",
    "FORMS SCHEDULE",
    "LISTING OF FORMS",
    "FORMS APPLICABLE",
)
LOB_MARKERS = ("COMMERCIAL GENERAL LIABILITY", "COMMERCIAL PROPERTY", "BUILDING AND PERSONAL")


# Attachment lists inside a docket description, e.g.
#   "(Attachments: # 1 Exhibit A - Notice, # (2) A copy of policy number ALTE003493 ...)"
# Numbering appears both bare and parenthesised.
ATTACHMENT_ITEM = re.compile(r"#\s*\(?(\d+)\)?\s*([^#]*)")


def attachment_label(description: str, attachment_number: int | None) -> str:
    """Pull one attachment's own label out of its parent docket entry description.

    Search results for `type=rd` carry the *entry* description, which lists every
    attachment. Scoring that whole string means a policy filed as exhibit 7 of an answer
    gets judged on the word "ANSWER". Narrowing to the attachment's own text is what turns
    "ANSWER to Counterclaim" into "Exhibit G - Commercial General Liability Declarations".

    Falls back to the full description when there is no attachment list to index into.
    """
    if attachment_number is None or "#" not in description:
        return description
    for num, label in ATTACHMENT_ITEM.findall(description):
        if int(num) == attachment_number:
            return label.strip(" ,);")
    return description


@dataclass(frozen=True)
class Ranked:
    candidate: Candidate
    score: int
    reasons: list[str]
    label: str = ""
    """The attachment's own description, when it could be isolated. This is what was
    actually scored — show it rather than the parent entry's text."""


def rank(candidates: list[Candidate]) -> list[Ranked]:
    """Score candidates on metadata alone. Highest first. Downloads nothing.

    Candidates with no stored binary are dropped outright — `filepath_local` is only valid
    when `is_available` is true, so these cannot be fetched at any price.
    """
    ranked: list[Ranked] = []
    for c in candidates:
        if not c.is_available or not c.filepath_local:
            continue

        score = 0
        reasons: list[str] = []

        if c.page_count is None:
            reasons.append("no page_count (unknown length)")
        elif c.page_count in IDEAL_PAGES:
            score += 40
            reasons.append(f"{c.page_count}pp — typical complete policy")
        elif c.page_count in PLAUSIBLE_PAGES:
            score += 15
            reasons.append(f"{c.page_count}pp — plausible")
        else:
            score -= 30
            reasons.append(f"{c.page_count}pp — too {'short' if c.page_count < 25 else 'long'}")

        # Score this attachment's own label, not the parent entry's full description.
        label = attachment_label(c.description, c.attachment_number)
        if PROMISING.search(label):
            score += 25
            reasons.append("label suggests an exhibit/policy")
        if UNPROMISING.search(label):
            score -= 25
            reasons.append("label suggests a pleading")

        ranked.append(Ranked(candidate=c, score=score, reasons=reasons, label=label))

    return sorted(ranked, key=lambda r: r.score, reverse=True)


@dataclass(frozen=True)
class Screening:
    """What a downloaded PDF actually turned out to be."""

    path: Path
    page_count: int
    text_pages: int
    """Pages with a usable text layer. 0 means fully scanned — still valuable (spec §3.2
    wants at least two image-only pairs), but it changes how the document is used."""
    has_dec_page: bool
    has_forms_schedule: bool
    has_target_lob: bool
    form_number_hits: int

    @property
    def is_scanned(self) -> bool:
        return self.text_pages == 0

    @property
    def looks_complete(self) -> bool:
        """Dec page plus a forms schedule — the minimum for a usable base document.

        A dec page alone cannot exercise most of the findings taxonomy; roughly half the
        findings that matter live in the endorsements (see README).
        """
        return self.has_dec_page and self.has_forms_schedule

    def verdict(self) -> str:
        if self.is_scanned:
            return "scanned — needs manual review, and counts toward the image-only quota"
        if self.looks_complete and self.has_target_lob:
            return "strong candidate"
        if self.has_dec_page and not self.has_forms_schedule:
            return "dec page only — not usable on its own"
        if not self.has_target_lob:
            return "no GL/property markers — probably the wrong line of business"
        return "unclear — review by hand"


def screen(path: Path, sample_pages: int = 60) -> Screening:
    """Inspect a downloaded PDF for the markers of a complete package policy.

    Samples the first `sample_pages` pages rather than the whole document: dec page and forms
    schedule appear near the front, and exhibit bundles can run to thousands of pages.

    Sampling is safe here only because this is a *filter*. A human confirming the document
    must read all of it — see `.spec/fixtures.md`, where the real forms schedule and limit
    breakout both sat on page 9 behind a cover note showing neither.
    """
    doc = pdfium.PdfDocument(path)
    try:
        total = len(doc)
        limit = min(total, sample_pages)

        text_pages = 0
        chunks: list[str] = []
        for n in range(1, limit + 1):
            pt = page_text(doc, n)  # raster owns ECF-stamp stripping and the density threshold
            if pt.has_text_layer:
                text_pages += 1
            chunks.append(pt.body.upper())

        body = "\n".join(chunks)
        return Screening(
            path=path,
            page_count=total,
            text_pages=text_pages,
            has_dec_page=any(m in body for m in DEC_MARKERS),
            has_forms_schedule=any(m in body for m in SCHEDULE_MARKERS),
            has_target_lob=any(m in body for m in LOB_MARKERS),
            # A real forms schedule lists dozens. A brief that quotes one form lists one or two.
            form_number_hits=len(set(FORM_NUMBER.findall(body))),
        )
    finally:
        doc.close()
