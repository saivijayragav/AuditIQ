"""AuditIQ Core command-line interface."""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .analytics import (
    RATIO_DEFINITIONS,
    AnalyticalReport,
    run_analytics,
)
from .gl import run_jet_file
from .gst import MatchStatus, run_gst_recon_files
from .gst.generator import generate_gst_dataset
from .gst.ingest import auto_load_books_file, auto_load_portal_file
from .core import load_default_taxonomy
from .ingest.erp import ADAPTERS, ingest_tb
from .ingest.fs import (
    fs_coverage,
    ingest_fs,
    list_unmapped_fs,
    reset_fs_line,
    resolve_fs_line,
)
from .ingest.prepare import (
    default_encoder_kind,
    list_pending,
    load_labelled_csv,
    map_engagement,
    reset_mapping,
    resolve_mapping,
    save_thresholds,
    tune_thresholds,
)
from .reconciliation import (
    MaterialityError,
    explain_unit,
    latest_run,
    run_recon,
    set_materiality,
    suggest_for_engagement,
)
from .store import SchemaDriftError, init_db, reset_db, session_scope
from .store.models import Engagement, FsLine, NoteItem, ReconLine, ReconRun, TbLine
from .store.queries import dispose_exception, list_exceptions

app = typer.Typer(help="AuditIQ Core — ingestion, reconciliation and review.", no_args_is_help=True)
taxonomy_app = typer.Typer(help="Inspect the Schedule III FSLI taxonomy.", no_args_is_help=True)
store_app = typer.Typer(help="Manage the AuditIQ database.", no_args_is_help=True)
ingest_app = typer.Typer(help="Ingest source data (trial balances, statements).", no_args_is_help=True)
fs_app = typer.Typer(help="Financial-statement ingestion and coverage.", no_args_is_help=True)
recon_app = typer.Typer(help="Reconcile the books with the draft financial statements.", no_args_is_help=True)
materiality_app = typer.Typer(help="Set and suggest engagement materiality.", no_args_is_help=True)
review_app = typer.Typer(help="Resolve pending FSLI mappings (the review queue).", no_args_is_help=True)
fsreview_app = typer.Typer(help="Resolve unmapped financial-statement labels.", no_args_is_help=True)
exceptions_app = typer.Typer(help="Inspect and disposition audit exceptions.", no_args_is_help=True)
api_app = typer.Typer(help="Inspect the HTTP API contract (OpenAPI).", no_args_is_help=True)
analytics_app = typer.Typer(help="SA 520 analytical procedures and Schedule III ratio analysis.", no_args_is_help=True)
jet_app = typer.Typer(help="SA 240 / ISA 240 Journal Entry Testing (fraud risk detection).", no_args_is_help=True)
gst_app = typer.Typer(help="GST Returns & ITC Reconciliation (GSTR-2B vs Books, GSTR-1).", no_args_is_help=True)

app.add_typer(taxonomy_app, name="taxonomy")
app.add_typer(store_app, name="store")
app.add_typer(ingest_app, name="ingest")
app.add_typer(fs_app, name="fs")
app.add_typer(recon_app, name="recon")
app.add_typer(materiality_app, name="materiality")
app.add_typer(review_app, name="review")
app.add_typer(fsreview_app, name="fs-review")
app.add_typer(exceptions_app, name="exceptions")
app.add_typer(api_app, name="api")
app.add_typer(analytics_app, name="analytics")
app.add_typer(jet_app, name="jet")
app.add_typer(gst_app, name="gst")

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
    try:
        engine = init_db()
    except SchemaDriftError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Initialised database: {engine.url}")


