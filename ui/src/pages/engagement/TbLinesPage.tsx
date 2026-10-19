import { useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { type Column } from "../../components/common/DataTable";
import { ArrowLeft, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useTbLines } from "../../api/ingest";
import { Button } from "../../components/common/Button";
import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { DataTable } from "../../components/common/DataTable";
import { ErrorBanner } from "../../components/common/ErrorBanner";
import { CardSkeleton } from "../../components/common/LoadingSkeleton";
import { ROUTES } from "../../utils/constants";
import { inr, pct, label } from "../../utils/format";
import { STATUS_COLORS } from "../../utils/colors";
import type { TbLineOut } from "../../api/types";
import "./TbLinesPage.css";

const PAGE_SIZE = 50;

export function TbLinesPage() {
  const { id } = useParams<{ id: string }>();
  const engagementId = Number(id);
  const navigate = useNavigate();

  const [page, setPage] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [searchTerm, setSearchTerm] = useState("");

  const { data: pageData, isLoading, error } = useTbLines(engagementId, {
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    status: statusFilter || undefined,
  });

  const filteredItems = useMemo(() => {
    if (!pageData?.items) return [];
    if (!searchTerm.trim()) return pageData.items;
    const q = searchTerm.toLowerCase();
    return pageData.items.filter(
      (item) =>
        item.raw_name?.toLowerCase().includes(q) ||
        item.raw_code?.toLowerCase().includes(q) ||
        item.group_name?.toLowerCase().includes(q) ||
        item.fsli_code?.toLowerCase().includes(q)
    );
  }, [pageData?.items, searchTerm]);

  const columns: Column<TbLineOut>[] = [
    {
      key: "raw_code",
      header: "Ledger Code",
      cell: (item) => (
        <span className="mono">{item.raw_code ?? "-"}</span>
      ),
    },
    {
      key: "raw_name",
      header: "Ledger Name",
      cell: (item) => (
        <span className="cell-name">{item.raw_name ?? ""}</span>
      ),
    },
    {
      key: "group_name",
      header: "Group",
      cell: (item) => (
        <span className="cell-muted">{item.group_name ?? "-"}</span>
      ),
    },
    {
      key: "normalized_amount",
      header: "Amount",
      cell: (item) => (
        <span className="mono amount-cell">
          {inr(item.normalized_amount ?? 0)}
        </span>
      ),
    },
    {
      key: "side",
      header: "Side",
      cell: (item) => {
        const side = (item.side ?? "").toUpperCase();
        return (
          <Badge
            size="sm"
            variant="outlined"
            color={side === "DR" ? "var(--info)" : "var(--accent)"}
          >
            {side || "-"}
          </Badge>
        );
      },
    },
    {
      key: "fsli_code",
      header: "Mapped FSLI",
      cell: (item) =>
        item.fsli_code ? (
          <span className="mono fsli-tag">{item.fsli_code}</span>
        ) : (
          <span className="cell-muted">—</span>
        ),
    },
    {
      key: "mapping_status",
      header: "Status",
      cell: (item) => {
        const st = item.mapping_status ?? "unmapped";
        return (
          <Badge
            size="sm"
            color={STATUS_COLORS[st] ?? "var(--text-secondary)"}
          >
            {label(st)}
          </Badge>
        );
      },
    },
    {
      key: "mapping_method",
      header: "Method",
      cell: (item) => (
        <span className="cell-muted">{item.mapping_method ?? "-"}</span>
      ),
    },
    {
      key: "mapping_confidence",
      header: "Confidence",
      cell: (item) => {
        const conf = item.mapping_confidence;
        if (conf == null) return <span className="cell-muted">—</span>;
        return (
          <div className="confidence-cell">
            <div className="confidence-bar">
              <div
                className="confidence-fill"
                style={{ width: `${Math.min(100, conf * 100)}%` }}
              />
            </div>
            <span className="mono">{pct(conf * 100)}</span>
          </div>
        );
      },
    },
  ];

  const totalPages = pageData ? Math.ceil(pageData.total / PAGE_SIZE) : 0;

  return (
    <div className="tb-lines-page fade-in">
      <div className="page-header">
        <div className="header-nav">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(ROUTES.engagement(engagementId))}
            icon={<ArrowLeft size={16} />}
          >
            Overview
          </Button>
          <h1 className="page-title">Trial Balance Lines</h1>
        </div>
        <div className="header-meta">
          {pageData && (
            <span className="total-badge mono">
              Total {pageData.total.toLocaleString()} lines
            </span>
          )}
        </div>
      </div>

      <ErrorBanner error={error as Error} />

      <Card padding="md" className="filter-bar">
        <div className="filter-controls">
          <div className="search-box">
            <Search size={16} className="search-icon" />
            <input
              type="text"
              className="search-input"
              placeholder="Search by code, ledger name, or group..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div className="status-filter">
            <label htmlFor="tb-status" className="filter-label">
              Status:
            </label>
            <select
              id="tb-status"
              className="filter-select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(0);
              }}
            >
              <option value="">All Statuses</option>
              <option value="auto">Auto-Mapped</option>
              <option value="pending_review">Pending Review</option>
              <option value="resolved">Resolved</option>
              <option value="unmapped">Unmapped</option>
            </select>
          </div>
        </div>
      </Card>

      {isLoading ? (
        <CardSkeleton />
      ) : (
        <Card padding="none">
          <DataTable
            columns={columns}
            data={filteredItems}
            emptyMessage="No trial balance lines match the filter criteria."
          />

          <div className="table-pagination">
            <span className="pagination-info">
              Showing {page * PAGE_SIZE + 1} to{" "}
              {Math.min((page + 1) * PAGE_SIZE, pageData?.total ?? 0)} of{" "}
              {pageData?.total ?? 0}
            </span>
            <div className="pagination-buttons">
              <Button
                variant="secondary"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                icon={<ChevronLeft size={16} />}
              >
                Previous
              </Button>
              <span className="page-indicator mono">
                Page {page + 1} of {Math.max(1, totalPages)}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => p + 1)}
                icon={<ChevronRight size={16} />}
              >
                Next
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
