"""AuditIQ Core command-line interface."""
from __future__ import annotations

import typer

from . import __version__
from .core import load_default_taxonomy
from .ingest.erp import ADAPTERS, ingest_tb
from .ingest.fs import (
    build_fs_mapper,
    extract_statements,
    ingest_fs,
    label_rows,
    read_fs,
    summarise,
)
from .ingest.prepare import (
    default_encoder_kind,
    load_labelled_csv,
    map_engagement,
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
from .store import init_db, session_scope
from .store.models import Engagement, FsLine, NoteItem, ReconLine, ReconRun, TbLine

app = typer.Typer(help="AuditIQ Core — ingestion, reconciliation and review.", no_args_is_help=True)
taxonomy_app = typer.Typer(help="Inspect the Schedule III FSLI taxonomy.", no_args_is_help=True)
store_app = typer.Typer(help="Manage the AuditIQ database.", no_args_is_help=True)
ingest_app = typer.Typer(help="Ingest source data (trial balances, statements).", no_args_is_help=True)
fs_app = typer.Typer(help="Financial-statement ingestion and coverage.", no_args_is_help=True)
recon_app = typer.Typer(help="Reconcile the books with the draft financial statements.", no_args_is_help=True)
materiality_app = typer.Typer(help="Set and suggest engagement materiality.", no_args_is_help=True)
app.add_typer(taxonomy_app, name="taxonomy")
app.add_typer(store_app, name="store")
app.add_typer(ingest_app, name="ingest")
app.add_typer(fs_app, name="fs")
app.add_typer(recon_app, name="recon")
app.add_typer(materiality_app, name="materiality")

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
) -> None:
    """Report FS-label -> FSLI coverage for a document (no persistence)."""
    try:
        document = read_fs(path, kind)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    statements = extract_statements(document)
    if not statements:
        typer.secho("error: no statement detected in document", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    mapper, _thresholds, encoder_kind, tuned = build_fs_mapper(
        client=client, encoder_kind=encoder
    )
    labelled = label_rows(statements, mapper, client=client or "")
    summary = summarise(labelled, encoder_kind, tuned)

    typer.echo(f"document      {path}")
    typer.echo(f"encoder       {summary.encoder}{'' if summary.tuned else '  (untuned defaults)'}")
    typer.echo(f"rows          {summary.rows}")
    typer.echo(f"coverage      {summary.mapped}/{summary.rows} ({summary.coverage:.1%})")
    for layer, count in sorted(summary.by_layer.items()):
        typer.echo(f"  by {layer:<6} {count}")

    unmapped = [item for item in labelled if not item.mapped]
    if unmapped:
        typer.echo("unmapped:")
        for item in unmapped:
            typer.echo(f"  [{item.statement}] {item.row.label}")


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


if __name__ == "__main__":
    app()
