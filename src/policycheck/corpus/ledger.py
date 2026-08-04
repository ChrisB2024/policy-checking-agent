"""Provenance for every document in the corpus.

`corpus/ledger.json` is tracked in git; the PDFs it describes are not (see README). It is
what makes the corpus reproducible by someone who clones the repo: every entry carries a
`source_url` a stranger could follow.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

DEFAULT_LEDGER = Path("corpus/ledger.json")


class CorpusEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    doc_id: str
    source: str  # courtlistener | gov | risk_pool | serff | specimen
    source_url: str
    retrieved_at: str
    page_count: int
    has_scanned_pages: bool
    carrier: str | None = None
    notes: str | None = None


class CorpusLedger:
    def __init__(self, path: Path = DEFAULT_LEDGER) -> None:
        self.path = path
        self.entries: list[CorpusEntry] = self._load()

    def _load(self) -> list[CorpusEntry]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text())
        return [CorpusEntry(**e) for e in raw.get("documents", [])]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"documents": [e.model_dump() for e in self.entries]}
        self.path.write_text(json.dumps(payload, indent=2) + "\n")

    def add(self, entry: CorpusEntry) -> None:
        if any(e.doc_id == entry.doc_id for e in self.entries):
            raise ValueError(f"{entry.doc_id} is already in the ledger")
        self.entries.append(entry)
        self.save()

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")

    def coverage(self) -> dict[str, int]:
        """Progress against the spec §3.2 corpus targets."""
        return {
            "documents": len(self.entries),
            "carriers": len({e.carrier for e in self.entries if e.carrier}),
            "scanned": sum(1 for e in self.entries if e.has_scanned_pages),
        }
