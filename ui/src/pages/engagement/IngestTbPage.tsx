import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  FileSpreadsheet,
  AlertTriangle,
  ArrowRight,
  Clock,
} from "lucide-react";
import { useIngestTb, useDocuments } from "../../api/ingest";
import { useMeta, useErpSources } from "../../api/reference";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/common/Card";
import { Button } from "../../components/common/Button";
import { Badge } from "../../components/common/Badge";
import { DropZone } from "../../components/common/DropZone";
import { ErrorBanner } from "../../components/common/ErrorBanner";
import { Metric } from "../../components/common/Metric";
import { ROUTES } from "../../utils/constants";
import { inr, num } from "../../utils/format";
import type { TbIngestOut } from "../../api/types";
import "./IngestTbPage.css";

export function IngestTbPage() {
  const { id } = useParams<{ id: string }>();
  const engagementId = Number(id);
  const navigate = useNavigate();

  const { data: meta } = useMeta();
  const { data: erpSources } = useErpSources();
  const { data: documents } = useDocuments(engagementId);
  const ingest = useIngestTb(engagementId);

  const [selectedUnit, setSelectedUnit] = useState<string>("");
  const [selectedSource, setSelectedSource] = useState<string>("");
  const [ingestResult, setIngestResult] = useState<TbIngestOut | null>(null);

  const handleFile = (file: File) => {
    ingest.mutate(
      {
        file,
        unit: selectedUnit || undefined,
        source: selectedSource || undefined,
      },
      {
        onSuccess: (data) => {
          setIngestResult(data);
        },
      }
    );
  };

  const tbDocs = documents?.filter((d) => d.kind === "tb_erp") ?? [];

  return (
    <div className="ingest-tb fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Ingest Trial Balance</h1>
          <p className="page-subtitle">
            Upload client Trial Balance (Excel/CSV) to extract ledgers, balances, and groupings.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => navigate(ROUTES.tbLines(engagementId))}
          icon={<ArrowRight size={16} />}
        >
          View TB Lines
        </Button>
      </div>

      <ErrorBanner error={ingest.error as Error} />

      <div className="ingest-tb__layout">
        <div className="ingest-tb__main">
          <Card padding="lg">
            <CardHeader>
              <CardTitle>Upload File</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="ingest-options">
                <div className="form-group">
                  <label className="form-label" htmlFor="unit-select">
                    Currency Units
                  </label>
                  <select
                    id="unit-select"
                    className="form-input"
                    value={selectedUnit}
                    onChange={(e) => setSelectedUnit(e.target.value)}
                  >
                    <option value="">Auto / Absolute</option>
                    {(meta?.units ?? ["absolute", "lakhs", "crores", "thousands"]).map(
                      (u) => (
                        <option key={u} value={u}>
                          {u}
                        </option>
                      )
                    )}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="source-select">
                    Source ERP Format
                  </label>
                  <select
                    id="source-select"
                    className="form-input"
                    value={selectedSource}
                    onChange={(e) => setSelectedSource(e.target.value)}
                  >
                    <option value="">Auto-Detect Format</option>
                    {erpSources?.sources?.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <DropZone
                accept=".xlsx,.xls,.csv"
                label="Drop Trial Balance (.xlsx, .xls, .csv) here or click to browse"
                onFile={handleFile}
                disabled={ingest.isPending}
              />
            </CardContent>
          </Card>

          {ingestResult && (
            <Card padding="lg" className="fade-in result-card">
              <CardHeader>
                <div className="result-header">
                  <CardTitle>Ingestion Successful</CardTitle>
                  <Badge
                    color={ingestResult.balanced ? "var(--success)" : "var(--danger)"}
                    pulse={!ingestResult.balanced}
                  >
                    {ingestResult.balanced ? "Balanced" : "Out of Balance"}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                {!ingestResult.balanced && (
                  <div className="balance-alert">
                    <AlertTriangle size={18} />
                    <span>
                      Debits and credits do not balance! Variance:{" "}
                      <strong>{inr(ingestResult.balance_difference)}</strong>
                    </span>
                  </div>
                )}

                <div className="result-grid">
                  <Metric label="Detected Source" value={ingestResult.source.toUpperCase()} />
                  <Metric label="Lines Parsed" value={num(ingestResult.lines)} />
                  <Metric label="Total Debit" value={inr(ingestResult.total_debit)} />
                  <Metric label="Total Credit" value={inr(ingestResult.total_credit)} />
                </div>

                <div className="result-actions">
                  <Button
                    onClick={() => navigate(ROUTES.tbLines(engagementId))}
                    icon={<ArrowRight size={16} />}
                  >
                    Review Ingested Lines
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => navigate(ROUTES.mapping(engagementId))}
                  >
                    Proceed to FSLI Mapping
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="ingest-tb__sidebar">
          <Card padding="md">
            <CardHeader>
              <CardTitle>Ingested TB Documents</CardTitle>
            </CardHeader>
            <CardContent>
              {tbDocs.length === 0 ? (
                <p className="no-docs-text">No trial balance uploaded yet.</p>
              ) : (
                <div className="doc-list">
                  {tbDocs.map((doc) => (
                    <div key={doc.document_id} className="doc-item">
                      <FileSpreadsheet size={20} className="doc-icon" />
                      <div className="doc-info">
                        <span className="doc-name">{doc.filename}</span>
                        <span className="doc-time">
                          <Clock size={12} />
                          {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString() : "Uploaded"}
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