@store_app.command("reset")
def store_reset(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Delete the local database and rebuild an empty schema.

    Removes every engagement, document and result. Uploaded source files in
    ``data/uploads`` are left in place. Use this after a schema change: the
    models gained columns, and ``store init`` cannot add them to an old file.
    """
    if not yes:
        typer.confirm(
            "This deletes the local AuditIQ database. Continue?", abort=True
        )
    try:
        engine = reset_db()
    except (SchemaDriftError, RuntimeError) as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Reset database: {engine.url}")


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
            "recon_runs": session.query(ReconRun).count(),
            "recon_lines": session.query(ReconLine).count(),
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


@ingest_app.command("fs")
def ingest_fs_command(
    path: str = typer.Argument(..., help="Path to the draft financial statements (PDF)."),
    client: str = typer.Option(..., "--client", "-c", help="Client code, e.g. T00."),
    period: str = typer.Option(..., "--period", "-p", help="Financial year, e.g. FY25-26."),
    basis: str = typer.Option("Standalone", "--basis", help="Standalone or Consolidated."),
    kind: str = typer.Option(
        None, "--kind", "-k", help="Reader kind (default: auto-detect from the file suffix)."
    ),
    name: str = typer.Option("", "--name", "-n", help="Client name (optional)."),
    unit: str = typer.Option(
        None, "--unit", help="Override the reporting unit: absolute, lakhs, crores, millions."
    ),
    encoder: str = typer.Option(
        None, "--encoder", help="tfidf | sbert | none (default: auto-detect)."
    ),
    use_llm: bool = typer.Option(
        False, "--llm", help="Enable the constrained LLM layer (off by default)."
    ),
    llm_cache: str = typer.Option("llm_cache.json", "--llm-cache", help="LLM response cache path."),
) -> None:
    """Ingest a draft financial statement (reconciliation Side B)."""
    try:
        result = ingest_fs(
            path,
            client_code=client,
            period=period,
            basis=basis,
            kind=kind,
            client_name=name,
            unit=unit,
            encoder_kind=encoder,
            use_llm=use_llm,
            llm_cache=llm_cache,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"reader        {result.reader}")
    typer.echo(f"company       {result.company or '(not detected)'}")
    typer.echo(
        f"engagement    #{result.engagement_id}  {client} {result.period} ({result.basis})"
    )
    typer.echo(
        f"period        {result.period} (prior {result.prior_period or 'n/a'})  unit {result.unit}"
    )
    typer.echo(f"document      #{result.document_id}  pages {result.pages}  tables {result.tables}")
    typer.echo(f"rows          {result.rows}  lines {result.lines}")
    typer.echo(
        f"mapped        {result.mapped}/{result.lines} "
        f"({result.mapped / result.lines:.1%})" if result.lines else "mapped        0"
    )
    typer.echo(f"subtotals     {result.subtotals} (excluded from tie-out)")
    for statement, count in sorted(result.by_statement.items()):
        typer.echo(f"  {statement:<10} {count}")
    typer.echo(f"encoder       {result.encoder}{'' if result.tuned else '  (untuned defaults)'}")
    for layer, count in sorted(result.by_layer.items()):
        typer.echo(f"  by {layer:<6} {count}")
    for issue in result.issues:
        colour = {
            "error": typer.colors.RED,
            "warning": typer.colors.YELLOW,
        }.get(issue.severity, typer.colors.CYAN)
        typer.secho(f"  {issue.severity:<7} {issue.code}: {issue.message}", fg=colour)


@fs_app.command("coverage")
def fs_coverage_command(
    path: str = typer.Argument(..., help="Path to the financial statement (PDF)."),
    kind: str = typer.Option(None, "--kind", "-k", help="Reader kind (default: auto-detect)."),
    client: str = typer.Option(None, "--client", "-c", help="Client code (for tuned thresholds)."),
    encoder: str = typer.Option(
        None, "--encoder", help="tfidf | sbert | none (default: auto-detect)."
    ),
    use_llm: bool = typer.Option(
        False, "--llm", help="Enable the constrained LLM layer (off by default)."
    ),
    llm_cache: str = typer.Option("llm_cache.json", "--llm-cache", help="LLM response cache path."),
) -> None:
    """Report FS-label -> FSLI coverage for a document (no persistence)."""
    try:
        report = fs_coverage(
            path,
            kind=kind,
            client=client,
            encoder_kind=encoder,
            use_llm=use_llm,
            llm_cache=llm_cache,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"document      {report.path}")
    typer.echo(f"encoder       {report.encoder}{'' if report.tuned else '  (untuned defaults)'}")
    typer.echo(f"rows          {report.rows}")
    typer.echo(f"coverage      {report.mapped}/{report.rows} ({report.coverage:.1%})")
    for layer, count in sorted(report.by_layer.items()):
        typer.echo(f"  by {layer:<6} {count}")

    if report.unmapped:
        typer.echo("unmapped:")
        for statement, label in report.unmapped:
            typer.echo(f"  [{statement}] {label}")


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


def _review_target(
    engagement: int | None,
    client: str | None,
    period: str | None,
    basis: str,
) -> int:
    return _resolve_engagement_id(engagement, client, period, basis)


@review_app.command("list")
def review_list_command(
    engagement: int = typer.Option(None, "--engagement", "-e", help="Engagement id."),
    client: str = typer.Option(None, "--client", "-c", help="Client code (with --period)."),
    period: str = typer.Option(None, "--period", "-p", help="Financial year (with --client)."),
    basis: str = typer.Option("Standalone", "--basis", help="Standalone or Consolidated."),
) -> None:
    """List ledger heads awaiting review (largest exposure first)."""
    engagement_id = _review_target(engagement, client, period, basis)
    heads = list_pending(engagement_id)
    if not heads:
        typer.secho("review queue empty — every head is accepted", fg=typer.colors.GREEN)
        return
    typer.echo(f"{len(heads)} pending head(s) for engagement #{engagement_id}")
    for head in heads:
        candidates = ",".join(head.candidates) or "-"
        typer.echo(
            f"  #{head.line_id:>6}  {_money(head.amount):>16}  x{head.lines:<2} "
            f"{head.raw_name[:36]:<36} [{head.method}] cand: {candidates}"
        )
    typer.echo("\nresolve with: auditiq review resolve <line-id> --fsli <CODE>")


@review_app.command("resolve")
def review_resolve_command(
    line: int = typer.Argument(..., help="Line id shown by `review list` (any line of the head)."),
    fsli: str = typer.Option(..., "--fsli", "-f", help="FSLI code the reviewer chooses."),
    reviewer: str = typer.Option("", "--reviewer", "-r", help="Reviewer name (optional)."),
) -> None:
    """Approve a head: record the reviewer's FSLI choice."""
    try:
        result = resolve_mapping(line, fsli, reviewer=reviewer)
    except ValueError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(
        f"resolved  {result.head} -> {result.fsli_code}  ({result.resolved_lines} line(s))",
        fg=typer.colors.GREEN,
    )


@review_app.command("reset")
def review_reset_command(
    line: int = typer.Argument(..., help="Line id shown by `review list` (any line of the head)."),
) -> None:
    """Undo a reviewer resolution; the head returns to the queue."""
    try:
        result = reset_mapping(line)
    except ValueError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"reset     {result.head}  (back to pending review)")


@fsreview_app.command("list")
def fs_review_list_command(
    engagement: int = typer.Option(None, "--engagement", "-e", help="Engagement id."),
    client: str = typer.Option(None, "--client", "-c", help="Client code (with --period)."),
    period: str = typer.Option(None, "--period", "-p", help="Financial year (with --client)."),
    basis: str = typer.Option("Standalone", "--basis", help="Standalone or Consolidated."),
) -> None:
    """List financial-statement labels that resolved to neither an FSLI nor a group."""
    engagement_id = _review_target(engagement, client, period, basis)
    labels = list_unmapped_fs(engagement_id)
    if not labels:
        typer.secho("no unmapped financial-statement labels", fg=typer.colors.GREEN)
        return
    typer.echo(f"{len(labels)} unmapped label(s) for engagement #{engagement_id}")
    for entry in labels:
        typer.echo(
            f"  #{entry.line_id:>6}  {_money(entry.total):>16}  x{entry.rows:<2} "
            f"[{entry.statement:<3}] {entry.label[:40]}"
        )
    typer.echo(
        "\nresolve with: auditiq fs-review resolve <line-id> --fsli <CODE> (or --group <CODE>)"
    )


