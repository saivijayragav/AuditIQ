import { useParams, useNavigate } from "react-router-dom";
import {
  Upload,
  GitBranch,
  FileText,
  ClipboardCheck,
  Scale,
  GitCompare,
  AlertCircle,
  CheckCircle2,
  Circle,
  Loader2,
} from "lucide-react";
import { useEngagement } from "../../api/engagements";
import { Card } from "../../components/common/Card";
import { Badge } from "../../components/common/Badge";
import { Metric } from "../../components/common/Metric";
import { LoadingSkeleton } from "../../components/common/LoadingSkeleton";
import { ErrorBanner } from "../../components/common/ErrorBanner";
import { compact, num } from "../../utils/format";
import { ROUTES } from "../../utils/constants";
import {
  INTAKE_STATUS_COLORS,
  RECON_STATUS_COLORS,
} from "../../utils/colors";
import "./OverviewPage.css";

interface Step {
  key: string;
  label: string;
  icon: React.ElementType;
  path: (id: string) => string;
  done: (e: NonNullable<ReturnType<typeof useEngagement>["data"]>) => boolean;
  inProgress: (e: NonNullable<ReturnType<typeof useEngagement>["data"]>) => boolean;
}

const STEPS: Step[] = [
  {
    key: "ingest-tb",
    label: "Ingest TB",
    icon: Upload,
    path: ROUTES.ingestTb,
    done: (e) => e.tb_lines > 0,
    inProgress: () => false,
  },
  {
    key: "mapping",
    label: "Map FSLIs",
    icon: GitBranch,
    path: ROUTES.mapping,
    done: (e) => e.resolved_lines > 0 && e.pending_lines === 0,
    inProgress: (e) => e.resolved_lines > 0 && e.pending_lines > 0,
  },
  {
    key: "ingest-fs",
    label: "Ingest FS",
    icon: FileText,
    path: ROUTES.ingestFs,
    done: (e) => e.fs_documents > 0,
    inProgress: () => false,
  },
  {
    key: "fs-review",
    label: "FS Review",
    icon: ClipboardCheck,
    path: ROUTES.fsReview,
    done: (e) => e.fs_documents > 0 && e.fs_unmapped_rows === 0,
    inProgress: (e) => e.fs_unmapped_rows > 0,
  },
  {
    key: "materiality",
    label: "Materiality",
    icon: Scale,
    path: ROUTES.materiality,
    done: (e) => e.materiality_value != null,
    inProgress: () => false,
  },
  {
    key: "recon",
    label: "Reconcile",
    icon: GitCompare,
    path: ROUTES.recon,
    done: (e) => e.recon_run_id != null,
    inProgress: () => false,
  },
  {
    key: "exceptions",
    label: "Exceptions",
    icon: AlertCircle,
    path: ROUTES.exceptions,
    done: (e) => e.recon_run_id != null && e.open_exceptions === 0,
    inProgress: (e) => e.open_exceptions > 0,
  },
];

export function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const engagementId = Number(id);
  const navigate = useNavigate();
  const { data: eng, isLoading, error } = useEngagement(engagementId);

  if (isLoading) return <LoadingSkeleton lines={6} height="24px" />;
  if (error) return <ErrorBanner error={error as Error} />;
  if (!eng) return null;

  return (
    <div className="overview fade-in">
      {/* Header */}
      <div className="overview__header">
        <div>
          <h1 className="overview__title">
            {eng.client_name || eng.client_code}
          </h1>
          <span className="overview__meta mono">
            {eng.client_code} · {eng.period} · {eng.basis}
          </span>
        </div>
        <div className="overview__badges">
          <Badge
            color={INTAKE_STATUS_COLORS[eng.intake_status] ?? "var(--text-secondary)"}
          >
            {eng.intake_status}
          </Badge>
          {eng.recon_status && (
            <Badge
              color={RECON_STATUS_COLORS[eng.recon_status] ?? "var(--text-secondary)"}
              pulse={eng.recon_status === "material differences"}
            >
              {eng.recon_status}
            </Badge>
          )}
        </div>
      </div>

      {/* Workflow Stepper */}
      <div className="overview__stepper">
        {STEPS.map((step, i) => {
          const done = step.done(eng);
          const active = step.inProgress(eng);
          return (
            <button
              key={step.key}
              className={`stepper__step ${done ? "stepper__step--done" : ""} ${active ? "stepper__step--active" : ""}`}
              onClick={() => navigate(step.path(String(eng.engagement_id)))}
            >
              <span className="stepper__icon">
                {done ? (
                  <CheckCircle2 size={20} />
                ) : active ? (
                  <Loader2 size={20} className="stepper__spin" />
                ) : (
                  <Circle size={20} />
                )}
              </span>
              <span className="stepper__label">{step.label}</span>
              {i < STEPS.length - 1 && (
                <span
                  className={`stepper__line ${done ? "stepper__line--done" : ""}`}
                />
              )}
            </button>
          );
        })}
      </div>

      {/* KPI Metrics */}
      <div className="overview__metrics">
        <Card padding="sm">
          <Metric label="TB Lines" value={num(eng.tb_lines)} />
        </Card>
        <Card padding="sm">
          <Metric
            label="Mapped"
            value={num(eng.resolved_lines)}
            sub={`${eng.pending_lines} pending`}
            color={eng.pending_lines > 0 ? "var(--warning)" : undefined}
          />
        </Card>
        <Card padding="sm">
          <Metric label="FS Docs" value={eng.fs_documents} />
        </Card>
        <Card padding="sm">
          <Metric
            label="Materiality"
            value={eng.materiality_value != null ? compact(eng.materiality_value) : "Unset"}
            sub={eng.materiality_basis ?? undefined}
          />
        </Card>
        <Card padding="sm">
          <Metric
            label="Exceptions"
            value={eng.open_exceptions}
            color={eng.open_exceptions > 0 ? "var(--danger)" : undefined}
          />
        </Card>
      </div>

      {/* Quick-action cards */}
      <div className="overview__actions">
        {STEPS.map((step) => {
          const done = step.done(eng);
          const Icon = step.icon;
          return (
            <Card
              key={step.key}
              onClick={() => navigate(step.path(String(eng.engagement_id)))}
              padding="sm"
            >
              <div className="action-card">
                <Icon
                  size={20}
                  style={{ color: done ? "var(--success)" : "var(--text-muted)" }}
                />
                <span className="action-card__label">{step.label}</span>
                {done && (
                  <CheckCircle2
                    size={14}
                    style={{ color: "var(--success)", marginLeft: "auto" }}
                  />
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
