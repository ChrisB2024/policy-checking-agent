"""CourtListener RECAP client — search and download, under a hard request budget.

Docs: https://wiki.free.law/c/courtlistener/help/api/rest/v4/search
      https://wiki.free.law/c/courtlistener/help/api/rest/v4/pacer-data

Two things drive the design:

1. **`type=rd`, not `type=r`.** `r` returns dockets with up to three nested documents, which
   forces the caller to walk into each docket to find the actual filing. `rd` returns filing
   documents directly. Same information, one fewer layer, and no extra requests.

2. **`is_available` gates everything.** `filepath_local` is only populated when the binary is
   actually stored. Most RECAP rows are metadata scraped from PACER dockets with no PDF
   behind them. Filtering on this before downloading is the difference between spending the
   daily budget on policies and spending it on 404s.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from policycheck.config import settings
from policycheck.corpus.quota import QuotaLedger

SEARCH_URL = "https://www.courtlistener.com/api/rest/v4/search/"

# `filepath_local` is a relative path (e.g. "recap/gov.uscourts.dcd.178502/....pdf"), not a
# URL — this is the host it hangs off. Confirm against a live response on first run; if it
# 404s, check the search result for an absolute URL field and prefer that.
STORAGE_BASE = "https://storage.courtlistener.com/"

# `plain_text` can be megabytes per document and we do not need it at search time — we screen
# the PDF locally after download. Excluding it materially cuts response size.
SEARCH_FIELDS = (
    "id,docket_id,description,short_description,page_count,is_available,"
    "filepath_local,absolute_url,court,dateFiled,caseName,attachment_number"
)


@dataclass(frozen=True)
class Candidate:
    """One RECAP document that might be a policy. Metadata only — nothing downloaded yet."""

    doc_id: int
    docket_id: int | None
    case_name: str
    court: str
    description: str
    page_count: int | None
    is_available: bool
    filepath_local: str | None
    absolute_url: str | None
    attachment_number: int | None = None

    @property
    def pdf_url(self) -> str | None:
        """Absolute URL for the cached PDF, or None when there is no binary to fetch."""
        if not self.is_available or not self.filepath_local:
            return None
        return STORAGE_BASE + self.filepath_local.lstrip("/")

    @staticmethod
    def _attachment_from_path(filepath: str | None) -> int | None:
        """Recover the attachment number from the stored filename.

        RECAP paths encode docket entry and attachment, e.g.
        `recap/gov.uscourts.dcd.119033.41.1.pdf` is entry 41, attachment 1. Used as a
        fallback because `attachment_number` is not always populated in search results.
        """
        if not filepath:
            return None
        parts = filepath.rsplit("/", 1)[-1].removesuffix(".pdf").split(".")
        if len(parts) >= 2 and parts[-1].isdigit() and parts[-2].isdigit():
            return int(parts[-1])
        return None

    @classmethod
    def from_result(cls, r: dict[str, Any]) -> "Candidate":
        # The search API mixes camelCase and snake_case across result types; read defensively
        # and prefer the longer description when both are present.
        #
        # NOTE: `caseName` and `court` come back empty for type=rd in practice, and
        # `description` is the *parent docket entry's* — it lists every attachment, not just
        # this document. triage.attachment_label() narrows it using the attachment number.
        description = r.get("description") or r.get("short_description") or ""
        filepath = r.get("filepath_local")
        return cls(
            doc_id=int(r.get("id", 0)),
            docket_id=r.get("docket_id"),
            case_name=r.get("caseName") or r.get("case_name") or "",
            court=r.get("court") or "",
            description=description,
            page_count=r.get("page_count"),
            is_available=bool(r.get("is_available")),
            filepath_local=filepath,
            absolute_url=r.get("absolute_url"),
            attachment_number=r.get("attachment_number") or cls._attachment_from_path(filepath),
        )


class CourtListenerClient:
    """Rate-limit-aware CourtListener client.

    Every call goes through the on-disk quota ledger. There is no bypass — a 125/day budget
    does not survive a code path that "just checks one thing" without recording it.
    """

    def __init__(self, token: str | None = None, ledger: QuotaLedger | None = None) -> None:
        # Falls through to .env via config.settings(); an explicit token still wins.
        self.token = token or settings().require_courtlistener_token()
        self.ledger = ledger or QuotaLedger()
        # "Token", not "Bearer" — the docs call this out as the most common mistake.
        self._client = httpx.Client(
            headers={"Authorization": f"Token {self.token}"},
            timeout=60.0,
            follow_redirects=True,
        )

    def search(self, query: str, page: int = 1, doc_type: str = "rd") -> list[Candidate]:
        """One search request. Returns candidates; downloads nothing.

        Searches are the cheap end of the budget — a single request yields many candidates
        with the metadata needed to rank them. Spend requests here, not on speculative
        downloads.
        """
        self.ledger.wait_for_slot()
        self.ledger.spend()
        resp = self._client.get(
            SEARCH_URL,
            params={"q": query, "type": doc_type, "page": page, "fields": SEARCH_FIELDS},
        )
        resp.raise_for_status()
        return [Candidate.from_result(r) for r in resp.json().get("results", [])]

    def download(self, candidate: Candidate, dest: Path) -> Path:
        """Fetch one candidate's PDF. Costs one request from the budget."""
        url = candidate.pdf_url
        if url is None:
            raise ValueError(
                f"Document {candidate.doc_id} has no stored binary "
                f"(is_available={candidate.is_available}). It should have been filtered out "
                f"before reaching download()."
            )
        self.ledger.wait_for_slot()
        self.ledger.spend()
        resp = self._client.get(url)
        resp.raise_for_status()

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return dest

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CourtListenerClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