@fsreview_app.command("resolve")
def fs_review_resolve_command(
    line: int = typer.Argument(..., help="FS line id shown by `fs-review list`."),
    fsli: str = typer.Option(None, "--fsli", "-f", help="FSLI code the reviewer chooses."),
    group: str = typer.Option(None, "--group", "-g", help="Presentation group code (e.g. REV_OPERATIONS)."),
) -> None:
    """Resolve an unmapped financial-statement label (applies to all its period rows)."""
    try:
        result = resolve_fs_line(line, fsli_code=fsli, group_code=group)
    except ValueError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    target = result.fsli_code or result.group_code
    typer.secho(
        f"resolved  {result.label} -> {target}  ({result.resolved_rows} row(s))",
        fg=typer.colors.GREEN,
    )


@fsreview_app.command("reset")
def fs_review_reset_command(
    line: int = typer.Argument(..., help="FS line id shown by `fs-review list`."),
) -> None:
    """Undo a manual FS resolution; the label returns to the unmapped queue."""
    try:
        result = reset_fs_line(line)
    except ValueError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"reset     {result.label}  (back to unmapped)")


@exceptions_app.command("list")
def exceptions_list_command(
    engagement: int = typer.Option(None, "--engagement", "-e", help="Engagement id."),
    client: str = typer.Option(None, "--client", "-c", help="Client code (with --period)."),
    period: str = typer.Option(None, "--period", "-p", help="Financial year (with --client)."),
    basis: str = typer.Option("Standalone", "--basis", help="Standalone or Consolidated."),
    status: str = typer.Option(None, "--status", help="Filter: open | explained | accepted."),
) -> None:
    """List exception records awaiting disposition."""
    if engagement is None and not (client and period):
        raise typer.BadParameter("provide --engagement, or both --client and --period")
    engagement_id = _review_target(engagement, client, period, basis)
    rows = list_exceptions(engagement_id, status=status)
    if not rows:
        typer.echo("no exceptions")
        return
    typer.echo(f"{len(rows)} exception(s) for engagement #{engagement_id}")
    for item in rows:
        typer.echo(
            f"  #{item.exception_id:>5}  {item.kind:<7} {item.severity:<8} "
            f"{item.status:<9} {_money(item.amount):>14}  "
            f"{item.fsli or '-':<14} {item.note or ''}"
        )
    typer.echo("\ndispose with: auditiq exceptions dispose <id> --status explained|accepted")


@exceptions_app.command("dispose")
def exceptions_dispose_command(
    exception_id: int = typer.Argument(..., help="Exception id (see `exceptions list`)."),
    status: str = typer.Option(..., "--status", "-s", help="explained or accepted."),
    note: str = typer.Option("", "--note", "-n", help="Reviewer note."),
) -> None:
    """Record an exception's disposition."""
    try:
        item = dispose_exception(exception_id, status, note=note)
    except ValueError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"exception #{item.exception_id}  status -> {item.status}")
    if item.note:
        typer.echo(f"  note: {item.note}")


def _money(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}"


def _parse_scope(statement: str | None):
    if not statement or statement.strip().lower() == "all":
        return None
    parts = [p.strip().upper() for p in statement.split(",") if p.strip()]
    normalised = []
    for part in parts:
        if part in ("PL", "P&L", "PNL", "PLL"):
            normalised.append("P&L")
        elif part == "BS":
            normalised.append("BS")
        else:
            normalised.append(part)
    return tuple(dict.fromkeys(normalised))


def _print_summary(summary) -> None:
    typer.echo(
        f"engagement    #{summary.engagement_id}  {summary.period} ({summary.basis})"
    )
    if summary.run_id is not None:
        typer.echo(f"run           #{summary.run_id}")
    typer.echo(
        f"unit          {summary.unit}  rounding tolerance {_money(summary.tolerance)} "
        f"({summary.rounding_decimals} decimals)"
    )
    typer.echo(
        f"materiality   {_money(summary.materiality)} "
        f"(PM {_money(summary.performance_materiality)})"
    )
    if summary.materiality_basis:
        typer.echo(f"              basis: {summary.materiality_basis}")
    typer.echo(f"scope         {', '.join(summary.statements) or 'all'}")
    typer.echo(
        f"units         {summary.units}  tied {summary.tied}  rounding {summary.rounding}  "
        f"minor {summary.minor}  watch {summary.watch}  material {summary.material}"
    )
    typer.echo(
        f"exposure      Side A {summary.exposure_a_lines} heads {_money(summary.exposure_a)}   "
        f"Side B {summary.exposure_b_rows} rows {_money(summary.exposure_b)}"
    )
    colour = {
        "clean": typer.colors.GREEN,
        "minor residual": typer.colors.CYAN,
        "watch items": typer.colors.YELLOW,
        "material differences": typer.colors.RED,
    }.get(summary.status, None)
    typer.secho(f"status        {summary.status}", fg=colour)

    if summary.worst:
        typer.echo("")
        typer.echo("differences:")
        for line in summary.worst:
            pct = f"{line.variance_pct:,.1f}%" if line.variance_pct is not None else "-"
            typer.echo(
                f"  {line.code:<16} {line.unit.name[:34]:<34} "
                f"a {_money(line.side_a):>16}  b {_money(line.side_b):>16}  "
                f"var {_money(line.variance):>16}  {pct:>8}  {line.severity}"
            )

    notable = [
        f for f in summary.findings if f.severity in ("material", "watch", "minor")
    ]
    if notable:
        typer.echo("")
        typer.echo("articulation:")
        for finding in notable:
            typer.echo(f"  {finding.severity:<8} {finding.code}: {finding.message}")


