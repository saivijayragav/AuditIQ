"""AuditIQ Core command-line interface."""
from __future__ import annotations

import typer

from . import __version__
from .core import load_default_taxonomy
from .ingest.erp import ADAPTERS, ingest_tb
from .store import init_db, session_scope
from .store.models import Engagement, FsLine, NoteItem, TbLine

app = typer.Typer(help="AuditIQ Core — ingestion, reconciliation and review.", no_args_is_help=True)
taxonomy_app = typer.Typer(help="Inspect the Schedule III FSLI taxonomy.", no_args_is_help=True)
store_app = typer.Typer(help="Manage the AuditIQ database.", no_args_is_help=True)
ingest_app = typer.Typer(help="Ingest source data (trial balances, statements).", no_args_is_help=True)
app.add_typer(taxonomy_app, name="taxonomy")
app.add_typer(store_app, name="store")
app.add_typer(ingest_app, name="ingest")

# Accept short codes as well as the full statement names used in the schema.
_STATEMENT_ALIASES = {
    "bs": "balance sheet",
    "pl": "statement of profit and loss",
    "p&l": "statement of profit and loss",
    "pnl": "statement of profit and loss",
    "pll": "statement of profit and loss",
    "cf": "cash flow",
    "equity": "equity",
    "notes": "notes",
}


def _match_statement(value: str, query: str) -> bool:
    target = _STATEMENT_ALIASES.get(query.strip().lower(), query.strip().lower())
    return target in value.strip().lower()


@app.command()
def version() -> None:
    """Print the AuditIQ Core version."""
    typer.echo(f"auditiq {__version__}")


@taxonomy_app.command("show")
def taxonomy_show(
    statement: str = typer.Option(
        None, "--statement", "-s", help="Filter by statement: BS, P&L, CF, Equity, Notes."
    ),
    search: str = typer.Option(None, "--search", help="Substring match on FSLI name."),
) -> None:
    """List FSLI line items from the committed taxonomy."""
    tax = load_default_taxonomy()
    items = list(tax)
    if statement:
        items = [i for i in items if _match_statement(i.statement, statement)]
    if search:
        needle = search.lower()
        items = [i for i in items if needle in i.name.lower()]

    label = f" in {statement}" if statement else ""
    typer.echo(f"{len(items)} FSLIs{label}")
    for item in items:
        typer.echo(
            f"  {item.code:<10} {item.statement:<10} {item.category:<14} "
            f"{item.name} ({item.normal_balance})"
        )


@store_app.command("init")
def store_init() -> None:
    """Create the database and all tables (idempotent)."""
    engine = init_db()
    typer.echo(f"Initialised database: {engine.url}")


@store_app.command("status")
def store_status() -> None:
    """Show row counts for the main tables."""
    init_db()
    with session_scope() as session:
        counts = {
            "engagements": session.query(Engagement).count(),
            "tb_lines": session.query(TbLine).count(),
            "fs_lines": session.query(FsLine).count(),
            "note_items": session.query(NoteItem).count(),
        }
    for name, count in counts.items():
        typer.echo(f"  {name:<14} {count}")


@ingest_app.command("tb")
def ingest_tb_command(
    path: str = typer.Argument(..., help="Path to the trial-balance export (.xlsx or .csv)."),
    client: str = typer.Option(..., "--client", "-c", help="Client code, e.g. T00."),
    period: str = typer.Option(..., "--period", "-p", help="Financial year, e.g. FY25-26."),
    basis: str = typer.Option("Standalone", "--basis", help="Standalone or Consolidated."),
    source: str = typer.Option(
        None,
        "--source",
        "-s",
        help=f"ERP layout (default: auto-detect). One of: {', '.join(sorted(ADAPTERS))}.",
    ),
    name: str = typer.Option("", "--name", "-n", help="Client name (optional)."),
    unit: str = typer.Option(
        "absolute", "--unit", help="Reporting unit of the amounts: absolute, lakhs, crores, millions."
    ),
) -> None:
    """Ingest an ERP trial-balance export into the store."""
    try:
        result = ingest_tb(
            path,
            client_code=client,
            period=period,
            basis=basis,
            source=source,
            client_name=name,
            unit=unit,
        )
    except (FileNotFoundError, ValueError) as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"source        {result.source}")
    typer.echo(f"engagement    #{result.engagement_id}  {result.client_code} {result.period} ({result.basis})")
    typer.echo(f"document      #{result.document_id}")
    typer.echo(f"lines         {result.lines} (duplicates skipped: {result.duplicates_skipped})")
    typer.echo(f"total debit   {result.total_debit:,.2f}")
    typer.echo(f"total credit  {result.total_credit:,.2f}")
    if result.balanced:
        typer.secho(f"balanced      yes (diff {result.balance_difference:,.2f})", fg=typer.colors.GREEN)
    else:
        typer.secho(
            f"balanced      NO (diff {result.balance_difference:,.2f})",
            fg=typer.colors.YELLOW,
        )


if __name__ == "__main__":
    app()
