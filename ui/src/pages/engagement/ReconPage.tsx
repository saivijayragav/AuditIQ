import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { type Column } from "../../components/common/DataTable";
import {
  GitCompare,
  Play,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  ArrowRight,
  ShieldAlert,
} from "lucide-react";
import {
  useRunRecon,
  useReconLatest,
  useReconExplain,
} from "../../api/reconciliation";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/common/Card";
import { Button } from "../../components/common/Button";
import { Badge } from "../../components/common/Badge";
import { Metric } from "../../components/common/Metric";
import { DataTable } from "../../components/common/DataTable";
import { Dialog } from "../../components/common/Dialog";
import { ErrorBanner } from "../../components/common/ErrorBanner";
import { CardSkeleton } from "../../components/common/LoadingSkeleton";
import { EmptyState } from "../../components/common/EmptyState";
import { ReconBar } from "../../components/charts/ReconBar";
import { inr, pct, label } from "../../utils/format";
import { CLASSIFICATION_COLORS } from "../../utils/colors";
import { ROUTES } from "../../utils/constants";
import type { StoredLineOut } from "../../api/types";
import "./ReconPage.css";

export function ReconPage() {
  const { id } = useParams<{ id: string }>();
  const engagementId = Number(id);
  const navigate = useNavigate();

  const { data: latestData, isLoading: loadingLatest, error: latestError, refetch } =
    useReconLatest(engagementId);
  const runRecon = useRunRecon(engagementId);

  // Recon configuration state
  const [materialityOverride, setMaterialityOverride] = useState<string>("");
  const [pmRatio, setPmRatio] = useState<number>(0.75);
  const [roundingDecimals, setRoundingDecimals] = useState<number>(2);
  const [statements, setStatements] = useState<string>("BS,PL");
  const [dryRun, setDryRun] = useState<boolean>(false);
  const [showConfig, setShowConfig] = useState<boolean>(false);

  // Explain modal state
  const [selectedUnitCode, setSelectedUnitCode] = useState<string | null>(null);
  const { data: explainData, isLoading: loadingExplain } = useReconExplain(
    engagementId,
    selectedUnitCode ?? ""
  );

  const handleRunRecon = () => {
    runRecon.mutate(
      {
        materiality: materialityOverride ? Number(materialityOverride) : null,
        pm: pmRatio,
        rounding_decimals: roundingDecimals,
        statements: statements || null,
        no_persist: dryRun,
      },
      {
        onSuccess: () => {
          refetch();
        },
      }
    );
  };

  const columns: Column<StoredLineOut>[] = [
    {
      key: "unit_code",
      header: "Code",
      cell: (line) => (
        <span className="mono text-xs">{line.unit_code}</span>
      ),
    },
    {
      key: "name",
      header: "Line Item / FSLI",
      cell: (line) => (
        <div className="line-name-cell">
          <span className="line-name">{line.name}</span>
          {line.is_group && (
            <Badge size="sm" variant="outlined" color="var(--info)">
              Group
            </Badge>
          )}
        </div>
      ),
    },
    {
      key: "statement",
      header: "Stmt",
      cell: (line) => (
        <Badge size="sm" variant="muted" color="var(--text-secondary)">
          {line.statement}
        </Badge>
      ),
    },
    {
      key: "side_a",
      header: "Side A (TB)",
      cell: (line) => (
        <span className="mono amount-cell">{inr(line.side_a)}</span>
      ),
    },
    {
      key: "side_b",
      header: "Side B (FS)",
      cell: (line) => (
        <span className="mono amount-cell">{inr(line.side_b)}</span>
      ),
    },
    {
      key: "variance",
      header: "Variance",
      cell: (line) => {
        const val = line.variance;
        const cls = line.classification;
        return (
          <span
            className="mono amount-cell font-bold"
            style={{
              color:
                CLASSIFICATION_COLORS[cls] ??
                (val === 0 ? "var(--success)" : "var(--text-primary)"),
            }}
          >
            {inr(val)}
          </span>
        );
      },
    },
    {
      key: "variance_pct",
      header: "Var %",
      cell: (line) =>
        line.variance_pct != null ? (
          <span className="mono text-xs">{pct(line.variance_pct * 100)}</span>
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      key: "classification",
      header: "Classification",
      cell: (line) => {
        const cls = line.classification;
        return (
          <Badge
            size="sm"
            color={CLASSIFICATION_COLORS[cls] ?? "var(--text-secondary)"}
            pulse={cls === "material"}
          >
            {label(cls)}
          </Badge>
        );
      },
    },
    {
      key: "actions",
      header: "",
      sortable: false,
      cell: (line) => (
        <Button
          size="sm"
          variant="ghost"
          onClick={(e) => {
            e.stopPropagation();
            setSelectedUnitCode(line.unit_code);
          }}
          icon={<ChevronRight size={14} />}
        >
          Explain
        </Button>
      ),
    },
  ];

  const run = latestData?.run;
  const lines = latestData?.lines ?? [];

  return (
    <div className="recon-page fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Trial Balance vs FS Reconciliation</h1>
          <p className="page-subtitle">
            Cross-tie mapped trial balance ledger aggregates (Side A) against published financial statement line items (Side B).
          </p>
        </div>
        <div className="header-actions">
          <Button
            variant="secondary"
            onClick={() => setShowConfig(!showConfig)}
            icon={<Sliders size={16} />}
          >
            {showConfig ? "Hide Config" : "Parameters"}
          </Button>
          <Button
            onClick={handleRunRecon}
            loading={runRecon.isPending}
            icon={<Play size={16} />}
          >
            Run Reconciliation
          </Button>
        </div>
      </div>

      <ErrorBanner error={(latestError || runRecon.error) as Error} />

      {/* Configuration Panel */}
      {showConfig && (
        <Card padding="md" className="recon-config-panel fade-in">
          <CardHeader>
            <CardTitle>Reconciliation Execution Parameters</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="config-grid">
              <div className="form-group">
                <label htmlFor="pm-ratio" className="form-label">
                  Performance Materiality Ratio ({pct(pmRatio * 100)})
                </label>
                <input
                  id="pm-ratio"
                  type="range"
                  min="0.5"
                  max="0.9"
                  step="0.05"
                  value={pmRatio}
                  onChange={(e) => setPmRatio(Number(e.target.value))}
                />
              </div>

              <div className="form-group">
                <label htmlFor="round-dec" className="form-label">
                  Rounding Decimals
                </label>
                <input
                  id="round-dec"
                  type="number"
                  min="0"
                  max="4"
                  className="form-input"
                  value={roundingDecimals}
                  onChange={(e) => setRoundingDecimals(Number(e.target.value))}
                />
              </div>

              <div className="form-group">
                <label htmlFor="mat-override" className="form-label">
                  Materiality Override (₹)
                </label>
                <input
                  id="mat-override"
                  type="number"
                  placeholder="Leave blank to use engagement threshold"
                  className="form-input mono"
                  value={materialityOverride}
                  onChange={(e) => setMaterialityOverride(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="stmts" className="form-label">
                  Statements
                </label>
                <select
                  id="stmts"
                  className="form-input"
                  value={statements}
                  onChange={(e) => setStatements(e.target.value)}
                >
                  <option value="BS,PL">Balance Sheet & P&L</option>
                  <option value="BS">Balance Sheet Only</option>
                  <option value="PL">P&L Only</option>
                </select>
              </div>

              <div className="form-group checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={dryRun}
                    onChange={(e) => setDryRun(e.target.checked)}
                  />
                  <span>Dry Run (do not persist findings / exceptions)</span>
                </label>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Reconciliation Results */}
      {loadingLatest ? (
        <CardSkeleton />
      ) : run ? (
        <div className="recon-results fade-in">
          {/* Status Ribbon */}
          <div
            className={`status-ribbon ${
              run.material > 0
                ? "status-ribbon--danger"
                : run.watch > 0
                ? "status-ribbon--warning"
                : "status-ribbon--success"
            }`}
          >
            <div className="ribbon-left">
              {run.material > 0 ? (
                <ShieldAlert size={24} className="text-danger" />
              ) : run.watch > 0 ? (
                <AlertTriangle size={24} className="text-warning" />
              ) : (
                <CheckCircle2 size={24} className="text-success" />
              )}
              <div>
                <h3 className="ribbon-title">
                  {run.material > 0
                    ? `${run.material} Material Difference${run.material > 1 ? "s" : ""} Identified`
                    : run.watch > 0
                    ? `${run.watch} Watch Item${run.watch > 1 ? "s" : ""} Flagged`
                    : "Clean Tie-Out — Fully Reconciled"}
                </h3>
                <p className="ribbon-sub">
                  Run #{run.run_id} · Materiality: {inr(run.materiality)} · PM:{" "}
                  {inr(run.performance_materiality)}
                </p>
              </div>
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate(ROUTES.exceptions(engagementId))}
              icon={<ArrowRight size={14} />}
            >
              View Exceptions
            </Button>
          </div>

          {/* Metric Tiles */}
          <div className="kpi-grid">
            <Card padding="sm">
              <Metric label="Total Line Items" value={run.units_total} />
            </Card>
            <Card padding="sm">
              <Metric
                label="Tied Exactly"
                value={run.tied}
                color="var(--success)"
              />
            </Card>
            <Card padding="sm">
              <Metric
                label="Rounding"
                value={run.rounding}
                color="var(--info)"
              />
            </Card>
            <Card padding="sm">
              <Metric
                label="Minor Residual"
                value={run.minor}
                color="var(--minor)"
              />
            </Card>
            <Card padding="sm">
              <Metric
                label="Watch Items"
                value={run.watch}
                color="var(--warning)"
              />
            </Card>
            <Card padding="sm">
              <Metric
                label="Material Differences"
                value={run.material}
                color="var(--danger)"
              />
            </Card>
          </div>

          {/* Breakdown Chart */}
          <Card padding="md">
            <CardHeader>
              <CardTitle>Classification Distribution</CardTitle>
            </CardHeader>
            <CardContent>
              <ReconBar
                tied={run.tied}
                rounding={run.rounding}
                minor={run.minor}
                watch={run.watch}
                material={run.material}
              />
            </CardContent>
          </Card>

          {/* Reconciliation Lines Table */}
          <Card padding="none">
            <div className="table-header-bar">
              <span className="font-semibold text-primary">
                Detailed Line-by-Line Tie-Out
              </span>
              <span className="text-xs text-muted">
                Click any row or "Explain" for variance attribution
              </span>
            </div>
            <DataTable
              columns={columns}
              data={lines}
              onRowClick={(row) => setSelectedUnitCode(row.unit_code)}
            />
          </Card>
        </div>
      ) : (
        <EmptyState
          icon={<GitCompare size={48} />}
          title="No Reconciliation Run Yet"
          description="Execute reconciliation to tie out the Trial Balance ledgers against Financial Statement disclosures."
          action={
            <Button
              onClick={handleRunRecon}
              loading={runRecon.isPending}
              icon={<Play size={16} />}
            >
              Run Reconciliation Now
            </Button>
          }
        />
      )}

      {/* Explain Attribution Drilldown Modal */}
      <Dialog
        open={!!selectedUnitCode}
        onClose={() => setSelectedUnitCode(null)}
        title={`Variance Analysis — ${selectedUnitCode}`}
        width="680px"
      >
        {loadingExplain ? (
          <CardSkeleton />
        ) : explainData?.line ? (
          <div className="explain-modal-content">
            <div className="explain-header">
              <div>
                <h3 className="text-lg font-bold text-primary">
                  {explainData.line.name}
                </h3>
                <span className="mono text-xs text-secondary">
                  Statement: {explainData.line.statement} · Unit:{" "}
                  {explainData.line.unit_code}
                </span>
              </div>
              <Badge
                color={
                  CLASSIFICATION_COLORS[explainData.line.classification] ??
                  "var(--text-secondary)"
                }
              >
                {label(explainData.line.classification)}
              </Badge>
            </div>

            <div className="explain-metrics">
              <Metric
                label="Side A (TB)"
                value={inr(explainData.line.side_a)}
                sub={`${explainData.line.a_lines} ledgers`}
              />
              <Metric
                label="Side B (FS)"
                value={inr(explainData.line.side_b)}
                sub={`${explainData.line.b_rows} disclosure rows`}
              />
              <Metric
                label="Variance"
                value={inr(explainData.line.variance)}
                sub={
                  explainData.line.variance_pct != null
                    ? `${pct(explainData.line.variance_pct * 100)} %`
                    : undefined
                }
                color={CLASSIFICATION_COLORS[explainData.line.classification]}
              />
            </div>

            <div className="attribution-section">
              <h4 className="text-sm font-semibold text-primary mb-2">
                Attribution & Contributing Ledgers
              </h4>
              <div className="code-block">
                <pre className="mono text-xs">
                  {JSON.stringify(explainData.line.attribution, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        ) : (
          <p className="text-muted">No details found for this unit.</p>
        )}
      </Dialog>
    </div>
  );
}