@materiality_app.command("set")
def materiality_set_command(
    engagement: int = typer.Option(None, "--engagement", "-e", help="Engagement id."),
    client: str = typer.Option(None, "--client", "-c", help="Client code (with --period)."),
    period: str = typer.Option(None, "--period", "-p", help="Financial year (with --client)."),
    basis: str = typer.Option("Standalone", "--basis", help="Standalone or Consolidated."),
    value: float = typer.Option(..., "--value", "-v", help="Materiality in absolute rupees."),
    basis_name: str = typer.Option("", "--basis-name", help="Basis, e.g. 0.5% of revenue."),
) -> None:
    """Store the engagement materiality used to grade reconciliation differences."""
    engagement_id = _resolve_engagement_id(engagement, client, period, basis)
    try:
        row = set_materiality(engagement_id, value, basis_name)
    except ValueError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"engagement    #{engagement_id}  {row.client_code} {row.period}")
    typer.echo(f"materiality   {_money(row.materiality_value)}")
    if row.materiality_basis:
        typer.echo(f"basis         {row.materiality_basis}")


@materiality_app.command("suggest")
def materiality_suggest_command(
    engagement: int = typer.Option(None, "--engagement", "-e", help="Engagement id."),
    client: str = typer.Option(None, "--client", "-c", help="Client code (with --period)."),
    period: str = typer.Option(None, "--period", "-p", help="Financial year (with --client)."),
    basis: str = typer.Option("Standalone", "--basis", help="Standalone or Consolidated."),
) -> None:
    """Suggest a materiality from the draft financial statements (for review)."""
    engagement_id = _resolve_engagement_id(engagement, client, period, basis)
    try:
        suggestion = suggest_for_engagement(engagement_id)
    except ValueError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"engagement    #{engagement_id}")
    typer.echo(f"revenue       {_money(suggestion['revenue'])}")
    typer.echo(f"total assets  {_money(suggestion['total_assets'])}")
    typer.echo(
        f"suggested     {_money(suggestion['suggested'])} "
        f"({suggestion['ratio']:.2%} of {suggestion['basis']})"
    )
    typer.secho(
        "review and confirm with `auditiq materiality set`", fg=typer.colors.CYAN
    )


@recon_app.command("run")
def recon_run_command(
    engagement: int = typer.Option(None, "--engagement", "-e", help="Engagement id."),
    client: str = typer.Option(None, "--client", "-c", help="Client code (with --period)."),
    period: str = typer.Option(None, "--period", "-p", help="Financial year (with --client)."),
    basis: str = typer.Option("Standalone", "--basis", help="Standalone or Consolidated."),
    materiality: float = typer.Option(None, "--materiality", "-m", help="Override materiality (rupees)."),
    pm: float = typer.Option(0.75, "--pm", help="Performance materiality as a ratio of materiality."),
    rounding_decimals: int = typer.Option(
        2, "--rounding-decimals", help="Decimals the statements are presented to."
    ),
    statement: str = typer.Option("all", "--statement", "-s", help="BS, P&L, or all."),
    side_b_period: str = typer.Option(
        None, "--side-b-period", help="Restrict Side B to one financial year."
    ),
    no_persist: bool = typer.Option(False, "--no-persist", help="Compute without writing a run."),
) -> None:
    """Reconcile the mapped trial balance against the client's draft statements."""
    engagement_id = _resolve_engagement_id(engagement, client, period, basis)
    try:
        summary = run_recon(
            engagement_id,
            materiality=materiality,
            pm_ratio=pm,
            rounding_decimals=rounding_decimals,
            statements=_parse_scope(statement),
            persist=not no_persist,
            side_b_period=side_b_period,
        )
    except MaterialityError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    _print_summary(summary)


