import { useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { type Column } from "../../components/common/DataTable";
import {
  CheckCircle,
  ArrowLeft,
  Sparkles,
} from "lucide-react";
import {
  useExceptions,
  useDisposeException,
} from "../../api/exceptions";
import { Card } from "../../components/common/Card";
import { Button } from "../../components/common/Button";
import { Badge } from "../../components/common/Badge";
import { DataTable } from "../../components/common/DataTable";
import { Dialog } from "../../components/common/Dialog";
import { ErrorBanner } from "../../components/common/ErrorBanner";
import { CardSkeleton } from "../../components/common/LoadingSkeleton";
import { EmptyState } from "../../components/common/EmptyState";
import { inr, label } from "../../utils/format";
import { SEVERITY_COLORS, STATUS_COLORS } from "../../utils/colors";
import { ROUTES } from "../../utils/constants";
import type { ExceptionOut } from "../../api/types";
import "./ExceptionsPage.css";

export function ExceptionsPage() {
  const { id } = useParams<{ id: string }>();
  const engagementId = Number(id);
  const navigate = useNavigate();

  const { data: exceptions, isLoading, error } = useExceptions(engagementId);
  const dispose = useDisposeException(engagementId);

  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [activeException, setActiveException] = useState<ExceptionOut | null>(null);
  const [disposeStatus, setDisposeStatus] = useState<string>("explained");
  const [disposeNote, setDisposeNote] = useState<string>("");

  const filtered = useMemo(() => {
    if (!exceptions) return [];
    if (statusFilter === "all") return exceptions;
    return exceptions.filter((ex) => ex.status === statusFilter);
  }, [exceptions, statusFilter]);

  const handleOpenDispose = (ex: ExceptionOut) => {
    setActiveException(ex);
    setDisposeStatus(ex.status === "open" ? "explained" : ex.status);
    setDisposeNote(ex.note || "");
  };

  const handleSubmitDispose = (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeException) return;

    dispose.mutate(
      {
        exceptionId: activeException.exception_id,
        data: {
          status: disposeStatus,
          note: disposeNote.trim() || undefined,
        },
      },
      {
        onSuccess: () => {
          setActiveException(null);
        },
      }
    );
  };

  const columns: Column<ExceptionOut>[] = [
    {
      key: "exception_id",
      header: "#",
      cell: (item) => (
        <span className="mono text-xs">EX-{item.exception_id}</span>
      ),
    },
    {
      key: "kind",
      header: "Issue Kind",
      cell: (item) => (
        <span className="font-semibold text-primary">
          {label(item.kind)}
        </span>
      ),
    },
    {
      key: "fsli",
      header: "FSLI / Scope",
      cell: (item) =>
        item.fsli ? (
          <span className="mono text-accent">{item.fsli}</span>
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      key: "amount",
      header: "Exposure Amount",
      cell: (item) =>
        item.amount != null ? (
          <span className="mono font-bold amount-cell">{inr(item.amount)}</span>
        ) : (
          <span className="text-muted amount-cell">—</span>
        ),
    },
    {
      key: "severity",
      header: "Severity",
      cell: (item) => (
        <Badge
          size="sm"
          color={SEVERITY_COLORS[item.severity] ?? "var(--text-secondary)"}
          pulse={item.severity === "material"}
        >
          {label(item.severity)}
        </Badge>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (item) => (
        <Badge
          size="sm"
          variant="outlined"
          color={STATUS_COLORS[item.status] ?? "var(--text-secondary)"}
        >
          {label(item.status)}
        </Badge>
      ),
    },
    {
      key: "note",
      header: "Audit Disposition Note",
      cell: (item) =>
        item.note ? (
          <span className="text-xs text-secondary line-clamp-2">{item.note}</span>
        ) : (
          <span className="text-muted text-xs italic">Pending review</span>
        ),
    },
    {
      key: "actions",
      header: "",
      sortable: false,
      cell: (item) => (
        <Button
          size="sm"
          variant="secondary"
          onClick={(e) => {
            e.stopPropagation();
            handleOpenDispose(item);
          }}
        >
          Dispose
        </Button>
      ),
    },
  ];

  const openCount = exceptions?.filter((e) => e.status === "open").length ?? 0;

  return (
    <div className="exceptions-page fade-in">
      <div className="page-header">
        <div className="header-nav">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(ROUTES.recon(engagementId))}
            icon={<ArrowLeft size={16} />}
          >
            Reconciliation
          </Button>
          <h1 className="page-title">Audit Exceptions & Dispositions</h1>
        </div>
        {openCount > 0 && (
          <Badge color="var(--danger)" pulse>
            {openCount} Open Exception{openCount > 1 ? "s" : ""}
          </Badge>
        )}
      </div>

      <ErrorBanner error={(error || dispose.error) as Error} />

      {/* Filter Tabs */}
      <div className="exception-filter-bar">
        <div className="tabs">
          <button
            className={`tab-btn ${statusFilter === "all" ? "tab-btn--active" : ""}`}
            onClick={() => setStatusFilter("all")}
          >
            All Issues ({exceptions?.length ?? 0})
          </button>
          <button
            className={`tab-btn ${statusFilter === "open" ? "tab-btn--active" : ""}`}
            onClick={() => setStatusFilter("open")}
          >
            Open ({openCount})
          </button>
          <button
            className={`tab-btn ${statusFilter === "explained" ? "tab-btn--active" : ""}`}
            onClick={() => setStatusFilter("explained")}
          >
            Explained (
            {exceptions?.filter((e) => e.status === "explained").length ?? 0})
          </button>
          <button
            className={`tab-btn ${statusFilter === "accepted" ? "tab-btn--active" : ""}`}
            onClick={() => setStatusFilter("accepted")}
          >
            Accepted (
            {exceptions?.filter((e) => e.status === "accepted").length ?? 0})
          </button>
        </div>
      </div>

      {isLoading ? (
        <CardSkeleton />
      ) : filtered.length > 0 ? (
        <Card padding="none">
          <DataTable
            columns={columns}
            data={filtered}
            onRowClick={handleOpenDispose}
          />
        </Card>
      ) : (
        <EmptyState
          icon={<Sparkles size={48} />}
          title="No Exceptions in this View"
          description={
            statusFilter === "open"
              ? "All identified exceptions have been formally disposed or explained."
              : "No exceptions recorded for this engagement."
          }
        />
      )}

      {/* Dispose Dialog */}
      <Dialog
        open={!!activeException}
        onClose={() => setActiveException(null)}
        title={`Audit Disposition — EX-${activeException?.exception_id}`}
        width="540px"
      >
        {activeException && (
          <form onSubmit={handleSubmitDispose} className="dispose-form">
            <div className="dispose-details">
              <div className="flex-between">
                <span className="font-semibold text-primary">
                  {label(activeException.kind)}
                </span>
                <Badge
                  color={
                    SEVERITY_COLORS[activeException.severity] ??
                    "var(--text-secondary)"
                  }
                >
                  {label(activeException.severity)}
                </Badge>
              </div>
              {activeException.amount != null && (
                <div className="text-sm mt-1">
                  Exposure:{" "}
                  <strong className="mono">{inr(activeException.amount)}</strong>
                </div>
              )}
              {activeException.detail && (
                <p className="detail-box">{activeException.detail}</p>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="dispose-status" className="form-label">
                Disposition Status *
              </label>
              <select
                id="dispose-status"
                className="form-input"
                value={disposeStatus}
                onChange={(e) => setDisposeStatus(e.target.value)}
              >
                <option value="explained">Explained by Management / Audit Workpaper</option>
                <option value="accepted">Accepted / Immaterial Under ISA 450</option>
                <option value="open">Keep Open / Escalated</option>
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="dispose-note" className="form-label">
                Audit Workpaper Note / Reference
              </label>
              <textarea
                id="dispose-note"
                rows={4}
                className="form-input text-sm"
                placeholder="Document client explanation, journal entry reclassification, or workpaper reference..."
                value={disposeNote}
                onChange={(e) => setDisposeNote(e.target.value)}
              />
            </div>

            <div className="form-actions">
              <Button
                variant="secondary"
                type="button"
                onClick={() => setActiveException(null)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                loading={dispose.isPending}
                icon={<CheckCircle size={16} />}
              >
                Confirm Disposition
              </Button>
            </div>
          </form>
        )}
      </Dialog>
    </div>
  );
}
