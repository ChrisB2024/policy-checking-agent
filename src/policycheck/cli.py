"""`pc` — the project CLI.

Every pipeline stage is runnable standalone from here before it has a UI. Right now that is
corpus sourcing; extract/compare/report/eval land in later chunks.
"""

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from policycheck.config import settings
from policycheck.corpus.courtlistener import Candidate, CourtListenerClient
from policycheck.corpus.ledger import CorpusEntry, CorpusLedger
from policycheck.corpus.quota import QuotaLedger
from policycheck.corpus.triage import rank, screen

app = typer.Typer(help="Policy Check CLI", no_args_is_help=True)
corpus_app = typer.Typer(help="Source and screen the document corpus", no_args_is_help=True)
app.add_typer(corpus_app, name="corpus")

console = Console()


@app.command("config")
def config_cmd() -> None:
    """Show what settings actually loaded. Secrets are masked."""
    s = settings()
    table = Table("Setting", "Value", "Source", box=None)
    for name, value in (
        ("ANTHROPIC_API_KEY", s.anthropic_api_key),
        ("COURTLISTENER_API_TOKEN", s.courtlistener_api_token),
    ):
        raw = value.get_secret_value() if value else ""
        shown = f"[green]set[/green] (…{raw[-4:]})" if raw else "[red]missing[/red]"
        table.add_row(name, shown, ".env or environment")
    for name, value in (
        ("DATABASE_URL", s.database_url),
        ("EXTRACTION_MODEL", s.extraction_model),
        ("EXTRACTION_PASSES", str(s.extraction_passes)),
        ("DEMO_MODE", str(s.demo_mode)),
        ("RASTER_CACHE_DIR", str(s.raster_cache_dir)),
    ):
        table.add_row(name, str(value), "")
    console.print(table)
    if not Path(".env").exists():
        console.print("\n[yellow]No .env found. Run: cp .env.example .env[/yellow]")

CANDIDATES = Path("corpus/.candidates.json")
RAW_DIR = Path("corpus/raw")


@corpus_app.command("quota")
def quota_cmd() -> None:
    """Show remaining CourtListener request budget."""
    state = QuotaLedger().state()
    table = Table("Window", "Remaining", box=None)
    for window, label in ((60, "per minute"), (3_600, "per hour"), (86_400, "per day")):
        table.add_row(label, str(state.remaining[window]))
    console.print(table)
    if state.exhausted:
        console.print("[red]Daily budget spent. Resume tomorrow.[/red]")
    elif state.wait_seconds > 0:
        console.print(f"[yellow]Next slot in {state.wait_seconds:.0f}s[/yellow]")


@corpus_app.command("search")
def search_cmd(
    query: str = typer.Argument(
        '"commercial general liability" "declarations" "forms and endorsements"',
        help="Full-text query. Quote phrases.",
    ),
    pages: int = typer.Option(1, help="Search result pages to pull (1 request each)."),
) -> None:
    """Search RECAP and rank candidates. Downloads nothing.

    Searches are the cheap end of the budget: one request returns many candidates with the
    metadata needed to rank them. Spend requests here rather than on speculative downloads.
    """
    found: list[Candidate] = []
    with CourtListenerClient() as client:
        for page in range(1, pages + 1):
            found.extend(client.search(query, page=page))

    ranked = rank(found)
    CANDIDATES.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES.write_text(
        json.dumps(
            [{"score": r.score, "label": r.label, **r.candidate.__dict__} for r in ranked],
            indent=2,
        )
    )

    dropped = len(found) - len(ranked)
    # Show the attachment's own label — the parent entry's description is the same string
    # for every attachment in the filing and tells you nothing about which one this is.
    table = Table("Score", "Pages", "Att", "Attachment label", box=None)
    for r in ranked[:25]:
        table.add_row(
            str(r.score),
            str(r.candidate.page_count or "?"),
            str(r.candidate.attachment_number or "-"),
            (r.label or "")[:74],
        )
    console.print(table)
    console.print(
        f"\n{len(found)} results · {dropped} dropped (no stored PDF) · "
        f"{len(ranked)} fetchable → {CANDIDATES}"
    )