@recon_app.command("show")
def recon_show_command(
    engagement: int = typer.Option(None, "--engagement", "-e", help="Engagement id."),
    client: str = typer.Option(None, "--client", "-c", help="Client code (with --period)."),
    period: str = typer.Option(None, "--period", "-p", help="Financial year (with --client)."),
    basis: str = typer.Option("Standalone", "--basis", help="Standalone or Consolidated."),
    severity: str = typer.Option(None, "--severity", help="Only material | watch | minor."),
    statement: str = typer.Option(None, "--statement", "-s", help="BS or P&L."),
) -> None:
    """Show the persisted reconciliation grid for an engagement."""
    engagement_id = _resolve_engagement_id(engagement, client, period, basis)
    run, lines = latest_run(engagement_id)
    if run is None:
        typer.secho(
            f"error: no reconciliation run for engagement #{engagement_id}; run `auditiq recon run`",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    scope = _parse_scope(statement)
    selected = [
        line
        for line in lines
        if (severity is None or line.severity == severity)
        and (scope is None or line.statement in scope)
    ]
    typer.echo(
        f"run #{run.run_id}  {run.period} ({run.basis})  unit {run.unit}  "
        f"materiality {_money(run.materiality)} (PM {_money(run.performance_materiality)})"
    )
    typer.echo(
        f"units {run.units_total}  tied {run.tied}  rounding {run.rounding}  "
        f"minor {run.minor}  watch {run.watch}  material {run.material}   "
        f"exposure A {_money(run.exposure_a)}  B {_money(run.exposure_b)}"
    )
    if not selected:
        typer.echo("no lines match the filter")
        return
    typer.echo("")
    for line in selected:
        pct = f"{line.variance_pct:,.1f}%" if line.variance_pct is not None else "-"
        tag = "G" if line.is_group else " "
        typer.echo(
            f"  {tag} {line.unit_code:<16} {line.name[:32]:<32} "
            f"a {_money(line.side_a):>16}  b {_money(line.side_b):>16}  "
            f"var {_money(line.variance):>16}  {pct:>8}  {line.classification:<9} {line.severity}"
        )


@recon_app.command("explain")
def recon_explain_command(
    fsli: str = typer.Argument(..., help="Unit code: an FSLI or a group code."),
    engagement: int = typer.Option(None, "--engagement", "-e", help="Engagement id."),
    client: str = typer.Option(None, "--client", "-c", help="Client code (with --period)."),
    period: str = typer.Option(None, "--period", "-p", help="Financial year (with --client)."),
    basis: str = typer.Option("Standalone", "--basis", help="Standalone or Consolidated."),
) -> None:
    """Explain one reconciliation unit: its components and attributed causes."""
    engagement_id = _resolve_engagement_id(engagement, client, period, basis)
    run, line = explain_unit(engagement_id, fsli)
    if run is None:
        typer.secho(
            f"error: no reconciliation run for engagement #{engagement_id}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if line is None:
        typer.secho(
            f"error: unit '{fsli}' is not in run #{run.run_id}", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)

    typer.echo(f"unit          {line.unit_code}  {line.name}" + ("  [group]" if line.is_group else ""))
    typer.echo(f"statement     {line.statement or '-'}")
    typer.echo(f"side A        {_money(line.side_a)}  ({line.a_lines} lines)")
    typer.echo(f"side B        {_money(line.side_b)}  ({line.b_rows} rows)")
    pct = f"{line.variance_pct:,.1f}%" if line.variance_pct is not None else "-"
    typer.echo(f"variance      {_money(line.variance)}  {pct}  {line.classification} / {line.severity}")

    attribution = line.attribution or {}
    candidates = attribution.get("candidates") or []
    typer.echo(
        f"explained     {_money(attribution.get('explained'))}  "
        f"residual {_money(attribution.get('residual'))}"
    )
    if candidates:
        typer.echo("causes:")
        for candidate in candidates:
            typer.echo(
                f"  {candidate.get('kind', '?'):<18} {_money(candidate.get('amount')):>16}  "
                f"{candidate.get('detail', '')}"
            )

    members = (line.refs or {}).get("members") or []
    if members:
        typer.echo(f"members       {', '.join(members)}")

    a_ids = (line.refs or {}).get("a_line_ids") or []
    if a_ids:
        with session_scope() as session:
            rows = session.query(TbLine).filter(TbLine.id.in_(a_ids)).all()
            books = [(row.raw_name, row.normalized_amount) for row in rows]
        if books:
            typer.echo("books:")
            for name, amount in books:
                typer.echo(f"  {name[:44]:<44} {_money(amount):>18}")


# ── Analytics commands ───────────────────────────────────────────────────────


def _fmt_ratio_val(val: float | None, unit: str) -> str:
    if val is None:
        return "-"
    if unit == "%":
        return f"{val:,.2f}%"
    if unit == "x":
        return f"{val:,.2f}x"
    if unit == "days":
        return f"{val:,.0f}d"
    return f"{val:,.2f}"


def _print_analytics_report(
    report: AnalyticalReport,
    family_filter: Optional[str] = None,
    statutory_only: bool = False,
    flagged_only: bool = False,
) -> None:
    status_color = typer.colors.GREEN
    if report.status == "material findings":
        status_color = typer.colors.RED
    elif report.status == "watch items":
        status_color = typer.colors.YELLOW
    elif report.status == "minor observations":
        status_color = typer.colors.CYAN

    client_info = (
        f" ({report.client_code} {report.period} {report.basis})"
        if report.client_code
        else f" ({report.period})"
    )
    typer.echo(f"\nSA 520 Analytical Procedures — Engagement #{report.engagement_id}{client_info}")
    typer.secho(f"Status: {report.status.upper()}", fg=status_color, bold=True)
    typer.echo(
        f"Summary: {report.computed_count}/{len(report.ratios)} ratios computed  |  "
        f"{report.statutory_count} Schedule III statutory  |  "
        f"{report.flagged_count} findings ({len(report.material_findings)} material, {len(report.watch_findings)} watch)"
    )

    if report.findings:
        typer.echo("\n" + "=" * 105)
        typer.secho("AUDIT FINDINGS & ANOMALIES (SA 520 / Going Concern SA 570):", bold=True)
        typer.echo("=" * 105)
        for f in report.findings:
            if f.severity == "material":
                sev_tag = typer.style("[MATERIAL]", fg=typer.colors.RED, bold=True)
            elif f.severity == "watch":
                sev_tag = typer.style("[ WATCH  ]", fg=typer.colors.YELLOW, bold=True)
            else:
                sev_tag = typer.style("[  INFO  ]", fg=typer.colors.BLUE)
            typer.echo(f"  {sev_tag} ({f.flag_type.upper()}) {f.ratio_name}: {f.message}")

    flagged_codes = {f.ratio_code for f in report.findings}
    filtered_ratios = [
        r
        for r in report.ratios
        if (family_filter is None or r.family == family_filter.lower())
        and (not statutory_only or r.statutory)
        and (not flagged_only or r.code in flagged_codes)
    ]

    typer.echo("\n" + "-" * 105)
    typer.echo(
        f"  {'Family':<14} {'Ratio Name':<32} {'Stat':<6} {'Current':>12} {'Prior':>12} {'YoY Change':>12}  Status"
    )
    typer.echo("-" * 105)
    for r in filtered_ratios:
        stat_mark = "Y" if r.statutory else "-"
        cur_str = _fmt_ratio_val(r.current, r.unit)
        pri_str = _fmt_ratio_val(r.prior, r.unit)
        chg_str = f"{r.change_pct:+,.1f}%" if r.change_pct is not None else "-"

        if r.code in flagged_codes:
            mat = any(
                f.ratio_code == r.code and f.severity == "material"
                for f in report.findings
            )
            if mat:
                status_text = typer.style("FLAGGED (M)", fg=typer.colors.RED, bold=True)
            else:
                status_text = typer.style("FLAGGED (W)", fg=typer.colors.YELLOW)
        elif r.current is not None:
            status_text = typer.style("OK", fg=typer.colors.GREEN)
        else:
            status_text = typer.style("NO DATA", fg=typer.colors.WHITE)

        typer.echo(
            f"  {r.family:<14} {r.name[:30]:<32} {stat_mark:<6} {cur_str:>12} {pri_str:>12} {chg_str:>12}  {status_text}"
        )
    typer.echo("-" * 105 + "\n")


@analytics_app.command("run")
def analytics_run_command(
    engagement: int = typer.Option(None, "--engagement", "-e", help="Engagement id."),
    client: str = typer.Option(None, "--client", "-c", help="Client code (with --period)."),
    period: str = typer.Option(None, "--period", "-p", help="Financial year (with --client)."),
    basis: str = typer.Option("Standalone", "--basis", help="Standalone or Consolidated."),
    swing: float = typer.Option(15.0, "--swing", "-s", help="YoY swing threshold (%) for anomaly flag."),
    material_swing: float = typer.Option(25.0, "--material-swing", "-m", help="YoY swing (%) for material severity."),
    family: str = typer.Option(None, "--family", "-f", help="Filter by family: liquidity | solvency | profitability | activity | coverage."),
    statutory_only: bool = typer.Option(False, "--statutory-only", help="Only show Schedule III mandatory ratios."),
    flagged_only: bool = typer.Option(False, "--flagged-only", help="Only show ratios with findings."),
    json_out: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Run SA 520 analytical procedures and Schedule III ratio analysis."""
    engagement_id = _resolve_engagement_id(engagement, client, period, basis)
    try:
        report = run_analytics(
            engagement_id,
            swing_threshold=swing,
            material_swing=material_swing,
        )
    except ValueError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if json_out:
        typer.echo(json.dumps(report.to_dict(), indent=2))
        return

    _print_analytics_report(
        report,
        family_filter=family,
        statutory_only=statutory_only,
        flagged_only=flagged_only,
    )


@analytics_app.command("catalog")
def analytics_catalog_command(
    family: str = typer.Option(None, "--family", "-f", help="Filter by family: liquidity | solvency | profitability | activity | coverage."),
    statutory_only: bool = typer.Option(False, "--statutory-only", help="Only show Schedule III mandatory ratios."),
) -> None:
    """List the full catalogue of ratio definitions and Schedule III requirements."""
    filtered = [
        r
        for r in RATIO_DEFINITIONS
        if (family is None or r.family.value == family.lower())
        and (not statutory_only or r.statutory)
    ]

    typer.echo(f"AuditIQ Ratio Catalogue ({len(filtered)} ratios):\n")
    typer.echo(f"  {'Code':<26} {'Stat':<6} {'Family':<15} {'Name':<32} {'Unit':<6} Formula")
    typer.echo("  " + "-" * 105)
    for r in filtered:
        stat_mark = "Y" if r.statutory else "-"
        typer.echo(
            f"  {r.code:<26} {stat_mark:<6} {r.family.value:<15} {r.name[:30]:<32} {r.unit:<6} {r.description}"
        )
    typer.echo("")


# ── Journal Entry Testing (SA 240) commands ─────────────────────────────────


@jet_app.command("test")
def jet_test_command(
    file: Path = typer.Argument(..., help="Path to Tally Prime Excel or CSV voucher export."),
    fy_end: Optional[str] = typer.Option(None, "--fy-end", help="Financial year end date (YYYY-MM-DD)."),
    severity: Optional[str] = typer.Option(None, "--severity", "-s", help="Filter by severity: high | medium | low."),
    rule: Optional[str] = typer.Option(None, "--rule", "-r", help="Filter by risk rule."),
    json_out: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Run SA 240 Journal Entry Testing and fraud risk detection on general ledger vouchers."""
    try:
        report = run_jet_file(file, fy_end_date=fy_end)
    except (FileNotFoundError, ValueError) as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if json_out:
        typer.echo(json.dumps(report.to_dict(), indent=2))
        return

    # Header
    status_color = typer.colors.GREEN
    if report.status == "high risk":
        status_color = typer.colors.RED
    elif report.status == "medium risk":
        status_color = typer.colors.YELLOW
    elif report.status == "low risk":
        status_color = typer.colors.CYAN

    typer.echo(f"\nSA 240 Journal Entry Testing -- {file.name}")
    typer.secho(f"Overall Risk Status: {report.status.upper()}", fg=status_color, bold=True)
    typer.echo(
        f"Analyzed {report.total_vouchers} vouchers ({report.total_lines} ledger lines) "
        f"from {report.date_range[0]} to {report.date_range[1]}"
    )

    types_summary = "  ".join(f"{k}: {v}" for k, v in sorted(report.voucher_type_counts.items()))
    typer.echo(f"Voucher Breakdown: {types_summary}")
    typer.echo(
        f"Risk Findings: {report.high_risk_count} High  |  {report.medium_risk_count} Medium  |  {report.low_risk_count} Low"
    )

    # Filter findings
    filtered_findings = [
        f
        for f in report.findings
        if (severity is None or f.severity.lower() == severity.lower())
        and (rule is None or f.risk_rule.lower() == rule.lower())
    ]

    if not filtered_findings:
        typer.secho("\nNo anomalies detected matching the filter.", fg=typer.colors.GREEN)
        return

    typer.echo("\n" + "=" * 105)
    typer.secho(f"FLAGGED AUDIT EXCEPTIONS ({len(filtered_findings)} findings):", bold=True)
    typer.echo("=" * 105)
    typer.echo(f"  {'Risk':<8} {'Rule':<22} {'Voucher #':<12} {'Date':<12} {'Amount (INR)':>14}  Audit Finding")
    typer.echo("-" * 105)

    for f in filtered_findings:
        if f.severity == "high":
            sev_tag = typer.style("[HIGH] ", fg=typer.colors.RED, bold=True)
        elif f.severity == "medium":
            sev_tag = typer.style("[MED]  ", fg=typer.colors.YELLOW)
        else:
            sev_tag = typer.style("[LOW]  ", fg=typer.colors.BLUE)

        amt_str = f"{f.amount:,.2f}" if f.amount > 0 else "-"
        date_str = f.date.isoformat()
        typer.echo(
            f"  {sev_tag} {f.risk_rule:<22} {str(f.voucher_number)[:10]:<12} {date_str:<12} {amt_str:>14}  {f.message}"
        )
    typer.echo("-" * 105 + "\n")


@jet_app.command("benford")
def jet_benford_command(
    file: Path = typer.Argument(..., help="Path to Tally Prime Excel or CSV voucher export."),
    json_out: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Run Benford's Law (first-digit distribution) analysis across all ledger entries."""
    try:
        report = run_jet_file(file)
    except (FileNotFoundError, ValueError) as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if not report.benford:
        typer.secho("Not enough amounts (< 50) for Benford's Law analysis.", fg=typer.colors.YELLOW)
        return

    b = report.benford
    if json_out:
        typer.echo(json.dumps(b.to_dict(), indent=2))
        return

    typer.echo(f"\nBenford's Law First-Digit Analysis -- {file.name}")
    typer.echo(f"Sample Size: {b.total_amounts} line items  |  Chi-Square Statistic: {b.chi_square:.2f}")

    if b.is_conforming:
        typer.secho("Verdict: CONFORMING (natural commercial distribution, low fraud probability)", fg=typer.colors.GREEN, bold=True)
    else:
        typer.secho("Verdict: NON-CONFORMING (significant deviation, high fraud/manipulation risk)", fg=typer.colors.RED, bold=True)

    typer.echo("\n  " + "-" * 85)
    typer.echo(f"  {'Digit':<8} {'Observed Count':<18} {'Observed %':>12} {'Expected %':>12} {'Diff %':>12}  Status")
    typer.echo("  " + "-" * 85)

    for d in range(1, 10):
        cnt = b.digit_counts.get(d, 0)
        obs = b.observed_pct.get(d, 0.0)
        exp = b.expected_pct.get(d, 0.0)
        diff = obs - exp
        if d in b.flagged_digits:
            status = typer.style("FLAGGED SPIKE", fg=typer.colors.RED, bold=True)
        else:
            status = typer.style("Normal", fg=typer.colors.GREEN)

        typer.echo(
            f"  {d:<8} {cnt:<18} {obs:>11.1f}% {exp:>11.1f}% {diff:>+11.1f}%  {status}"
        )
    typer.echo("  " + "-" * 85 + "\n")


# ── GST Reconciliation (GSTR-2B vs Books) commands ──────────────────────────


@gst_app.command("recon")
def gst_recon_command(
    books: Path = typer.Option(..., "--books", "-b", help="Path to Books Purchase Register (.xlsx or .csv)."),
    portal: Path = typer.Option(..., "--portal", "-p", help="Path to GSTN GSTR-2B / GSTR-2 (.xlsx, .csv, or .json)."),
    tolerance: float = typer.Option(5.0, "--tolerance", "-t", help="Round-off tolerance in INR."),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter: EXACT_MATCH | PROBABLE_MATCH | VALUE_MISMATCH | BOOKS_ONLY | PORTAL_ONLY | BLOCKED_CREDIT."),
    json_out: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Reconcile Books Purchase Register against GSTR-2B for Section 16(2)(aa) compliance."""
    try:
        report = run_gst_recon_files(books, portal, tolerance=tolerance)
    except (FileNotFoundError, ValueError) as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if json_out:
        typer.echo(json.dumps(report.to_dict(), indent=2))
        return

    s = report.summary
    matched_itc = s.exact_match_itc + s.probable_match_itc

    typer.echo(f"\nGST Reconciliation (Section 16(2)(aa) ITC Audit) -- {report.report_id}")
    typer.echo(f"Books File:  {books.name} ({s.books_invoice_count} invoices, Tax: INR {s.books_total_itc:,.2f})")
    typer.echo(f"Portal File: {portal.name} ({s.portal_invoice_count} invoices, Tax: INR {s.portal_total_itc:,.2f})")

    comp_color = typer.colors.GREEN if s.itc_compliance_ratio >= 90.0 else (typer.colors.YELLOW if s.itc_compliance_ratio >= 70.0 else typer.colors.RED)
    typer.secho(f"ITC Compliance Ratio: {s.itc_compliance_ratio:.2f}% (Matched ITC: INR {matched_itc:,.2f} / Books ITC: INR {s.books_total_itc:,.2f})", fg=comp_color, bold=True)

    typer.echo("\nReconciliation Summary:")
    typer.echo(f"  Exact Matches:        {s.exact_match_count:<4} (ITC: INR {s.exact_match_itc:,.2f})")
    typer.echo(f"  Probable Matches:     {s.probable_match_count:<4} (ITC: INR {s.probable_match_itc:,.2f})")
    typer.echo(f"  Value Mismatches:     {s.value_mismatch_count:<4} (Net Tax Diff: INR {s.value_mismatch_tax_diff:+,.2f})")
    if s.books_only_count > 0:
        typer.secho(f"  Books Only (S.16(2)): {s.books_only_count:<4} (At-Risk ITC: INR {s.books_only_itc:,.2f}) <-- High Audit Risk", fg=typer.colors.RED, bold=True)
    else:
        typer.echo(f"  Books Only (S.16(2)): 0    (At-Risk ITC: INR 0.00)")
    typer.echo(f"  Portal Only:          {s.portal_only_count:<4} (Unrecorded Tax: INR {s.portal_only_itc:,.2f})")
    if s.blocked_credit_count > 0:
        typer.secho(f"  Blocked S.17(5) ITC:  {s.blocked_credit_count:<4} (Reversal Needed: INR {s.blocked_credit_itc:,.2f})", fg=typer.colors.YELLOW)
    else:
        typer.echo(f"  Blocked S.17(5) ITC:  0    (Reversal Needed: INR 0.00)")

    # Filter records
    filtered = [
        r for r in report.records
        if (status is None or r.match_status.value.upper() == status.strip().upper())
    ]

    if not filtered:
        typer.secho("\nNo records found matching status filter.", fg=typer.colors.YELLOW)
        return

    typer.echo("\n" + "=" * 115)
    typer.secho(f"RECONCILIATION FINDINGS & LINE ITEMS ({len(filtered)} items):", bold=True)
    typer.echo("=" * 115)
    typer.echo(f"  {'Risk':<8} {'Status':<16} {'GSTIN':<17} {'Books Inv':<12} {'Portal Inv':<12} {'Tax Diff':>12}  Statutory Finding")
    typer.echo("-" * 115)

    for rec in filtered:
        if rec.risk_level.value == "CRITICAL":
            r_tag = typer.style("[CRIT]", fg=typer.colors.RED, bold=True)
        elif rec.risk_level.value == "HIGH":
            r_tag = typer.style("[HIGH]", fg=typer.colors.RED)
        elif rec.risk_level.value == "MEDIUM":
            r_tag = typer.style("[MED] ", fg=typer.colors.YELLOW)
        else:
            r_tag = typer.style("[LOW] ", fg=typer.colors.GREEN)

        b_inv = rec.books_invoice.invoice_number if rec.books_invoice else "-"
        p_inv = rec.portal_invoice.invoice_number if rec.portal_invoice else "-"
        gstin = (rec.books_invoice.gstin if rec.books_invoice else (rec.portal_invoice.gstin if rec.portal_invoice else "-"))[:15]
        diff_str = f"{rec.tax_difference:+,.2f}" if abs(rec.tax_difference) > Decimal("0.0") else "0.00"

        typer.echo(
            f"  {r_tag} {rec.match_status.value:<16} {gstin:<17} {b_inv[:11]:<12} {p_inv[:11]:<12} {diff_str:>12}  {rec.audit_remark[:45]}"
        )
    typer.echo("-" * 115 + "\n")


@gst_app.command("generate-demo")
def gst_generate_demo_command(
    out_dir: Path = typer.Option(Path("data/GST"), "--output-dir", "-o", help="Target output folder."),
    invoices: int = typer.Option(80, "--invoices", "-n", help="Number of invoice transactions to simulate."),
) -> None:
    """Generate realistic paired Books Purchase Register and GSTR-2B datasets for FY 2023-24."""
    typer.echo(f"Generating realistic GST datasets ({invoices} invoices) under {out_dir}...")
    b_file, p_file = generate_gst_dataset(out_dir, num_invoices=invoices)
    typer.secho(f"Books Purchase Register generated: {b_file}", fg=typer.colors.GREEN)
    typer.secho(f"Portal GSTR-2B generated:         {p_file}", fg=typer.colors.GREEN)
    typer.echo("Ready to run: auditiq gst recon --books " + str(b_file) + " --portal " + str(p_file))


@gst_app.command("inspect")
def gst_inspect_command(
    file: Path = typer.Argument(..., help="Path to GST file (.xlsx, .csv, or .json)."),
    source: str = typer.Option("portal", "--source", "-s", help="'portal' (GSTR-2B/1) or 'books' (Purchase Register)."),
    json_out: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Inspect and parse a GST Return or Books file."""
    try:
        if source.lower() == "books":
            invoices = auto_load_books_file(file)
        else:
            invoices = auto_load_portal_file(file)
    except Exception as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if json_out:
        typer.echo(json.dumps([i.model_dump(mode="json") for i in invoices], indent=2))
        return

    tot_taxable = sum((i.taxable_value for i in invoices), Decimal("0.0"))
    tot_tax = sum((i.total_tax for i in invoices), Decimal("0.0"))
    typer.echo(f"\nGST File Inspection -- {file.name}")
    typer.echo(f"Source: {source.upper()}  |  Invoices: {len(invoices)}")
    typer.echo(f"Total Taxable Value: INR {tot_taxable:,.2f}  |  Total Tax: INR {tot_tax:,.2f}\n")
    typer.echo(f"  {'GSTIN':<17} {'Invoice #':<14} {'Date':<12} {'Taxable (INR)':>14} {'Tax (INR)':>14}  Eligibility")
    typer.echo("  " + "-" * 85)
    for inv in invoices[:15]:
        dt_str = inv.invoice_date.isoformat() if inv.invoice_date else "-"
        typer.echo(
            f"  {inv.gstin:<17} {inv.invoice_number[:12]:<14} {dt_str:<12} {inv.taxable_value:>14,.2f} {inv.total_tax:>14,.2f}  {inv.itc_eligibility}"
        )
    if len(invoices) > 15:
        typer.echo(f"  ... and {len(invoices) - 15} more invoices")
    typer.echo("  " + "-" * 85 + "\n")


@api_app.command("schema")
def api_schema(
    out: Optional[Path] = typer.Option(
        None, "--out", help="Write the document here; omit to print it."
    ),
    indent: int = typer.Option(2, "--indent", min=0, max=8, help="JSON indentation."),
) -> None:
    """Export the OpenAPI document — no server or network needed."""
    try:
        from .api import create_app
    except ImportError as exc:
        typer.secho(
            'error: schema export needs the [web] extra: pip install -e ".[web]"',
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc

    text = json.dumps(create_app().openapi(), indent=indent or None, sort_keys=True)
    if out is None:
        typer.echo(text)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    typer.echo(f"wrote {out}")


@app.command("serve")
def serve_command(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address (loopback only by design)."),
    port: int = typer.Option(8765, "--port", min=1, max=65535),
    reload: bool = typer.Option(False, "--reload", help="Dev auto-reload."),
) -> None:
    """Serve the typed JSON API on this machine (docs at /docs)."""
    try:
        import uvicorn
    except ImportError as exc:
        typer.secho(
            'error: the API needs the [web] extra: pip install -e ".[web]"',
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc
    from .settings import DATABASE_URL

    typer.echo(f"serving AuditIQ {__version__}  db {DATABASE_URL}")
    if reload:
        uvicorn.run("auditiq.api.app:create_app", factory=True, host=host, port=port, reload=reload)
    else:
        from .api import create_app

        uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    app()
