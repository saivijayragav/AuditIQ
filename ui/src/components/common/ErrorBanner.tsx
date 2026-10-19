import { AlertTriangle } from "lucide-react";
import { ApiError } from "../../api/client";
import "./ErrorBanner.css";

/** Human-friendly labels for the API's closed error code set. */
const CODE_LABELS: Record<string, string> = {
  bad_request: "Bad Request",
  validation_failed: "Validation Failed",
  not_found: "Not Found",
  materiality_unset: "Materiality Required",
  ingest_failed: "Ingestion Failed",
  schema_drift: "Database Schema Outdated",
  internal_error: "Server Error",
};

interface ErrorBannerProps {
  error: Error | null;
  onDismiss?: () => void;
}

export function ErrorBanner({ error, onDismiss }: ErrorBannerProps) {
  if (!error) return null;

  const isApi = error instanceof ApiError;
  const code = isApi ? error.code : "internal_error";
  const title = CODE_LABELS[code] ?? code;
  const message = error.message;

  return (
    <div className="error-banner fade-in" role="alert">
      <AlertTriangle size={18} className="error-banner__icon" />
      <div className="error-banner__body">
        <strong className="error-banner__title">{title}</strong>
        <p className="error-banner__message">{message}</p>
      </div>
      {onDismiss && (
        <button className="error-banner__dismiss" onClick={onDismiss}>
          ×
        </button>
      )}
    </div>
  );
}
