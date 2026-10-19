import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Play,
  CheckCircle,
  RotateCcw,
  CheckSquare,
  Sparkles,
  Layers,
  ArrowRight,
} from "lucide-react";
import {
  useRunMapping,
  usePendingMappings,
  useResolvedMappings,
  useMappingCounts,
  useResolveMapping,
  useBulkResolve,
  useResetMapping,
} from "../../api/mapping";
import { useMeta, useTaxonomy } from "../../api/reference";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/common/Card";
import { Button } from "../../components/common/Button";
import { Badge } from "../../components/common/Badge";
import { Metric } from "../../components/common/Metric";
import { ErrorBanner } from "../../components/common/ErrorBanner";
import { MappingDonut } from "../../components/charts/MappingDonut";
import { CardSkeleton } from "../../components/common/LoadingSkeleton";
import { EmptyState } from "../../components/common/EmptyState";
import { inr, pct, num } from "../../utils/format";
import { ROUTES } from "../../utils/constants";
import type { MappingSummaryOut, PendingHeadOut } from "../../api/types";
import "./MappingPage.css";

export function MappingPage() {
  const { id } = useParams<{ id: string }>();
  const engagementId = Number(id);
  const navigate = useNavigate();

  const { data: meta } = useMeta();
  const { data: taxonomy } = useTaxonomy();
  const { data: counts, refetch: refetchCounts } = useMappingCounts(engagementId);
  const { data: pendingHeads, isLoading: loadingPending } = usePendingMappings(engagementId);
  const { data: resolvedHeads, isLoading: loadingResolved } = useResolvedMappings(engagementId);

  const runMapping = useRunMapping(engagementId);
  const resolveMapping = useResolveMapping(engagementId);
  const bulkResolve = useBulkResolve(engagementId);
  const resetMapping = useResetMapping(engagementId);

  const [activeTab, setActiveTab] = useState<"pending" | "resolved">("pending");
  const [selectedEncoder, setSelectedEncoder] = useState<string>("auto");
  const [useLlm, setUseLlm] = useState<boolean>(false);
  const [runResult, setRunResult] = useState<MappingSummaryOut | null>(null);

  // Per-row selected candidate
  const [rowSelections, setRowSelections] = useState<Record<number, string>>({});
  // Bulk selection checkboxes
  const [bulkChecked, setBulkChecked] = useState<Set<number>>(new Set());
  const [reviewerName, setReviewerName] = useState("Auditor");

  const handleRunCascade = () => {
    runMapping.mutate(
      {
        encoder: selectedEncoder || undefined,
        use_llm: useLlm,
      },
      {
        onSuccess: (data) => {
          setRunResult(data);
          refetchCounts();
        },
      }
    );
  };

  const handleSingleResolve = (head: PendingHeadOut) => {
    const fsliCode = rowSelections[head.line_id] || head.candidates?.[0];
    if (!fsliCode) return;

    resolveMapping.mutate({
      line_id: head.line_id,
      fsli_code: fsliCode,
      reviewer: reviewerName,
    });
  };

  const handleBulkApprove = () => {
    if (bulkChecked.size === 0 || !pendingHeads) return;

    const pairs: [number, string][] = [];
    for (const head of pendingHeads) {
      if (bulkChecked.has(head.line_id)) {
        const fsli = rowSelections[head.line_id] || head.candidates?.[0];
        if (fsli) {
          pairs.push([head.line_id, fsli]);
        }
      }
    }

    if (pairs.length === 0) return;

    bulkResolve.mutate(
      {
        pairs,
        reviewer: reviewerName,
      },
      {
        onSuccess: () => {
          setBulkChecked(new Set());
        },
      }
    );
  };

  const toggleBulkSelect = (lineId: number) => {
    setBulkChecked((prev) => {
      const next = new Set(prev);
      if (next.has(lineId)) next.delete(lineId);
      else next.add(lineId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (!pendingHeads) return;
    if (bulkChecked.size === pendingHeads.length) {
      setBulkChecked(new Set());
    } else {
      setBulkChecked(new Set(pendingHeads.map((h) => h.line_id)));
    }
  };

  const totalLines = counts?.total ?? 0;
  const resolvedCount = counts?.counts?.["resolved"] ?? 0;
  const pendingCount = counts?.counts?.["pending_review"] ?? 0;
  const unmappedCount = counts?.counts?.["unmapped"] ?? 0;
  const resolvedPct = totalLines > 0 ? (resolvedCount / totalLines) * 100 : 0;
  const pendingPct = totalLines > 0 ? (pendingCount / totalLines) * 100 : 0;
  const unmappedPct = totalLines > 0 ? (unmappedCount / totalLines) * 100 : 0;

  return (
    <div className="mapping-page fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">FSLI Mapping & Review</h1>
          <p className="page-subtitle">
            Automated multi-layer mapping cascade with human review of ambiguous ledger heads.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => navigate(ROUTES.ingestFs(engagementId))}
          icon={<ArrowRight size={16} />}
        >
          Proceed to Ingest FS
        </Button>
      </div>

      <ErrorBanner
        error={
          (runMapping.error || resolveMapping.error || bulkResolve.error) as Error
        }
      />

      {/* Mapping Progress Bar */}
      {counts && totalLines > 0 && (
        <Card padding="md" className="progress-banner">
          <div className="progress-header">
            <span className="progress-title">Mapping Progress</span>
            <span className="mono progress-summary">
              {resolvedCount} Resolved · {pendingCount} In Review · {unmappedCount} Unmapped ({totalLines} total)
            </span>
          </div>
          <div className="stacked-progress">
            <div
              className="progress-bar progress-resolved"
              style={{ width: `${resolvedPct}%` }}
              title={`Resolved: ${resolvedCount}`}
            />
            <div
              className="progress-bar progress-pending"
              style={{ width: `${pendingPct}%` }}
              title={`Pending Review: ${pendingCount}`}
            />
            <div
              className="progress-bar progress-unmapped"
              style={{ width: `${unmappedPct}%` }}
              title={`Unmapped: ${unmappedCount}`}
            />
          </div>
        </Card>
      )}

      {/* Cascade Run Controls */}
      <Card padding="lg" className="cascade-card">
        <CardHeader>
          <div className="cascade-header">
            <CardTitle>
              <div className="flex-align gap-2">
                <Layers size={18} className="text-accent" />
                Run Mapping Cascade
              </div>
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="cascade-controls">
            <div className="form-group">
              <label htmlFor="encoder-select" className="form-label">
                Semantic Encoder
              </label>
              <select
                id="encoder-select"
                className="form-input"
                value={selectedEncoder}
                onChange={(e) => setSelectedEncoder(e.target.value)}
              >
                {(meta?.encoder_kinds ?? ["auto", "none", "tfidf", "sbert"]).map((enc: string) => (
                  <option key={enc} value={enc}>
                    {enc.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>

            {meta?.features?.llm && (
              <div className="form-group checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={useLlm}
                    onChange={(e) => setUseLlm(e.target.checked)}
                  />
                  <span>Enable LLM Reasoning Layer</span>
                </label>
              </div>
            )}

            <Button
              onClick={handleRunCascade}
              loading={runMapping.isPending}
              icon={<Play size={16} />}
              className="cascade-btn"
            >
              Run Cascade
            </Button>
          </div>

          {runResult && (
            <div className="run-result-summary fade-in">
              <div className="run-metrics">
                <Metric
                  label="Resolution Rate"
                  value={pct(runResult.resolution_rate * 100)}
                />
                <Metric label="Lines Mapped" value={num(runResult.resolved)} />
                <Metric label="Heads for Review" value={num(runResult.review)} />
                <Metric label="Encoder Used" value={runResult.encoder.toUpperCase()} />
              </div>
              <div className="run-donut">
                <MappingDonut byLayer={runResult.by_layer} />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Review Queue */}
      <div className="queue-section">
        <div className="queue-tabs">
          <button
            className={`tab-btn ${activeTab === "pending" ? "tab-btn--active" : ""}`}
            onClick={() => setActiveTab("pending")}
          >
            Review Queue ({pendingHeads?.length ?? 0})
          </button>
          <button
            className={`tab-btn ${activeTab === "resolved" ? "tab-btn--active" : ""}`}
            onClick={() => setActiveTab("resolved")}
          >
            Resolved ({resolvedHeads?.length ?? 0})
          </button>
        </div>

        {activeTab === "pending" && (
          <Card padding="none">
            {pendingHeads && pendingHeads.length > 0 && (
              <div className="bulk-bar">
                <div className="bulk-left">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={
                        bulkChecked.size === pendingHeads.length &&
                        pendingHeads.length > 0
                      }
                      onChange={toggleSelectAll}
                    />
                    <span>Select All ({pendingHeads.length})</span>
                  </label>
                  <span className="bulk-count">
                    {bulkChecked.size} selected
                  </span>
                </div>
                <div className="bulk-right">
                  <input
                    type="text"
                    className="reviewer-input"
                    placeholder="Reviewer Name"
                    value={reviewerName}
                    onChange={(e) => setReviewerName(e.target.value)}
                  />
                  <Button
                    size="sm"
                    disabled={bulkChecked.size === 0}
                    loading={bulkResolve.isPending}
                    onClick={handleBulkApprove}
                    icon={<CheckSquare size={16} />}
                  >
                    Approve Selected
                  </Button>
                </div>
              </div>
            )}

            {loadingPending ? (
              <div className="p-4">
                <CardSkeleton />
              </div>
            ) : pendingHeads && pendingHeads.length > 0 ? (
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th style={{ width: 40 }}></th>
                      <th>Ledger Head</th>
                      <th>Group</th>
                      <th>Amount</th>
                      <th>Lines</th>
                      <th>Similarity</th>
                      <th>Assign FSLI</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pendingHeads.map((head) => {
                      const selectedFsli =
                        rowSelections[head.line_id] || head.candidates?.[0] || "";

                      return (
                        <tr key={head.line_id}>
                          <td>
                            <input
                              type="checkbox"
                              checked={bulkChecked.has(head.line_id)}
                              onChange={() => toggleBulkSelect(head.line_id)}
                            />
                          </td>
                          <td>
                            <div className="head-name-cell">
                              <span className="head-name">{head.raw_name}</span>
                              <span className="mono text-xs text-muted">
                                {head.raw_code}
                              </span>
                            </div>
                          </td>
                          <td className="text-secondary text-xs">
                            {head.group_name || "—"}
                          </td>
                          <td className="mono font-semibold">
                            {inr(head.abs_amount ?? head.amount)}
                          </td>
                          <td>
                            <Badge size="sm" variant="outlined" color="var(--text-secondary)">
                              {head.lines} lines
                            </Badge>
                          </td>
                          <td>
                            {head.embed_score != null ? (
                              <span className="mono text-xs">
                                {pct(head.embed_score * 100)}
                                {head.embed_margin != null && (
                                  <span className="text-muted ml-1">
                                    (Δ {pct(head.embed_margin * 100)})
                                  </span>
                                )}
                              </span>
                            ) : (
                              <span className="text-muted">—</span>
                            )}
                          </td>
                          <td>
                            <select
                              className="candidate-select"
                              value={selectedFsli}
                              onChange={(e) =>
                                setRowSelections((prev) => ({
                                  ...prev,
                                  [head.line_id]: e.target.value,
                                }))
                              }
                            >
                              {head.candidates?.map((c) => (
                                <option key={c} value={c}>
                                  ★ {c}
                                </option>
                              ))}
                              {taxonomy && (
                                <optgroup label="All Taxonomy">
                                  {taxonomy.map((t) => (
                                    <option key={t.code} value={t.code}>
                                      {t.code} - {t.name}
                                    </option>
                                  ))}
                                </optgroup>
                              )}
                            </select>
                          </td>
                          <td>
                            <Button
                              size="sm"
                              loading={
                                resolveMapping.isPending &&
                                resolveMapping.variables?.line_id === head.line_id
                              }
                              onClick={() => handleSingleResolve(head)}
                              icon={<CheckCircle size={14} />}
                            >
                              Approve
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                icon={<Sparkles size={40} />}
                title="Review Queue is Clean!"
                description="All ledger heads have been mapped with high confidence or resolved."
              />
            )}
          </Card>
        )}

        {activeTab === "resolved" && (
          <Card padding="none">
            {loadingResolved ? (
              <div className="p-4">
                <CardSkeleton />
              </div>
            ) : resolvedHeads && resolvedHeads.length > 0 ? (
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Ledger Head</th>
                      <th>Group</th>
                      <th>Amount</th>
                      <th>Mapped FSLI</th>
                      <th>Method</th>
                      <th>Reset</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resolvedHeads.map((head) => (
                      <tr key={head.line_id}>
                        <td>
                          <span className="head-name">{head.raw_name}</span>
                        </td>
                        <td className="text-muted text-xs">{head.group_name}</td>
                        <td className="mono">{inr(head.abs_amount ?? head.amount)}</td>
                        <td>
                          <span className="mono text-accent">{head.candidates?.[0]}</span>
                        </td>
                        <td>
                          <Badge size="sm" variant="outlined" color="var(--success)">
                            {head.method || "manual"}
                          </Badge>
                        </td>
                        <td>
                          <Button
                            variant="ghost"
                            size="sm"
                            loading={
                              resetMapping.isPending &&
                              resetMapping.variables === head.line_id
                            }
                            onClick={() => resetMapping.mutate(head.line_id)}
                            icon={<RotateCcw size={14} />}
                          >
                            Reset
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                title="No resolved mappings yet"
                description="Resolve heads in the review queue to see them listed here."
              />
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
