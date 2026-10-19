import { useNavigate } from "react-router-dom";
import { Plus, Briefcase } from "lucide-react";
import { useEngagements } from "../api/engagements";
import { Card } from "../components/common/Card";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { EmptyState } from "../components/common/EmptyState";
import { CardSkeleton } from "../components/common/LoadingSkeleton";
import { ErrorBanner } from "../components/common/ErrorBanner";
import { Metric } from "../components/common/Metric";
import { ROUTES } from "../utils/constants";
import { compact, label } from "../utils/format";
import {
  INTAKE_STATUS_COLORS,
  RECON_STATUS_COLORS,
} from "../utils/colors";
import "./DashboardPage.css";

export function DashboardPage() {
  const navigate = useNavigate();
  const { data: engagements, isLoading, error } = useEngagements();

  return (
    <div className="dashboard fade-in">
      <div className="dashboard__header">
        <div>
          <h1 className="dashboard__title">Engagements</h1>
          <p className="dashboard__subtitle">
            Manage your statutory audit engagements
          </p>
        </div>
        <Button
          icon={<Plus size={18} />}
          onClick={() => navigate(ROUTES.newEngagement)}
        >
          New Engagement
        </Button>
      </div>

      <ErrorBanner error={error as Error} />

      {isLoading && (
        <div className="dashboard__grid">
          {Array.from({ length: 3 }, (_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      )}

      {engagements && engagements.length === 0 && (
        <EmptyState
          icon={<Briefcase size={48} />}
          title="No engagements yet"
          description="Create your first audit engagement to get started with trial balance ingestion, FSLI mapping, and reconciliation."
          action={
            <Button
              icon={<Plus size={18} />}
              onClick={() => navigate(ROUTES.newEngagement)}
            >
              Create Engagement
            </Button>
          }
        />
      )}

      {engagements && engagements.length > 0 && (
        <div className="dashboard__grid">
          {engagements.map((eng) => (
            <Card
              key={eng.engagement_id}
              onClick={() => navigate(ROUTES.engagement(eng.engagement_id))}
              glass
            >
              <div className="eng-card__header">
                <div>
                  <h3 className="eng-card__name">
                    {eng.client_name || eng.client_code}
                  </h3>
                  <span className="eng-card__meta">
                    {eng.client_code} · {eng.period} · {eng.basis}
                  </span>
                </div>
                <Badge
                  color={
                    INTAKE_STATUS_COLORS[eng.intake_status] ??
                    "var(--text-secondary)"
                  }
                >
                  {label(eng.intake_status)}
                </Badge>
              </div>

              <div className="eng-card__metrics">
                <Metric label="TB Lines" value={eng.tb_lines} />
                <Metric label="Mapped" value={eng.resolved_lines} />
                <Metric label="Pending" value={eng.pending_lines} />
                <Metric
                  label="Materiality"
                  value={
                    eng.materiality_value != null
                      ? compact(eng.materiality_value)
                      : "Unset"
                  }
                />
              </div>

              {eng.recon_status && (
                <div className="eng-card__recon">
                  <Badge
                    color={
                      RECON_STATUS_COLORS[eng.recon_status] ??
                      "var(--text-secondary)"
                    }
                    variant={
                      eng.recon_status === "material differences"
                        ? "filled"
                        : "outlined"
                    }
                    pulse={eng.recon_status === "material differences"}
                  >
                    Recon: {label(eng.recon_status)}
                  </Badge>
                  {eng.open_exceptions > 0 && (
                    <Badge color="var(--danger)" variant="outlined">
                      {eng.open_exceptions} exception
                      {eng.open_exceptions > 1 ? "s" : ""}
                    </Badge>
                  )}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