@corpus_app.command("fetch")
def fetch_cmd(
    top: int = typer.Option(5, help="How many top-ranked candidates to download."),
    min_score: int = typer.Option(20, help="Skip candidates scoring below this."),
) -> None:
    """Download the top-ranked candidates from the last search. One request each."""
    if not CANDIDATES.exists():
        raise typer.BadParameter("No candidates. Run `pc corpus search` first.")

    rows = [r for r in json.loads(CANDIDATES.read_text()) if r["score"] >= min_score][:top]
    if not rows:
        console.print(f"[yellow]Nothing scored >= {min_score}. Try a different query.[/yellow]")
        raise typer.Exit()

    with CourtListenerClient() as client:
        for row in rows:
            score = row.pop("score")
            row.pop("label", None)  # display-only; not a Candidate field
            candidate = Candidate(**row)
            dest = RAW_DIR / f"cl-{candidate.doc_id}.pdf"
            if dest.exists():
                console.print(f"[dim]have  {dest.name}[/dim]")
                continue
            client.download(candidate, dest)
            console.print(f"[green]saved[/green] {dest.name}  (score {score})")


@corpus_app.command("screen")
def screen_cmd(
    path: Path = typer.Argument(RAW_DIR, help="A PDF, or a directory of them."),
) -> None:
    """Check downloaded PDFs for the markers of a complete policy. Costs no requests."""
    targets = sorted(path.glob("*.pdf")) if path.is_dir() else [path]
    if not targets:
        console.print(f"[yellow]No PDFs under {path}[/yellow]")
        raise typer.Exit()

    table = Table("File", "Pages", "Text", "Dec", "Forms", "LOB", "Form#", "Verdict", box=None)
    for pdf in targets:
        s = screen(pdf)
        table.add_row(
            pdf.name[:26],
            str(s.page_count),
            f"{s.text_pages}pp" if not s.is_scanned else "none",
            "yes" if s.has_dec_page else "-",
            "yes" if s.has_forms_schedule else "-",
            "yes" if s.has_target_lob else "-",
            str(s.form_number_hits),
            s.verdict(),
        )
    console.print(table)
    console.print("\n[dim]Confirm by hand before `pc corpus add` — screening is a filter, "
                  "not a decision.[/dim]")


@corpus_app.command("add")
def add_cmd(
    pdf: Path = typer.Argument(..., help="The PDF to promote into the corpus."),
    source: str = typer.Option(..., help="courtlistener | gov | risk_pool | serff | specimen"),
    url: str = typer.Option(..., help="Public URL a stranger could follow."),
    carrier: str | None = typer.Option(None),
    notes: str | None = typer.Option(None),
) -> None:
    """Register a screened PDF in the corpus ledger and copy it to corpus/base/."""
    s = screen(pdf)
    doc_id = pdf.stem
    ledger = CorpusLedger()
    ledger.add(
        CorpusEntry(
            doc_id=doc_id,
            source=source,
            source_url=url,
            retrieved_at=CorpusLedger.now(),
            page_count=s.page_count,
            has_scanned_pages=s.is_scanned,
            carrier=carrier,
            notes=notes,
        )
    )
    base = Path("corpus/base") / f"{doc_id}.pdf"
    base.parent.mkdir(parents=True, exist_ok=True)
    base.write_bytes(pdf.read_bytes())
    console.print(f"[green]added[/green] {doc_id} → {base}")


@corpus_app.command("status")
def status_cmd() -> None:
    """Coverage against the spec §3.2 corpus targets."""
    c = CorpusLedger().coverage()
    table = Table("Target", "Have", "Need", box=None)
    table.add_row("base documents", str(c["documents"]), "15-20")
    table.add_row("distinct carriers", str(c["carriers"]), "3-5")
    table.add_row("with scanned pages", str(c["scanned"]), ">=2")
    console.print(table)


if __name__ == "__main__":
    app()
