"""AuditIQ Core command-line interface."""
from __future__ import annotations

import typer

from . import __version__
from .core import load_default_taxonomy
from .ingest.erp import ADAPTERS, ingest_tb
from .ingest.prepare import (
    default_encoder_kind,
    load_labelled_csv,
    map_engagement,
    save_thresholds,
    tune_thresholds,
)
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


def _resolve_engagement_id(engagement, client, period, basis) -> int:
    if engagement is not None:
        return engagement
    if not (client and period):
        typer.secho(
            "error: provide --engagement, or both --client and --period",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    with session_scope() as session:
        row = session.query(Engagement).filter_by(
            client_code=client, period=period, basis=basis
        ).one_or_none()
        if row is None:
            typer.secho(
                f"error: no engagement for {client} {period} ({basis})",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        return row.id


@app.command("map")
def map_command(
    engagement: int = typer.Option(None, "--engagement", "-e", help="Engagement id."),
    client: str = typer.Option(None, "--client", "-c", help="Client code (with --period)."),
    period: str = typer.Option(None, "--period", "-p", help="Financial year (with --client)."),
    basis: str = typer.Option("Standalone", "--basis", help="Standalone or Consolidated."),
    encoder: str = typer.Option(
        None, "--encoder", help="tfidf | sbert | none (default: auto-detect)."
    ),
    use_llm: bool = typer.Option(
        False, "--llm", help="Enable the constrained LLM layer (off by default)."
    ),
    llm_cache: str = typer.Option("llm_cache.json", "--llm-cache", help="LLM response cache path."),
) -> None:
    """Map an engagement's trial-balance lines to Schedule III FSLIs."""
    engagement_id = _resolve_engagement_id(engagement, client, period, basis)
    try:
        summary = map_engagement(
            engagement_id,
            client=client,
            encoder_kind=encoder,
            use_llm=use_llm,
            llm_cache=llm_cache,
        )
    except (RuntimeError, ValueError) as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"engagement    #{summary.engagement_id}")
    typer.echo(f"encoder       {summary.encoder}{'' if summary.tuned else '  (untuned defaults)'}")
    typer.echo(f"lines         {summary.lines}")
    typer.echo(f"resolved      {summary.resolved} ({summary.resolution_rate:.1%})")
    typer.echo(f"review        {summary.review}")
    for layer, count in sorted(summary.by_layer.items()):
        typer.echo(f"  by {layer:<6} {count}")
    if use_llm:
        typer.echo(f"llm calls     {summary.llm_calls}")


@app.command("tune")
def tune_command(
    gold: str = typer.Argument(..., help="Labelled CSV with raw_name, group, gold columns."),
    client: str = typer.Option(None, "--client", "-c", help="Save as thresholds/<client>.json."),
    encoder: str = typer.Option(None, "--encoder", help="tfidf | sbert (default: auto-detect)."),
    out: str = typer.Option(None, "--out", help="Explicit thresholds output path."),
    split: str = typer.Option(
        "dev", "--split", help="Keep rows with this split value (blank = all rows)."
    ),
    dict_mode: str = typer.Option("full", "--dict-mode", help="full | heldout."),
    k: int = typer.Option(5, "--k", help="Shortlist size."),
    use_llm: bool = typer.Option(False, "--llm", help="Tune the LLM gate too (needs an API key)."),
) -> None:
    """Tune cascade thresholds on a labelled dev set and save them."""
    import json

    dev = load_labelled_csv(gold, split=split or None)
    if not dev:
        typer.secho("error: no labelled heads loaded", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    llm = None
    if use_llm:
        from .ingest.prepare import LLM

        llm = LLM(cache_path="llm_cache.json")

    kind = encoder or default_encoder_kind()
    if kind == "none":
        typer.secho("warning: no encoder available; tuning the embedding gate is skipped", fg=typer.colors.YELLOW)

    thresholds, report = tune_thresholds(
        dev, encoder_kind=kind, llm=llm, k=k, dict_mode=dict_mode
    )
    if llm is not None:
        llm.flush()

    path = save_thresholds(thresholds, client=client, path=out)
    typer.echo(f"tuned {len(dev)} heads ({kind}, dict_mode={dict_mode})")
    typer.echo(f"  tau_e={thresholds.tau_e}  delta={thresholds.delta}  tau_l={thresholds.tau_l}  k={thresholds.k}")
    typer.echo(f"saved {path}")
    typer.echo(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    app()
