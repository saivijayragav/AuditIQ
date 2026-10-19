import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  CheckCircle,
  Sparkles,
  ArrowRight,
  ArrowLeft,
} from "lucide-react";
import {
  useFsReview,
  useResolveFsLine,
  useResetFsLine,
} from "../../api/mapping";
import { useTaxonomy, useGroups } from "../../api/reference";
import { Card } from "../../components/common/Card";
import { Button } from "../../components/common/Button";
import { Badge } from "../../components/common/Badge";
import { ErrorBanner } from "../../components/common/ErrorBanner";
import { EmptyState } from "../../components/common/EmptyState";
import { CardSkeleton } from "../../components/common/LoadingSkeleton";
import { ROUTES } from "../../utils/constants";
import { inr } from "../../utils/format";
import type { FsUnmappedOut } from "../../api/types";
import "./FsReviewPage.css";

export function FsReviewPage() {
  const { id } = useParams<{ id: string }>();
  const engagementId = Number(id);
  const navigate = useNavigate();

  const { data: unmappedLines, isLoading, error } = useFsReview(engagementId);
  const { data: taxonomy } = useTaxonomy();
  const { data: groups } = useGroups();

  const resolveLine = useResolveFsLine(engagementId);
  const resetLine = useResetFsLine(engagementId);

  // Per-row assignment: { [lineId]: { type: "fsli" | "group", code: string } }
  const [assignments, setAssignments] = useState<
    Record<number, { type: "fsli" | "group"; code: string }>
  >({});

  const handleResolve = (line: FsUnmappedOut) => {
    const selected = assignments[line.line_id];
    if (!selected?.code) return;

    resolveLine.mutate({
      lineId: line.line_id,
      data: {
        fsli_code: selected.type === "fsli" ? selected.code : null,
        group_code: selected.type === "group" ? selected.code : null,
      },
    });
  };

  return (
    <div className="fs-review fade-in">
      <div className="page-header">
        <div className="header-nav">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(ROUTES.ingestFs(engagementId))}
            icon={<ArrowLeft size={16} />}
          >
            Ingest FS
          </Button>
          <h1 className="page-title">Financial Statements Review</h1>
        </div>
        <Button
          variant="secondary"
          onClick={() => navigate(ROUTES.materiality(engagementId))}
          icon={<ArrowRight size={16} />}
        >
          Proceed to Materiality
        </Button>
      </div>

      <ErrorBanner error={(error || resolveLine.error || resetLine.error) as Error} />

      {isLoading ? (
        <CardSkeleton />
      ) : unmappedLines && unmappedLines.length > 0 ? (
        <Card padding="none">
          <div className="review-banner">
            <span className="banner-text">
              Found <strong>{unmappedLines.length}</strong> unmapped disclosure
              label{unmappedLines.length > 1 ? "s" : ""} in the draft Financial
              Statements. Map them to a standard FSLI or roll-up Group to ensure full
              reconciliation coverage.
            </span>
          </div>

          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Statement</th>
                  <th>Extracted Label</th>
                  <th>Periods</th>
                  <th>Total Amount</th>
                  <th>Rows</th>
                  <th>Map To FSLI / Group</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {unmappedLines.map((line) => {
                  const current = assignments[line.line_id] || {
                    type: "fsli",
                    code: "",
                  };

                  return (
                    <tr key={line.line_id}>
                      <td>
                        <Badge
                          size="sm"
                          variant="outlined"
                          color={
                            line.statement === "BS"
                              ? "var(--accent)"
                              : "var(--info)"
                          }
                        >
                          {line.statement}
                        </Badge>
                      </td>
                      <td>
                        <span className="font-semibold text-primary">
                          {line.label}
                        </span>
                      </td>
                      <td>
                        <span className="mono text-xs text-secondary">
                          {line.periods?.join(", ") || "—"}
                        </span>
                      </td>
                      <td className="mono font-semibold">
                        {inr(line.abs_total ?? line.total)}
                      </td>
                      <td>
                        <Badge
                          size="sm"
                          variant="outlined"
                          color="var(--text-secondary)"
                        >
                          {line.rows} rows
                        </Badge>
                      </td>
                      <td>
                        <select
                          className="fs-select"
                          value={
                            current.code
                              ? `${current.type}:${current.code}`
                              : ""
                          }
                          onChange={(e) => {
                            const [type, code] = e.target.value.split(":");
                            setAssignments((prev) => ({
                              ...prev,
                              [line.line_id]: {
                                type: type as "fsli" | "group",
                                code: code || "",
                              },
                            }));
                          }}
                        >
                          <option value="">Select target...</option>
                          <optgroup label="Standard FSLIs">
                            {taxonomy?.map((t) => (
                              <option
                                key={`fsli:${t.code}`}
                                value={`fsli:${t.code}`}
                              >
                                {t.code} — {t.name} ({t.statement})
                              </option>
                            ))}
                          </optgroup>
                          <optgroup label="Rollup Groups">
                            {groups?.map((g) => (
                              <option
                                key={`group:${g.code}`}
                                value={`group:${g.code}`}
                              >
                                [Group] {g.name}
                              </option>
                            ))}
                          </optgroup>
                        </select>
                      </td>
                      <td>
                        <Button
                          size="sm"
                          disabled={!current.code}
                          loading={
                            resolveLine.isPending &&
                            resolveLine.variables?.lineId === line.line_id
                          }
                          onClick={() => handleResolve(line)}
                          icon={<CheckCircle size={14} />}
                        >
                          Resolve
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        <EmptyState
          icon={<Sparkles size={48} />}
          title="All Financial Statement Rows Mapped!"
          description="Every statement label extracted from the draft financial statements is matched with a valid FSLI or roll-up group."
          action={
            <Button
              onClick={() => navigate(ROUTES.materiality(engagementId))}
              icon={<ArrowRight size={16} />}
            >
              Continue to Materiality
            </Button>
          }
        />
      )}
    </div>
  );
}
