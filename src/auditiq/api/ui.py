"""Server-rendered audit workspace (Jinja2 + HTMX, vendored assets).

The UI is a thin test harness over the same services the JSON API and the CLI
use: one page per workflow step, fragments swapped in by HTMX. No build step,
no CDN — everything under ``api/static`` ships with the package.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from ..ingest.erp import ingest_tb
from ..ingest.fs import ingest_fs, list_unmapped_fs, resolve_fs_line, reset_fs_line
from ..ingest.prepare import (
    bulk_resolve,
    list_pending,
    list_resolved,
    map_engagement,
    reset_mapping,
    resolve_mapping,
)
from ..reconciliation import (
    MaterialityError,
    explain_unit,
    latest_run,
    run_recon,
    set_materiality,
    suggest_for_engagement,
)
from ..store.queries import (
    create_engagement,
    dispose_exception,
    engagement_summary,
    list_exceptions,
    list_engagements,
)
from .app import _parse_statements, _source


TAB_LABELS: dict[str, str] = {
    "ingest": "Ingest",
    "map": "Map FSLIs",
    "review": "Review queue",
    "materiality": "Materiality",
    "results": "Reconcile",
    "fsreview": "FS review",
    "exceptions": "Exceptions",
}
TABS = tuple(TAB_LABELS)


def ui_router(templates) -> APIRouter:  # noqa: C901
    router = APIRouter()

    # -- helpers ---------------------------------------------------------------

    def page(request: Request, name: str, status_code: int = 200, **ctx):
        return templates.TemplateResponse(
            request, name, {"request": request, **ctx}, status_code=status_code
        )

    def alert(request: Request, message: str, kind: str = "error"):
        return page(request, "partials/alert.html", message=str(message), kind=kind)

    def _eng_ctx(request: Request, eid: int) -> Optional[dict]:
        try:
            return {"e": engagement_summary(eid)}
        except ValueError:
            return None

    def not_found(request: Request, eid: int):
        return page(request, "partials/alert.html", message=f"no engagement with id {eid}")

    def render_tab(request: Request, eid: int, tab: str, error: Optional[str] = None, **extra):
        ctx = {"e": engagement_summary(eid), "tab": tab, "tab_label": TAB_LABELS[tab]}
        if error:
            ctx["error"] = error
        ctx.update(extra)
        if tab == "review":
            ctx["pending"] = list_pending(eid)
            ctx["resolved"] = list_resolved(eid, limit=25)
        elif tab == "materiality":
            suggestion = _try(suggest_for_engagement, eid)
            if suggestion and not suggestion.get("suggested"):
                suggestion = None  # no Side B yet — nothing to suggest from
            ctx["suggestion"] = suggestion
        elif tab == "results":
            run, lines = latest_run(eid)
            ctx["run"] = run
            ctx["lines"] = lines
        elif tab == "fsreview":
            ctx["labels"] = list_unmapped_fs(eid)
        elif tab == "exceptions":
            ctx["rows"] = list_exceptions(eid)
        return page(request, f"partials/{tab}.html", **ctx)

    def _try(fn, *args, **kw):
        try:
            return fn(*args, **kw)
        except (ValueError, MaterialityError):
            return None

    # -- pages -----------------------------------------------------------------

    @router.get("/ui", response_class=HTMLResponse)
    def ui_home(request: Request):
        return page(request, "engagements.html", engagements=list_engagements())

    @router.post("/ui", response_class=HTMLResponse)
    def ui_create(request: Request, client_code: str = Form(""), period: str = Form(""), basis: str = Form("Standalone"), client_name: str = Form("")):
        try:
            summary = create_engagement(client_code, period, basis=basis, client_name=client_name)
        except ValueError as exc:
            return page(
                request,
                "engagements.html",
                engagements=list_engagements(),
                error=str(exc),
            )
        return RedirectResponse(f"/ui/engagements/{summary.engagement_id}", status_code=303)

    @router.get("/ui/engagements/{eid}", response_class=HTMLResponse)
    def workspace(request: Request, eid: int):
        e = _eng_ctx(request, eid)
        if e is None:
            return not_found(request, eid)
        return page(request, "workspace.html", tabs=TABS, tab_labels=TAB_LABELS, tab="ingest", **e)

    @router.get("/ui/engagements/{eid}/tabs/{tab}", response_class=HTMLResponse)
    def tab(request: Request, eid: int, tab: str):
        if tab not in TAB_LABELS:
            return alert(request, f"unknown tab '{tab}'")
        try:
            return render_tab(request, eid, tab)
        except ValueError as exc:
            return alert(request, str(exc))

    # -- ingest ---------------------------------------------------------------

    @router.post("/ui/engagements/{eid}/ingest/tb", response_class=HTMLResponse)
    def ingest_tb_ui(request: Request, eid: int, file: Optional[UploadFile] = File(None), path: str = Form("")):
        ctx = _eng_ctx(request, eid)
        if ctx is None:
            return not_found(request, eid)
        try:
            source = _source(file, path or None)
            e = ctx["e"]
            result = ingest_tb(
                source,
                client_code=e.client_code,
                period=e.period,
                basis=e.basis,
                client_name=e.client_name,
            )
            return render_tab(request, eid, "ingest", tb_result=result)
        except (ValueError, FileNotFoundError) as exc:
            return render_tab(request, eid, "ingest", error=str(exc))

    @router.post("/ui/engagements/{eid}/ingest/fs", response_class=HTMLResponse)
    def ingest_fs_ui(request: Request, eid: int, file: Optional[UploadFile] = File(None), path: str = Form(""), kind: str = Form(""), unit: str = Form("")):
        ctx = _eng_ctx(request, eid)
        if ctx is None:
            return not_found(request, eid)
        try:
            source = _source(file, path or None)
            e = ctx["e"]
            result = ingest_fs(
                source,
                client_code=e.client_code,
                period=e.period,
                basis=e.basis,
                kind=kind or None,
                client_name=e.client_name,
                unit=unit or None,
            )
            return render_tab(request, eid, "ingest", fs_result=result)
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return render_tab(request, eid, "ingest", error=str(exc))

    # -- map ------------------------------------------------------------------

    @router.post("/ui/engagements/{eid}/map", response_class=HTMLResponse)
    def map_ui(request: Request, eid: int, encoder: str = Form("")):
        try:
            summary = map_engagement(eid, encoder_kind=encoder or None)
            return render_tab(request, eid, "map", summary=summary)
        except (ValueError, RuntimeError) as exc:
            return render_tab(request, eid, "map", error=str(exc))

    # -- review ---------------------------------------------------------------

    @router.post("/ui/engagements/{eid}/review/resolve", response_class=HTMLResponse)
    def resolve_ui(request: Request, eid: int, line_id: int = Form(0), fsli: str = Form(""), reviewer: str = Form("")):
        try:
            resolve_mapping(line_id, fsli, reviewer=reviewer)
            return render_tab(request, eid, "review")
        except ValueError as exc:
            return render_tab(request, eid, "review", error=str(exc))

    @router.post("/ui/engagements/{eid}/review/bulk", response_class=HTMLResponse)
    def bulk_ui(request: Request, eid: int, reviewer: str = Form("")):
        """Approve every pending head with the cascade's top candidate."""
        try:
            heads = list_pending(eid)
            pairs = []
            for head in heads:
                if head.candidates:
                    pairs.append((head.line_id, head.candidates[0]))
            results, failures = bulk_resolve(pairs, reviewer=reviewer)
            error = None if not failures else f"{len(failures)} of {len(pairs)} bulk approvals were rejected"
            return render_tab(request, eid, "review", error=error)
        except ValueError as exc:
            return render_tab(request, eid, "review", error=str(exc))

    @router.post("/ui/engagements/{eid}/review/reset", response_class=HTMLResponse)
    def reset_ui(request: Request, eid: int, line_id: int = Form(0)):
        try:
            reset_mapping(line_id)
            return render_tab(request, eid, "review")
        except ValueError as exc:
            return render_tab(request, eid, "review", error=str(exc))

    # -- materiality ----------------------------------------------------------

    @router.post("/ui/engagements/{eid}/materiality", response_class=HTMLResponse)
    def materiality_ui(request: Request, eid: int, value: float = Form(0.0), basis: str = Form("")):
        try:
            set_materiality(eid, value, basis)
            return render_tab(request, eid, "materiality")
        except (ValueError, MaterialityError) as exc:
            return render_tab(request, eid, "materiality", error=str(exc))

    # -- results --------------------------------------------------------------

    @router.post("/ui/engagements/{eid}/recon/run", response_class=HTMLResponse)
    def recon_ui(request: Request, eid: int, statements: str = Form("all"), side_b_period: str = Form("")):
        try:
            run_recon(
                eid,
                statements=_parse_statements(statements),
                side_b_period=side_b_period or None,
            )
        except (MaterialityError, ValueError, RuntimeError) as exc:
            return render_tab(request, eid, "results", error=str(exc))
        return render_tab(request, eid, "results")

    @router.get("/ui/engagements/{eid}/results/explain/{code}", response_class=HTMLResponse)
    def explain_ui(request: Request, eid: int, code: str):
        _run, line = explain_unit(eid, code)
        if line is None:
            return page(request, "partials/alert.html", message=f"unit '{code}' is not in the latest run")
        return page(request, "partials/explain.html", line=line, run=_run)

    # -- fs review ------------------------------------------------------------

    @router.post("/ui/engagements/{eid}/fsreview/resolve", response_class=HTMLResponse)
    def fs_resolve_ui(request: Request, eid: int, line_id: int = Form(0), fsli: str = Form(""), group: str = Form("")):
        try:
            resolve_fs_line(line_id, fsli_code=fsli or None, group_code=group or None)
            return render_tab(request, eid, "fsreview")
        except ValueError as exc:
            return render_tab(request, eid, "fsreview", error=str(exc))

    @router.post("/ui/engagements/{eid}/fsreview/reset", response_class=HTMLResponse)
    def fs_reset_ui(request: Request, eid: int, line_id: int = Form(0)):
        try:
            reset_fs_line(line_id)
            return render_tab(request, eid, "fsreview")
        except ValueError as exc:
            return render_tab(request, eid, "fsreview", error=str(exc))

    # -- exceptions -----------------------------------------------------------

    @router.post("/ui/engagements/{eid}/exceptions/{exception_id}/dispose", response_class=HTMLResponse)
    def dispose_ui(request: Request, eid: int, exception_id: int, status: str = Form(""), note: str = Form("")):
        try:
            dispose_exception(exception_id, status, note=note)
            return render_tab(request, eid, "exceptions")
        except ValueError as exc:
            return render_tab(request, eid, "exceptions", error=str(exc))

    return router
