import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  FileText,
  ArrowRight,
  Clock,
  AlertTriangle,
} from "lucide-react";
import { useIngestFs, useDocuments } from "../../api/ingest";
import { useMeta } from "../../api/reference";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/common/Card";
import { Button } from "../../components/common/Button";
import { Badge } from "../../components/common/Badge";
import { DropZone } from "../../components/common/DropZone";
import { ErrorBanner } from "../../components/common/ErrorBanner";
import { Metric } from "../../components/common/Metric";
import { ROUTES } from "../../utils/constants";
import { num } from "../../utils/format";
import { SEVERITY_COLORS } from "../../utils/colors";
import type { FsIngestOut } from "../../api/types";
import "./IngestFsPage.css";

export function IngestFsPage() {
  const { id } = useParams<{ id: string }>();
  const engagementId = Number(id);
  const navigate = useNavigate();

  const { data: meta } = useMeta();
  const { data: documents } = useDocuments(engagementId);
  const ingest = useIngestFs(engagementId);

  const [selectedUnit, setSelectedUnit] = useState<string>("");
  const [ingestResult, setIngestResult] = useState<FsIngestOut | null>(null);

  const handleFile = (file: File) => {
    ingest.mutate(
      {
        file,
        unit: selectedUnit || undefined,
      },
      {
        onSuccess: (data) => {
          setIngestResult(data);
        },
      }
    );
  };

  const fsDocs =
    documents?.filter(
      (d) => d.kind === "fs_draft" || d.kind.startsWith("fs_")
    ) ?? [];

  return (
    <div className="ingest-fs fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Ingest Financial Statements</h1>
          <p className="page-subtitle">
            Upload draft Financial Statements (PDF/Excel) to extract statements, line items, and disclosures.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => navigate(ROUTES.fsReview(engagementId))}
          icon={<ArrowRight size={16} />}
        >
          FS Review Queue
        </Button>
      </div>

      <ErrorBanner error={ingest.error as Error} />

      <div className="ingest-fs__layout">
        <div className="ingest-fs__main">
          <Card padding="lg">
            <CardHeader>
              <CardTitle>Upload Financial Statements</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="ingest-options">
                <div className="form-group">
                  <label className="form-label" htmlFor="fs-unit-select">
                    Currency Unit Override
                  </label>
                  <select
                    id="fs-unit-select"
                    className="form-input"
                    value={selectedUnit}
                    onChange={(e) => setSelectedUnit(e.target.value)}
                  >
                    <option value="">Auto-Detect from Document</option>
                    {(meta?.units ?? ["absolute", "lakhs", "crores", "thousands"]).map(
                      (u) => (
                        <option key={u} value={u}>
                          {u}
                        </option>
                      )
                    )}
                  </select>
                </div>
              </div>

              <DropZone
                accept=".pdf,.xlsx,.xls"
                label="Drop Financial Statements (.pdf, .xlsx) here or click to browse"
                onFile={handleFile}
                disabled={ingest.isPending}
              />
            </CardContent>
          </Card>

          {ingestResult && (
            <Card padding="lg" className="fade-in result-card">
              <CardHeader>
                <div className="result-header">
                  <CardTitle>Extraction Complete</CardTitle>
                  <Badge color="var(--success)">
                    {ingestResult.company || "Parsed Successfully"}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="result-grid">
                  <Metric label="Period" value={ingestResult.period} />
                  <Metric label="Pages" value={ingestResult.pages} />
                  <Metric label="Rows Extracted" value={num(ingestResult.rows)} />
                  <Metric label="Mapped" value={num(ingestResult.mapped)} />
                  <Metric
                    label="Unmapped"
                    value={num(ingestResult.unmapped)}
                    color={ingestResult.unmapped > 0 ? "var(--warning)" : undefined}
                  />
                  <Metric label="Parser Engine" value={ingestResult.reader.toUpperCase()} />
                </div>

                {/* Statement Breakdown */}
                {ingestResult.by_statement && (
                  <div className="statement-breakdown">
                    <span className="breakdown-title">Extracted Statements:</span>
                    <div className="statement-tags">
                      {Object.entries(ingestResult.by_statement).map(
                        ([stmt, count]) => (
                          <Badge
                            key={stmt}
                            variant="outlined"
                            color="var(--accent)"
                          >
                            {stmt.toUpperCase()}: {count} rows
                          </Badge>
                        )
                      )}
                    </div>
                  </div>
                )}

                {/* Validation Issues */}
                {ingestResult.issues && ingestResult.issues.length > 0 && (
                  <div className="issues-box">
                    <div className="issues-title">
                      <AlertTriangle size={16} />
                      Validation Notices ({ingestResult.issues.length})
                    </div>
                    <ul className="issues-list">
                      {ingestResult.issues.map((iss, i) => (
                        <li key={i} className="issue-item">
                          <Badge
                            size="sm"
                            color={SEVERITY_COLORS[iss.severity] ?? "var(--warning)"}
                          >
                            {iss.severity}
                          </Badge>
                          <span className="issue-message">{iss.message}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="result-actions">
                  <Button
                    onClick={() => navigate(ROUTES.fsReview(engagementId))}
                    icon={<ArrowRight size={16} />}
                  >
                    Review Unmapped FS Items ({ingestResult.unmapped})
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => navigate(ROUTES.materiality(engagementId))}
                  >
                    Set Materiality
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="ingest-fs__sidebar">
          <Card padding="md">
            <CardHeader>
              <CardTitle>Uploaded FS Documents</CardTitle>
            </CardHeader>
            <CardContent>
              {fsDocs.length === 0 ? (
                <p className="no-docs-text">No financial statements uploaded yet.</p>
              ) : (
                <div className="doc-list">
                  {fsDocs.map((doc) => (
                    <div key={doc.document_id} className="doc-item">
                      <FileText size={20} className="doc-icon" />
                      <div className="doc-info">
                        <span className="doc-name">{doc.filename}</span>
                        <span className="doc-time">
                          <Clock size={12} />
                          {doc.uploaded_at
                            ? new Date(doc.uploaded_at).toLocaleDateString()
                            : "Uploaded"}
                        </span>
                      </div>
                      <Badge size="sm" variant="outlined" color="var(--accent)">
                        {doc.system}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
