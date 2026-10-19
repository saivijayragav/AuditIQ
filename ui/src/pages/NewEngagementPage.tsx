import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateEngagement } from "../api/engagements";
import { useMeta } from "../api/reference";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { ErrorBanner } from "../components/common/ErrorBanner";
import { ROUTES } from "../utils/constants";
import "./NewEngagementPage.css";

export function NewEngagementPage() {
  const navigate = useNavigate();
  const { data: meta } = useMeta();
  const create = useCreateEngagement();

  const [clientCode, setClientCode] = useState("");
  const [clientName, setClientName] = useState("");
  const [period, setPeriod] = useState("");
  const [basis, setBasis] = useState("Standalone");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    create.mutate(
      { client_code: clientCode, client_name: clientName, period, basis },
      {
        onSuccess: (eng) =>
          navigate(ROUTES.engagement(eng.engagement_id)),
      }
    );
  };

  return (
    <div className="new-engagement fade-in">
      <h1 className="new-engagement__title">New Engagement</h1>
      <p className="new-engagement__subtitle">
        Set up a new statutory audit engagement
      </p>

      <Card padding="lg" className="new-engagement__card">
        <form onSubmit={handleSubmit} className="new-engagement__form">
          <ErrorBanner error={create.error as Error} />

          <div className="form-group">
            <label className="form-label" htmlFor="client-code">
              Client Code *
            </label>
            <input
              id="client-code"
              className="form-input"
              type="text"
              required
              placeholder="e.g. T00"
              value={clientCode}
              onChange={(e) => setClientCode(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="client-name">
              Client Name
            </label>
            <input
              id="client-name"
              className="form-input"
              type="text"
              placeholder="e.g. Test Company Pvt Ltd"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="period">
              Financial Year *
            </label>
            <input
              id="period"
              className="form-input"
              type="text"
              required
              placeholder="e.g. FY25-26"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="basis">
              Basis
            </label>
            <select
              id="basis"
              className="form-input"
              value={basis}
              onChange={(e) => setBasis(e.target.value)}
            >
              {(meta?.bases ?? ["Standalone", "Consolidated"]).map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
          </div>

          <div className="form-actions">
            <Button
              variant="secondary"
              type="button"
              onClick={() => navigate(ROUTES.dashboard)}
            >
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Create Engagement
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
