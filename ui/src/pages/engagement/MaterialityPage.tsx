import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Scale,
  Sparkles,
  CheckCircle,
  ArrowRight,
  TrendingUp,
  Landmark,
} from "lucide-react";
import { useMateriality, useSetMateriality } from "../../api/materiality";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/common/Card";
import { Button } from "../../components/common/Button";
import { Badge } from "../../components/common/Badge";
import { Metric } from "../../components/common/Metric";
import { ErrorBanner } from "../../components/common/ErrorBanner";
import { CardSkeleton } from "../../components/common/LoadingSkeleton";
import { ROUTES } from "../../utils/constants";
import { inr, pct, compact } from "../../utils/format";
import "./MaterialityPage.css";

export function MaterialityPage() {
  const { id } = useParams<{ id: string }>();
  const engagementId = Number(id);
  const navigate = useNavigate();

  const { data: matData, isLoading, error } = useMateriality(engagementId);
  const setMateriality = useSetMateriality(engagementId);

  const [valueInput, setValueInput] = useState<string>("");
  const [basisInput, setBasisInput] = useState<string>("");

  useEffect(() => {
    if (matData) {
      if (matData.value != null) {
        setValueInput(String(matData.value));
      }
      if (matData.basis) {
        setBasisInput(matData.basis);
      }
    }
  }, [matData]);

  const handleApplySuggestion = () => {
    if (!matData?.suggestion) return;
    const { suggested, basis } = matData.suggestion;
    setValueInput(String(suggested));
    setBasisInput(basis);
    setMateriality.mutate({
      value: suggested,
      basis,
    });
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    const val = Number(valueInput);
    if (isNaN(val) || val <= 0) return;

    setMateriality.mutate({
      value: val,
      basis: basisInput.trim() || undefined,
    });
  };

  return (
    <div className="materiality-page fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Audit Materiality</h1>
          <p className="page-subtitle">
            Configure overall materiality threshold for variance classification and exception scoping.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => navigate(ROUTES.recon(engagementId))}
          icon={<ArrowRight size={16} />}
        >
          Proceed to Reconciliation
        </Button>
      </div>

      <ErrorBanner error={(error || setMateriality.error) as Error} />

      {isLoading ? (
        <CardSkeleton />
      ) : (
        <div className="materiality-layout">
          {/* Active Status Tile */}
          <Card padding="lg" className="active-mat-card">
            <CardHeader>
              <div className="flex-between">
                <CardTitle>Current Materiality</CardTitle>
                <Badge
                  color={
                    matData?.value != null
                      ? "var(--success)"
                      : "var(--warning)"
                  }
                  pulse={matData?.value == null}
                >
                  {matData?.value != null ? "Set" : "Pending"}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="mat-display">
                <span className="mat-amount mono">
                  {matData?.value != null ? inr(matData.value) : "Not Configured"}
                </span>
                {matData?.value != null && (
                  <span className="mat-compact mono">
                    ({compact(matData.value)})
                  </span>
                )}
                {matData?.basis && (
                  <span className="mat-basis">
                    Benchmark: <strong>{matData.basis}</strong>
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Benchmark Suggestion */}
          {matData?.suggestion && (
            <Card padding="lg" className="suggestion-card">
              <CardHeader>
                <div className="flex-align gap-2">
                  <Sparkles size={18} className="text-accent" />
                  <CardTitle>Suggested Benchmark</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <div className="suggestion-grid">
                  <div className="sug-metric">
                    <TrendingUp size={16} className="text-muted" />
                    <Metric
                      label="Total Revenue"
                      value={inr(matData.suggestion.revenue)}
                    />
                  </div>
                  <div className="sug-metric">
                    <Landmark size={16} className="text-muted" />
                    <Metric
                      label="Total Assets"
                      value={inr(matData.suggestion.total_assets)}
                    />
                  </div>
                  <div className="sug-metric">
                    <Scale size={16} className="text-muted" />
                    <Metric
                      label="Benchmark Ratio"
                      value={pct(matData.suggestion.ratio * 100)}
                      sub={matData.suggestion.basis}
                    />
                  </div>
                  <div className="sug-metric">
                    <Sparkles size={16} className="text-accent" />
                    <Metric
                      label="Recommended"
                      value={inr(matData.suggestion.suggested)}
                      color="var(--accent)"
                    />
                  </div>
                </div>

                <div className="mt-4">
                  <Button
                    variant="secondary"
                    onClick={handleApplySuggestion}
                    loading={setMateriality.isPending}
                    icon={<CheckCircle size={16} />}
                  >
                    Apply Recommended Materiality ({inr(matData.suggestion.suggested)})
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Manual Input Form */}
          <Card padding="lg" className="form-card">
            <CardHeader>
              <CardTitle>Set Materiality Threshold</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSave} className="mat-form">
                <div className="form-group">
                  <label htmlFor="mat-val" className="form-label">
                    Materiality Amount (₹) *
                  </label>
                  <input
                    id="mat-val"
                    type="number"
                    step="any"
                    required
                    placeholder="e.g. 5000000"
                    className="form-input mono"
                    value={valueInput}
                    onChange={(e) => setValueInput(e.target.value)}
                  />
                  {valueInput && !isNaN(Number(valueInput)) && Number(valueInput) > 0 && (
                    <span className="text-xs text-muted mt-1">
                      Formatted: {inr(Number(valueInput))} ({compact(Number(valueInput))})
                    </span>
                  )}
                </div>

                <div className="form-group">
                  <label htmlFor="mat-basis" className="form-label">
                    Basis / Rationale
                  </label>
                  <input
                    id="mat-basis"
                    type="text"
                    placeholder="e.g. 0.5% of Gross Revenue per ISA 320"
                    className="form-input"
                    value={basisInput}
                    onChange={(e) => setBasisInput(e.target.value)}
                  />
                </div>

                <div className="form-actions">
                  <Button
                    type="submit"
                    loading={setMateriality.isPending}
                    icon={<CheckCircle size={16} />}
                  >
                    Save Threshold
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
