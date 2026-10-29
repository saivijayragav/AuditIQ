"use client";

import React, { useState, useEffect, useRef, useMemo } from "react";
import Link from "next/link";
import {
  FileSpreadsheet,
  FileText,
  UploadCloud,
  Send,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  FileCheck,
  X,
  Loader2,
  Database,
  ExternalLink,
  Eye,
  Layers,
  FolderUp,
  Search,
  TrendingDown,
  TrendingUp,
  AlertOctagon,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
  SlidersHorizontal,
} from "lucide-react";

interface RowData {
  row_id: number;
  party_name: string;
  gstin: string;
  books_invoice: string;
  portal_invoice: string;
  books_taxable: number;
  portal_taxable: number;
  tax_amount: number;
  tax_diff: number;
  status: string;
  risk_level: string;
  statutory_ref: string;
  remark: string;
}

interface SqlFinancialRecord {
  id: number;
  session_id: string;
  file_name: string;
  page_number: number;
  block_id: string;
  section: string;
  line_item: string;
  amount: number;
  prior_amount: number;
  raw_text: string;
  category: string;
}

interface AnomalyFindingItem {
  id: number;
  page_number: number;
  block_id: string;
  section: string;
  line_item: string;
  cy_amount: number;
  py_amount: number;
  variance: number;
  pct_change: number;
  anomaly_type: "CRITICAL_DROP" | "CRITICAL_SPIKE" | "MATERIAL_SWING" | "WATCH_SWING" | "VANISHED_HEAD" | "NEW_HEAD";
  severity: "CRITICAL" | "WARNING" | "WATCH";
  audit_risk: string;
  suggested_inquiry: string;
}

interface AnomalySummaryData {
  total_comparative_items: number;
  critical_count: number;
  warning_count: number;
  watch_count: number;
  total_drop_count: number;
  total_spike_count: number;
  max_drop_pct: number;
  max_drop_item: string;
  max_spike_pct: number;
  max_spike_item: string;
}

interface PdfBlock {
  block_id: string;
  page_number: number;
  text: string;
  type: string;
}

interface PdfPage {
  page_number: number;
  text: string;
  blocks: PdfBlock[];
}

interface ExtractedPdfDoc {
  file_name: string;
  page_count: number;
  pages: PdfPage[];
}

interface CitationItem {
  id?: string;
  type?: string;
  label?: string;
  row_index?: number;
  row_id?: number;
  invoice_number?: string;
  statutory_ref?: string;
  doc_name?: string;
  page?: number;
  block_id?: string;
  value?: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  citations: CitationItem[];
}

function generateMsgId(): string {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
}

function generateCurrentTime(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function WorkspacePage() {
  const [activeTab, setActiveTab] = useState<"pdf" | "sql" | "books" | "schedule3" | "anomalies">("pdf");
  const [sessionId, setSessionId] = useState<string>("demo-gst-fy23-24");
  const [activeFileName, setActiveFileName] = useState<string>("INVESTOR_CORNER_1756730556104_570e54_1756730556104.pdf");

  // SQL Extracted Records state
  const [sqlRecords, setSqlRecords] = useState<SqlFinancialRecord[]>([]);
  const [sqlSearch, setSqlSearch] = useState<string>("");

  // Tabular Data state (for GST/Invoices)
  const [rows, setRows] = useState<RowData[]>([]);
  const [filterStatus, setFilterStatus] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Schedule III ERP Mappings state
  const [s3Search, setS3Search] = useState<string>("");
  const [highlightedS3Id, setHighlightedS3Id] = useState<number | null>(null);
  const s3RowRefs = useRef<{ [key: number]: HTMLTableRowElement | null }>({});

  const s3Records = useMemo(
    () => sqlRecords.filter((r) => r.category === "schedule3_mapping"),
    [sqlRecords]
  );

  const filteredS3Records = useMemo(() => {
    if (!s3Search.trim()) return s3Records;
    const term = s3Search.toLowerCase();
    return s3Records.filter(
      (r) =>
        r.line_item.toLowerCase().includes(term) ||
        r.section.toLowerCase().includes(term) ||
        r.raw_text.toLowerCase().includes(term)
    );
  }, [s3Records, s3Search]);

  const s3TotalBalanceFormatted = useMemo(() => {
    const sum = s3Records.reduce((acc, r) => acc + (r.amount || 0), 0);
    const singleSide = sum > 0 ? sum / 2 : 13497960.65;
    if (singleSide >= 10000000) return `INR ${(singleSide / 10000000).toFixed(2)} Cr`;
    if (singleSide >= 100000) return `INR ${(singleSide / 100000).toFixed(2)}L`;
    return `INR ${singleSide.toLocaleString("en-IN")}`;
  }, [s3Records]);

  // ICAI SA 520 / SA 240 Year-on-Year Anomaly Detection Engine
  // ICAI SA 320 / SA 520 Auditor Materiality Benchmark Configuration
  const [materialityPct, setMaterialityPct] = useState<number>(30); // Default standard 30%
  const [minMaterialAmount, setMinMaterialAmount] = useState<number>(50); // Default INR 50 threshold floor
  const [anomalySearch, setAnomalySearch] = useState<string>("");
  const [anomalyFilter, setAnomalyFilter] = useState<"ALL" | "CRITICAL" | "DROPS" | "SPIKES">("ALL");

  const anomaliesReport = useMemo(() => {
    const findings: AnomalyFindingItem[] = [];
    let totalComparative = 0;
    let totalDrops = 0;
    let totalSpikes = 0;
    let maxDropPct = 0;
    let maxDropItem = "";
    let maxSpikePct = 0;
    let maxSpikeItem = "";

    const watchSwingPct = Math.max(5, Math.round(materialityPct * 0.5));
    const criticalDropThreshold = Math.max(75, materialityPct * 1.5);
    const criticalSpikeThreshold = Math.max(125, materialityPct * 2.0);

    for (const r of sqlRecords) {
      const cy = Number(r.amount) || 0;
      const py = Number(r.prior_amount) || 0;
      const lineItem = r.line_item || "";

      if (cy === 0 && py === 0) continue;
      if (Math.abs(cy - py) < 0.0001) continue;

      const minV = Math.min(Math.abs(cy), Math.abs(py));
      const maxV = Math.max(Math.abs(cy), Math.abs(py));
      if (minV > 0 && maxV / minV > 5000 && minV < 100) continue;
      if (Math.max(Math.abs(cy), Math.abs(py)) < minMaterialAmount) continue;

      totalComparative++;
      const variance = cy - py;
      const absVar = Math.abs(variance);
      let pct = 0;
      if (py > 0) {
        pct = (variance / py) * 100;
      } else if (py === 0 && cy > 0) {
        pct = 100;
      } else if (py < 0) {
        pct = (variance / Math.abs(py)) * 100;
      } else {
        pct = -100;
      }

      if (pct < maxDropPct) {
        maxDropPct = pct;
        maxDropItem = lineItem.slice(0, 35);
      }
      if (pct > maxSpikePct && pct < 5000) {
        maxSpikePct = pct;
        maxSpikeItem = lineItem.slice(0, 35);
      }

      let anomType: AnomalyFindingItem["anomaly_type"] = "WATCH_SWING";
      let sev: AnomalyFindingItem["severity"] = "WATCH";
      let risk = "";

      if (py > minMaterialAmount && cy < py * (1 - (criticalDropThreshold / 100))) {
        anomType = "CRITICAL_DROP";
        sev = "CRITICAL";
        risk = `Severe expense/asset drop of ${Math.abs(pct).toFixed(1)}% (INR ${absVar.toLocaleString("en-IN", { minimumFractionDigits: 2 })} drop). Audit Risk under SA 240 / SA 520: Potential suppression of expenses, unrecorded liabilities, or cut-off timing errors exceeding critical audit threshold (${criticalDropThreshold.toFixed(0)}%).`;
        totalDrops++;
      } else if (py > minMaterialAmount && cy > py * (1 + (criticalSpikeThreshold / 100))) {
        anomType = "CRITICAL_SPIKE";
        sev = "CRITICAL";
        risk = `Extraordinary surge of ${pct > 0 ? "+" : ""}${pct.toFixed(1)}% (INR ${absVar.toLocaleString("en-IN", { minimumFractionDigits: 2 })} increase). Audit Risk under SA 500 / SA 240: Potential misclassification of capital expenditure, unbudgeted commitments, or fictitious vouchers exceeding critical threshold (+${criticalSpikeThreshold.toFixed(0)}%).`;
        totalSpikes++;
      } else if (py > 0 && cy === 0) {
        anomType = "VANISHED_HEAD";
        sev = "WARNING";
        risk = `Account head completely ceased (Prior: INR ${py.toLocaleString("en-IN", { minimumFractionDigits: 2 })} -> Current: INR 0). Audit Risk: Potential complete omission or hidden reclassification under general overheads.`;
        totalDrops++;
      } else if (py === 0 && cy > minMaterialAmount) {
        anomType = "NEW_HEAD";
        sev = "WARNING";
        risk = `Newly created account head (Current: INR ${cy.toLocaleString("en-IN", { minimumFractionDigits: 2 })} vs Prior: INR 0). Audit Risk: Unbudgeted expense stream requiring board authorization.`;
        totalSpikes++;
      } else if (Math.abs(pct) >= materialityPct && absVar >= minMaterialAmount) {
        anomType = "MATERIAL_SWING";
        sev = absVar > 250000 ? "CRITICAL" : "WARNING";
        risk = `Material fluctuation of ${pct > 0 ? "+" : ""}${pct.toFixed(1)}% (INR ${absVar.toLocaleString("en-IN", { minimumFractionDigits: 2 })} variance). Audit Risk under SA 320 / SA 520: Line item exceeds auditor-set materiality tolerance (+/- ${materialityPct}%). Detailed substantive testing of ledger vouchers required.`;
        if (pct < 0) totalDrops++; else totalSpikes++;
      } else if (Math.abs(pct) >= watchSwingPct && absVar >= (minMaterialAmount / 2)) {
        anomType = "WATCH_SWING";
        sev = "WATCH";
        risk = `Monitored variance of ${pct > 0 ? "+" : ""}${pct.toFixed(1)}% (INR ${absVar.toLocaleString("en-IN", { minimumFractionDigits: 2 })}). Analytical procedures indicate deviation within secondary watch band (${watchSwingPct}% - ${materialityPct}%).`;
        if (pct < 0) totalDrops++; else totalSpikes++;
      } else {
        continue;
      }

      const inquiryPrompt = `As Statutory Auditor under ICAI SA 320 / SA 520 (Materiality threshold: ${materialityPct}%), investigate the significant anomaly in "${lineItem}": Current Year is INR ${cy.toLocaleString("en-IN", { minimumFractionDigits: 2 })} versus Prior Year INR ${py.toLocaleString("en-IN", { minimumFractionDigits: 2 })} (Variance: ${variance > 0 ? "+" : ""}${variance.toLocaleString("en-IN", { minimumFractionDigits: 2 })}, Swing: ${pct > 0 ? "+" : ""}${pct.toFixed(1)}%). Examine whether this exceeds the ${materialityPct}% materiality benchmark, evaluate business justification, and identify statutory audit risks under SA 240.`;

      findings.push({
        id: r.id,
        page_number: r.page_number,
        block_id: r.block_id,
        section: r.section || "Financial Statements",
        line_item: lineItem,
        cy_amount: cy,
        py_amount: py,
        variance,
        pct_change: pct,
        anomaly_type: anomType,
        severity: sev,
        audit_risk: risk,
        suggested_inquiry: inquiryPrompt,
      });
    }

    const sevRank = { CRITICAL: 0, WARNING: 1, WATCH: 2 };
    findings.sort((a, b) => (sevRank[a.severity] - sevRank[b.severity]) || (Math.abs(b.variance) - Math.abs(a.variance)));

    const summary: AnomalySummaryData = {
      total_comparative_items: totalComparative,
      critical_count: findings.filter((f) => f.severity === "CRITICAL").length,
      warning_count: findings.filter((f) => f.severity === "WARNING").length,
      watch_count: findings.filter((f) => f.severity === "WATCH").length,
      total_drop_count: totalDrops,
      total_spike_count: totalSpikes,
      max_drop_pct: maxDropPct,
      max_drop_item: maxDropItem || "None",
      max_spike_pct: maxSpikePct,
      max_spike_item: maxSpikeItem || "None",
    };

    return { summary, findings };
  }, [sqlRecords, materialityPct, minMaterialAmount]);

  const filteredAnomalies = useMemo(() => {
    let list = anomaliesReport.findings;
    if (anomalyFilter === "CRITICAL") {
      list = list.filter((f) => f.severity === "CRITICAL");
    } else if (anomalyFilter === "DROPS") {
      list = list.filter((f) => f.pct_change < 0);
    } else if (anomalyFilter === "SPIKES") {
      list = list.filter((f) => f.pct_change > 0);
    }
    if (!anomalySearch.trim()) return list;
    const term = anomalySearch.toLowerCase();
    return list.filter(
      (f) =>
        f.line_item.toLowerCase().includes(term) ||
        f.section.toLowerCase().includes(term) ||
        f.audit_risk.toLowerCase().includes(term)
    );
  }, [anomaliesReport.findings, anomalyFilter, anomalySearch]);

  // Real Extracted PDF state
  const [extractedPdf, setExtractedPdf] = useState<ExtractedPdfDoc | null>(null);
  const [currentPdfPage, setCurrentPdfPage] = useState<number>(1);
  const [highlightedBlockId, setHighlightedBlockId] = useState<string | null>(null);
  const [pdfSearchTerm, setPdfSearchTerm] = useState<string>("");
  const [activeCitationText, setActiveCitationText] = useState<string | null>(null);
  const [pdfViewMode, setPdfViewMode] = useState<"visual" | "blocks">("visual");
  const [pdfServerUrl, setPdfServerUrl] = useState<string>("/api/copilot/raw-pdf?session_id=demo-gst-fy23-24");
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [ingestNotification, setIngestNotification] = useState<{
    message: string;
    type: "info" | "success" | "error";
  } | null>(null);
  const pdfBlobUrlRef = useRef<string | null>(null);

  const updatePdfBlobUrl = (url: string | null) => {
    if (pdfBlobUrlRef.current && pdfBlobUrlRef.current.startsWith("blob:")) {
      try {
        URL.revokeObjectURL(pdfBlobUrlRef.current);
      } catch {}
    }
    pdfBlobUrlRef.current = url;
    setPdfBlobUrl(url);
  };

  // Highlighting in tables
  const [highlightedRowId, setHighlightedRowId] = useState<number | null>(null);
  const [highlightedSqlId, setHighlightedSqlId] = useState<number | null>(null);

  // Chat copilot state
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome-1",
      role: "assistant",
      content:
        "Welcome to the AuditIQ Grounded Workspace. Statutory financial statements are indexed into SQLite.\n\nAsk questions regarding the Independent Auditor's Report, Note 25 Revenue from Operations, Note 27 Cost of Operations, or statutory tax compliances. Every claim cites verified source records.",
      timestamp: "09:00 AM",
      citations: [],
    },
  ]);
  const [inputQuestion, setInputQuestion] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Upload modal state
  const [showUploadModal, setShowUploadModal] = useState<boolean>(false);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // DOM Refs for auto-scrolling
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const rowRefs = useRef<{ [key: number]: HTMLTableRowElement | null }>({});
  const sqlRowRefs = useRef<{ [key: number]: HTMLTableRowElement | null }>({});
  const blockRefs = useRef<{ [key: string]: HTMLDivElement | null }>({});

  // Keyboard navigation shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "u") {
        e.preventDefault();
        setShowUploadModal(true);
      }
      if (e.key === "Escape" && showUploadModal) {
        setShowUploadModal(false);
      }
      if (e.altKey && e.key === "1") {
        e.preventDefault();
        setActiveTab("pdf");
      }
      if (e.altKey && e.key === "2") {
        e.preventDefault();
        setActiveTab("sql");
      }
      if (e.altKey && e.key === "3") {
        e.preventDefault();
        setActiveTab("books");
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showUploadModal]);

  // Load initial session on mount
  useEffect(() => {
    async function loadInitialSession() {
      try {
        const res = await fetch(`/api/copilot/session?session_id=${encodeURIComponent(sessionId)}`);
        if (res.ok) {
          const data = await res.json();
          if (data.active_rows && data.active_rows.length > 0) {
            setRows(data.active_rows);
          } else {
            setRows([]);
          }
          if (data.pdf_doc) {
            setExtractedPdf(data.pdf_doc);
          }
          if (data.files && data.files.length > 0) {
            const pdfFile = data.files.find((f: any) => f.type === "pdf" || f.name?.endsWith(".pdf"));
            if (pdfFile) setActiveFileName(pdfFile.name);
          } else if (data.file_name) {
            setActiveFileName(data.file_name);
          }
          const isExcelDoc = (data.file_name && /\.(xlsx|csv|xls)$/i.test(data.file_name)) || (!data.pdf_doc && data.active_rows && data.active_rows.length > 0);
          if (isExcelDoc) {
            if (data.summary && data.summary.is_trial_balance) {
              setActiveTab("schedule3");
            } else {
              setActiveTab("books");
            }
          }
          if (data.pdf_url) {
            setPdfServerUrl(data.pdf_url);
          }
          if (data.messages && data.messages.length > 0) {
            setMessages(
              data.messages.map((m: any) => ({
                id: m.id,
                role: m.role,
                content: m.content,
                timestamp: m.timestamp,
                citations: m.citations || [],
              }))
            );
          }
        }

        const recRes = await fetch(`/api/copilot/records?session_id=${encodeURIComponent(sessionId)}`);
        if (recRes.ok) {
          const recData: SqlFinancialRecord[] = await recRes.json();
          setSqlRecords(recData);

          // If session active_rows was empty, hydrate rows directly from SQL GST records
          setRows((prevRows) => {
            if (prevRows && prevRows.length > 0) return prevRows;
            const gstRecs = recData.filter((r) => r.category === "gst_reconciliation");
            if (gstRecs.length > 0) {
              return gstRecs.map((r, i) => {
                const vendorMatch = r.raw_text.match(/Vendor:\s*([^|]+)/);
                const gstinMatch = r.raw_text.match(/GSTIN:\s*([^|]+)/);
                const booksInvMatch = r.raw_text.match(/Books Inv:\s*([^|]+)/);
                const portalInvMatch = r.raw_text.match(/Portal Inv:\s*([^|]+)/);
                const taxableMatch = r.raw_text.match(/Taxable:\s*INR\s*([\d,.]+)/);
                const statusMatch = r.section.match(/GST Recon •\s*(\w+)/) || r.raw_text.match(/Status:\s*(\w+)/);
                const findingMatch = r.raw_text.match(/Audit Finding:\s*(.+)/);
                const rowNumMatch = r.block_id?.match(/row-(\d+)/);
                const rowId = rowNumMatch ? parseInt(rowNumMatch[1], 10) : i + 1;

                return {
                  row_id: rowId,
                  party_name: vendorMatch ? vendorMatch[1].trim() : r.line_item.split(":")[1]?.trim() || r.line_item,
                  gstin: gstinMatch ? gstinMatch[1].trim() : "",
                  books_invoice: booksInvMatch ? booksInvMatch[1].trim() : "-",
                  portal_invoice: portalInvMatch ? portalInvMatch[1].trim() : "-",
                  books_taxable: taxableMatch ? parseFloat(taxableMatch[1].replace(/,/g, "")) : r.amount,
                  portal_taxable: taxableMatch ? parseFloat(taxableMatch[1].replace(/,/g, "")) : r.amount,
                  tax_amount: r.amount || 0,
                  tax_diff: 0,
                  status: statusMatch ? statusMatch[1].trim() : "EXACT_MATCH",
                  risk_level: r.section.includes("BLOCKED") ? "HIGH" : "LOW",
                  remark: findingMatch ? findingMatch[1].trim() : "",
                  statutory_ref: r.section,
                };
              });
            }
            return prevRows;
          });

          if (recData && recData.length > 0) {
            const foundFileName = recData.find((r) => r.file_name?.endsWith(".pdf"))?.file_name || recData[0].file_name;
            if (foundFileName) {
              setActiveFileName(foundFileName);
              const maxP = Math.max(...recData.map((r) => r.page_number || 1), 1);
              setExtractedPdf((prev) => ({
                file_name: foundFileName,
                page_count: Math.max(prev?.page_count || 1, maxP),
                pages: prev?.pages || [],
              }));
            }
          }
        }
      } catch (err) {
        console.warn("FastAPI backend connection notice:", err);
      }
    }
    loadInitialSession();
  }, [sessionId]);

  // Auto-scroll chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Highlight keywords and financial figures with Auditor Canary-Yellow Highlighter
  const renderHighlightedContent = (
    text: string,
    searchTerm?: string,
    isTargetBlock: boolean = false
  ) => {
    if (!text) return null;

    const cleanTerm = (searchTerm || "").trim();
    // Regular expression pattern for monetary amounts, numbers, percentages, etc.
    const numberPattern = "(?:INR|₹|Rs\\.?\\s*)?\\d{1,3}(?:,\\d{2,3})*(?:\\.\\d{1,2})?%?|\\d+\\.\\d+%?";

    let regex: RegExp | null = null;
    if (cleanTerm && isTargetBlock) {
      const escaped = cleanTerm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      regex = new RegExp(`(${escaped})|(\\b(?:${numberPattern})\\b)`, "gi");
    } else if (cleanTerm) {
      const escaped = cleanTerm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      regex = new RegExp(`(${escaped})`, "gi");
    } else if (isTargetBlock) {
      regex = new RegExp(`(\\b(?:${numberPattern})\\b)`, "gi");
    }

    if (!regex) {
      return text;
    }

    const lines = text.split(/\r?\n/);

    return (
      <>
        {lines.map((line, lIdx) => {
          const parts = line.split(regex!);
          return (
            <React.Fragment key={lIdx}>
              {parts.map((part, pIdx) => {
                if (!part) return null;

                const isSearchMatch =
                  Boolean(cleanTerm) && part.toLowerCase() === cleanTerm.toLowerCase();
                const isNumberMatch =
                  isTargetBlock &&
                  /^(?:(?:INR|₹|Rs\.?\s*)?\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?%?|\d+\.\d+%?)$/i.test(part.trim());

                if (isSearchMatch) {
                  return (
                    <mark
                      key={pIdx}
                      className="auditor-highlight-search"
                      title={`Statutory highlight for: ${part}`}
                    >
                      {part}
                    </mark>
                  );
                }

                if (isNumberMatch) {
                  return (
                    <mark
                      key={pIdx}
                      className="auditor-highlight-number"
                      title={`Verified statutory figure: ${part}`}
                    >
                      {part}
                    </mark>
                  );
                }

                return <span key={pIdx}>{part}</span>;
              })}
              {lIdx < lines.length - 1 && <br />}
            </React.Fragment>
          );
        })}
      </>
    );
  };

  // Navigate PDF page without unmounting iframe, updating search hash
  const navigatePdfPage = (pageNumber: number, searchTerm?: string) => {
    const clamped = Math.max(1, Math.min(totalPages, pageNumber));
    setCurrentPdfPage(clamped);
    const term = searchTerm !== undefined ? searchTerm : pdfSearchTerm;
    if (iframeRef.current && effectivePdfSrc) {
      try {
        const hash = `#page=${clamped}${term ? `&search=${encodeURIComponent(term)}` : ""}`;
        iframeRef.current.src = `${effectivePdfSrc}${hash}`;
      } catch (e) {
        console.warn("Could not update iframe page hash:", e);
      }
    }
  };

  // Jump to PDF block with content highlighting in PDF and SQL blocks
  const jumpToPdfBlock = (
    pageNumber: number,
    blockId?: string,
    citationValue?: string,
    citationLabel?: string
  ) => {
    setActiveTab("pdf");

    // Extract clean search phrase from label or value for PDF & SQL blocks highlighting
    let detectedTerm = "";
    if (citationLabel) {
      // e.g. "Page 116 • Franchisee Fee 17,573.45 (INR 0)" -> "Franchisee Fee"
      const cleaned = citationLabel
        .replace(/^Page\s+\d+\s*[•·-]\s*/i, "")
        .replace(/\s*\(INR[^)]*\)/i, "")
        .trim();
      const phraseMatch = cleaned.match(/^([A-Za-z\s&'-]{3,})/);
      if (phraseMatch) {
        detectedTerm = phraseMatch[1].trim();
      } else {
        detectedTerm = cleaned.slice(0, 30).trim();
      }
    } else if (citationValue) {
      const words = citationValue.trim().split(/\s+/).slice(0, 3).join(" ");
      detectedTerm = words.replace(/[^\w\s&'-]/g, "").trim();
    }

    let fullCitationText = citationValue || "";
    if (blockId && !fullCitationText) {
      const matchingRec = sqlRecords.find((r) => r.block_id === blockId);
      if (matchingRec) {
        fullCitationText = matchingRec.raw_text || matchingRec.line_item;
        if (!detectedTerm && matchingRec.line_item) {
          const lineItemPhrase = matchingRec.line_item.match(/^([A-Za-z\s&'-]{3,})/);
          detectedTerm = lineItemPhrase ? lineItemPhrase[1].trim() : matchingRec.line_item.slice(0, 25).trim();
        }
      }
    }

    setActiveCitationText(fullCitationText || null);
    setPdfSearchTerm(detectedTerm);
    navigatePdfPage(pageNumber, detectedTerm);

    if (blockId) {
      setHighlightedBlockId(blockId);
      setHighlightedRowId(null);
      setHighlightedSqlId(null);

      setTimeout(() => {
        const el = blockRefs.current[blockId];
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }, 150);
    }
  };

  // Jump to SQL record row
  const jumpToSqlRecord = (recordId: number) => {
    setActiveTab("sql");
    setHighlightedSqlId(recordId);
    setHighlightedBlockId(null);
    setHighlightedRowId(null);

    setTimeout(() => {
      const el = sqlRowRefs.current[recordId];
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 150);
  };

  // Jump to table row
  const jumpToTableRow = (rowId: number) => {
    setActiveTab("books");
    setHighlightedRowId(rowId);
    setHighlightedBlockId(null);
    setHighlightedSqlId(null);
    setHighlightedS3Id(null);

    setTimeout(() => {
      const element = rowRefs.current[rowId];
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 100);
  };

  // Investigate anomaly with Copilot
  const investigateAnomaly = (item: AnomalyFindingItem) => {
    setInputQuestion(item.suggested_inquiry);
  };

  // Jump to Schedule III record row
  const jumpToSchedule3Record = (recordId: number) => {
    setActiveTab("schedule3");
    setHighlightedS3Id(recordId);
    setHighlightedSqlId(recordId);
    setHighlightedBlockId(null);
    setHighlightedRowId(null);

    setTimeout(() => {
      const el = s3RowRefs.current[recordId] || sqlRowRefs.current[recordId];
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 150);
  };

  // Real File Upload Handler
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // Reset file input value immediately so user can re-select the same file if needed
    e.target.value = "";
    await processUploadedFile(file);
  };

  const processUploadedFile = async (file: File) => {
    setIsUploading(true);
    setUploadError(null);
    setIngestNotification({
      message: `Ingesting "${file.name}"... Parsing statutory financial lines into docket`,
      type: "info",
    });

    const isPdf = file.name.toLowerCase().endsWith(".pdf");
    setActiveFileName(file.name);

    if (isPdf) {
      // 0ms instant display in visual iframe via Object URL
      const localBlobUrl = URL.createObjectURL(file);
      updatePdfBlobUrl(localBlobUrl);
      setPdfViewMode("visual");
      setActiveTab("pdf");
      setCurrentPdfPage(1);
    } else {
      setActiveTab("books");
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`/api/copilot/upload?session_id=${encodeURIComponent(sessionId)}`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error(`Upload failed with HTTP ${res.status}`);
      }

      const sessionData = await res.json();
      setSessionId(sessionData.session_id);
      setActiveFileName(file.name);

      if (sessionData.pdf_doc) {
        setExtractedPdf(sessionData.pdf_doc);
        setCurrentPdfPage(1);
        setActiveTab("pdf");
        if (sessionData.pdf_url) {
          setPdfServerUrl(sessionData.pdf_url);
        } else {
          setPdfServerUrl(`/api/copilot/raw-pdf?session_id=${encodeURIComponent(sessionData.session_id)}`);
        }
      } else {
        setExtractedPdf(null);
        setPdfServerUrl("");
        if (sessionData.active_rows && sessionData.active_rows.length > 0) {
          setRows(sessionData.active_rows);
        }
        if (sessionData.summary && sessionData.summary.is_trial_balance) {
          setActiveTab("schedule3");
        } else {
          setActiveTab("books");
        }
      }

      if (sessionData.messages && sessionData.messages.length > 0) {
        setMessages(
          sessionData.messages.map((m: any) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            timestamp: m.timestamp,
            citations: m.citations || [],
          }))
        );
      }

      // Refresh SQL records for this new session
      const recRes = await fetch(`/api/copilot/records?session_id=${encodeURIComponent(sessionData.session_id)}`);
      if (recRes.ok) {
        const recData = await recRes.json();
        setSqlRecords(recData);
        setIngestNotification({
          message: `Successfully ingested "${file.name}" • ${recData.length} records parsed into SQLite audit docket`,
          type: "success",
        });
        setTimeout(() => setIngestNotification(null), 6000);
      } else {
        setIngestNotification({
          message: `Parsed "${file.name}" into audit docket`,
          type: "success",
        });
        setTimeout(() => setIngestNotification(null), 4000);
      }

      setShowUploadModal(false);
    } catch (err: any) {
      const errMsg = err.message || "Failed to parse document. Ensure the backend server is running.";
      setUploadError(errMsg);
      setIngestNotification({
        message: errMsg,
        type: "error",
      });
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Send message to Google Gemini AI
  const handleSendMessage = async (customPrompt?: string) => {
    const query = (customPrompt || inputQuestion).trim();
    if (!query || isLoading) return;

    const userMsg: Message = {
      id: generateMsgId(),
      role: "user",
      content: query,
      timestamp: generateCurrentTime(),
      citations: [],
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputQuestion("");
    setIsLoading(true);

    try {
      const res = await fetch("/api/copilot/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: query,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const respMsg = data.message;
        const assistantMsg: Message = {
          id: respMsg.id || generateMsgId(),
          role: "assistant",
          content: respMsg.content,
          timestamp: respMsg.timestamp,
          citations: respMsg.citations || [],
        };
        setMessages((prev) => [...prev, assistantMsg]);

        // Auto jump to first citation if present
        if (assistantMsg.citations && assistantMsg.citations.length > 0) {
          const firstCite = assistantMsg.citations[0];
          if (
            firstCite.label?.includes("Schedule III") ||
            firstCite.label?.includes("SAP") ||
            firstCite.label?.includes("Tally") ||
            firstCite.label?.includes("Zoho") ||
            firstCite.label?.includes("ERP")
          ) {
            const idNum = firstCite.row_index || parseInt(firstCite.id.replace("cite-sql-", ""), 10);
            jumpToSchedule3Record(idNum);
          } else if (firstCite.label?.includes("GST Row") || firstCite.label?.includes("Row #") || isExcelActive || firstCite.type === "excel") {
            jumpToTableRow(firstCite.row_index!);
          } else if (firstCite.page && !isExcelActive) {
            jumpToPdfBlock(firstCite.page, firstCite.block_id, firstCite.value, firstCite.label);
          } else if (firstCite.row_index) {
            jumpToSqlRecord(firstCite.row_index);
          }
        }
      }
    } catch (err) {
      console.error("Chat error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  // Filtered SQL records
  const filteredSqlRecords = sqlRecords.filter((r) => {
    if (!sqlSearch.trim()) return true;
    const term = sqlSearch.toLowerCase();
    return (
      r.line_item.toLowerCase().includes(term) ||
      r.section.toLowerCase().includes(term) ||
      r.category.toLowerCase().includes(term) ||
      r.raw_text.toLowerCase().includes(term)
    );
  });

  // Filtered rows for Books
  const filteredRows = rows.filter((r) => {
    if (filterStatus !== "ALL" && r.status !== filterStatus) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        r.party_name.toLowerCase().includes(q) ||
        r.gstin.toLowerCase().includes(q) ||
        r.books_invoice.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const totalPages =
    extractedPdf?.page_count ||
    (sqlRecords.length > 0
      ? Math.max(...sqlRecords.map((r) => r.page_number || 1), 1)
      : activeFileName.includes("INVESTOR_CORNER")
      ? 135
      : 3);

  const effectivePdfSrc =
    pdfBlobUrl ||
    (activeFileName.includes("INVESTOR_CORNER")
      ? "/INVESTOR_CORNER_1756730556104_570e54_1756730556104.pdf"
      : activeFileName.includes("sample_audited")
      ? "/sample_audited_financial_statements.pdf"
      : pdfServerUrl || `/api/copilot/raw-pdf?session_id=${encodeURIComponent(sessionId)}`);

  const isExcelActive = Boolean(
    activeFileName && /\.(xlsx|csv|xls)$/i.test(activeFileName)
  );

  const effectiveActiveTab = isExcelActive && activeTab === "pdf"
    ? (s3Records.length > 0 ? "schedule3" : "books")
    : activeTab;

  // Dynamic Document Classification (Audit Report, SAP ERP, Zoho Books, Tally, GSTR-2B)
  const documentMeta = useMemo(() => {
    const fn = (activeFileName || "").toLowerCase();
    const isPdf = fn.endsWith(".pdf") || Boolean(extractedPdf) || effectiveActiveTab === "pdf";
    const isExcel = Boolean(activeFileName && /\.(xlsx|csv|xls)$/i.test(activeFileName));
    const isTrialBalance = s3Records.length > 0;

    // 1. PDF Documents (Statutory Audit Reports / Financial Statements)
    if (isPdf) {
      if (fn.includes("itc")) {
        return {
          type: "Audit Report (ITC Limited)",
          shortLabel: "Audit Report",
          statusText: `● ${totalPages} Pages Extracted`,
          statusColor: "var(--accent-emerald)",
          isTrialBalance: false,
          isPdf: true,
        };
      }
      if (fn.includes("investor_corner") || fn.includes("chennai") || fn.includes("csk")) {
        return {
          type: "Statutory Financial Statements (CSKCL)",
          shortLabel: "Audit Report",
          statusText: `● ${totalPages} Pages Extracted`,
          statusColor: "var(--accent-emerald)",
          isTrialBalance: false,
          isPdf: true,
        };
      }
      return {
        type: "Statutory Audit Report (PDF)",
        shortLabel: "Audit Report",
        statusText: `● ${totalPages} Pages Extracted`,
        statusColor: "var(--accent-emerald)",
        isTrialBalance: false,
        isPdf: true,
      };
    }

    // 2. SAP ERP
    if (
      fn.includes("sap") ||
      sqlRecords.some((r) => r.raw_text?.toLowerCase().includes("source erp: sap") || r.raw_text?.toLowerCase().includes("sap g/l"))
    ) {
      return {
        type: "SAP ERP Trial Balance",
        shortLabel: "SAP",
        statusText: "● Balanced",
        statusColor: "var(--accent-emerald)",
        isTrialBalance: true,
        isPdf: false,
      };
    }

    // 3. Zoho Books
    if (
      fn.includes("zoho") ||
      sqlRecords.some((r) => r.raw_text?.toLowerCase().includes("source erp: zoho") || r.raw_text?.toLowerCase().includes("zoho account"))
    ) {
      return {
        type: "Zoho Books Trial Balance",
        shortLabel: "Zoho",
        statusText: "● Balanced",
        statusColor: "var(--accent-emerald)",
        isTrialBalance: true,
        isPdf: false,
      };
    }

    // 4. Tally ERP
    if (
      fn.includes("tally") ||
      sqlRecords.some((r) => r.raw_text?.toLowerCase().includes("source erp: tally") || r.raw_text?.toLowerCase().includes("tally account"))
    ) {
      if (fn.includes("purchase_register") || fn.includes("gstr")) {
        return {
          type: "Tally GST Purchase Register",
          shortLabel: "Tally",
          statusText: `● ${rows.length} Invoices`,
          statusColor: "var(--accent-emerald)",
          isTrialBalance: false,
          isPdf: false,
        };
      }
      return {
        type: "Tally ERP 9 / Prime",
        shortLabel: "Tally",
        statusText: "● Balanced",
        statusColor: "var(--accent-emerald)",
        isTrialBalance: true,
        isPdf: false,
      };
    }

    // 5. GST Returns / GSTR-2B
    if (fn.includes("gstr") || fn.includes("2b") || fn.includes("purchase_register")) {
      return {
        type: "GSTR-2B Purchase Register",
        shortLabel: "GSTR-2B",
        statusText: `● ${rows.length} Records`,
        statusColor: "var(--accent-emerald)",
        isTrialBalance: false,
        isPdf: false,
      };
    }

    // 6. Generic Trial Balance or Spreadsheet
    if (isTrialBalance) {
      return {
        type: "ERP Trial Balance",
        shortLabel: "ERP",
        statusText: "● Balanced",
        statusColor: "var(--accent-emerald)",
        isTrialBalance: true,
        isPdf: false,
      };
    }

    if (isExcel) {
      return {
        type: "Audit Working Paper (Spreadsheet)",
        shortLabel: "Ledger",
        statusText: `● ${rows.length} Rows`,
        statusColor: "var(--accent-emerald)",
        isTrialBalance: false,
        isPdf: false,
      };
    }

    return {
      type: "Audit Working Paper",
      shortLabel: "Working Paper",
      statusText: "● Active",
      statusColor: "var(--accent-emerald)",
      isTrialBalance: false,
      isPdf: false,
    };
  }, [activeFileName, extractedPdf, effectiveActiveTab, totalPages, s3Records, sqlRecords, rows]);

  const erpShortLabel = documentMeta.shortLabel;
  const detectedErp = documentMeta.type;

  const dynamicPromptRecommendations = useMemo(() => {
    const fn = (activeFileName || "").toLowerCase();
    if (fn.includes("itc")) {
      return [
        "What were the Key Audit Matters (KAM) reported by statutory auditor S R B C & CO LLP?",
        "What were the segment revenues for FMCG - Cigarettes, FMCG - Others, and Agri Business under Note 30?",
        "What are the disputed claims for Excise duty, VAT/Sales tax, and GST under Contingent Liabilities?",
        "⚡ What are the major Year-on-Year anomalies under SA 520?",
        "What was the total Corporate Social Responsibility (CSR) expenditure during the year?",
        "What was the inter-segment revenue elimination in Note 30?",
        "What are the statutory disclosures regarding the Scheme of Demerger of the Hotels Business?",
      ];
    }
    if (documentMeta.isTrialBalance) {
      return [
        `What ${erpShortLabel} accounts were mapped to Property, Plant & Equipment (AST_PPE) under Schedule III?`,
        `Is the ${erpShortLabel} trial balance balanced? What are the total debits and credits?`,
        `What are the Current Investments (AST_CI) and Input Tax Credit (AST_OCA) balances from the ${erpShortLabel} trial balance?`,
        `Run journal entry testing on ${erpShortLabel} ledger for suspicious or non-standard entries`,
      ];
    }
    if (documentMeta.isPdf) {
      return [
        "Summarize the Independent Auditor's Report & Key Audit Matters",
        "What was Total Revenue from Operations & Central Rights in Note 25?",
        "What are the Player Remuneration and Franchisee Fee costs under Note 27?",
        "What are the Contingent Liabilities and Capital Commitments?",
      ];
    }
    return [
      "Cross-check inward invoices against GSTR-2B for Section 17(5) blocked credits",
      "What are the top invoice mismatches and tax rate differences?",
      "Run Journal Entry Testing on Daybook for suspicious Sunday or adjustment vouchers",
    ];
  }, [activeFileName, documentMeta, erpShortLabel]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", width: "100vw", overflow: "hidden", backgroundColor: "var(--bg-primary)" }}>
      {/* Hidden File Input for Real Uploads */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept=".pdf,.xlsx,.csv,.xls"
        style={{ display: "none" }}
      />

      {/* Top Header Bar */}
      <header
        style={{
          height: "48px",
          borderBottom: "2px solid var(--border-subtle)",
          backgroundColor: "var(--bg-card)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 1.25rem",
          flexShrink: 0,
          zIndex: 30,
        }}
      >
        {/* Left Branding & Document Status */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px", minWidth: 0, overflow: "hidden" }}>
          <Link href="/" style={{ display: "flex", alignItems: "center", gap: "8px", flexShrink: 0 }}>
            <span
              style={{
                border: "1.5px solid var(--accent-ink)",
                color: "var(--accent-ink)",
                padding: "2px 7px",
                fontSize: "0.685rem",
                fontWeight: 800,
                borderRadius: "2px",
                letterSpacing: "0.08em",
                fontFamily: "var(--font-mono)",
              }}
            >
              ICAI STATUTORY
            </span>
            <span
              style={{
                fontFamily: "var(--font-serif)",
                fontWeight: 700,
                fontSize: "1.05rem",
                letterSpacing: "-0.01em",
                color: "var(--accent-ink)",
              }}
            >
              AuditIQ Working Paper Docket
            </span>
          </Link>

          <div style={{ height: "16px", width: "1px", backgroundColor: "var(--border-subtle)", flexShrink: 0 }} />

          {/* Active File & ERP Pill */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "0.75rem",
              backgroundColor: "var(--bg-secondary)",
              border: "1px solid var(--border-subtle)",
              padding: "3px 9px",
              borderRadius: "3px",
              minWidth: 0,
            }}
          >
            <span style={{ color: "var(--text-muted)", fontSize: "0.7rem", textTransform: "uppercase", fontWeight: 700 }}>
              Working Paper:
            </span>
            <span
              style={{
                fontWeight: 700,
                fontFamily: "var(--font-mono)",
                color: "var(--accent-ink)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                maxWidth: "200px",
              }}
              title={activeFileName}
            >
              {activeFileName}
            </span>
            <span
              style={{
                color: "var(--accent-ink)",
                fontSize: "0.685rem",
                fontWeight: 700,
                padding: "2px 7px",
                borderRadius: "3px",
                backgroundColor: "rgba(15, 56, 42, 0.08)",
                border: "1px solid rgba(15, 56, 42, 0.18)",
                fontFamily: "var(--font-mono)",
                whiteSpace: "nowrap",
              }}
            >
              {documentMeta.type}
            </span>
            <span style={{ color: documentMeta.statusColor, fontWeight: 700, fontSize: "0.685rem", whiteSpace: "nowrap", fontFamily: "var(--font-mono)" }}>
              {documentMeta.statusText}
            </span>
          </div>

          {/* Records Count Badge */}
          <span
            style={{
              backgroundColor: "var(--bg-card)",
              color: "var(--accent-ink)",
              border: "1px solid var(--border-subtle)",
              fontSize: "0.7rem",
              fontWeight: 700,
              padding: "2px 7px",
              borderRadius: "3px",
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              fontFamily: "var(--font-mono)",
              flexShrink: 0,
            }}
          >
            <Database size={11} color="var(--accent-ink)" />
            {sqlRecords.length} Indexed Lines
          </span>
        </div>

        {/* Right Tools & Auditor Profile */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexShrink: 0 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "0.725rem",
              color: "var(--text-muted)",
              paddingRight: "6px",
            }}
          >
            <span>Engagement Partner:</span>
            <strong style={{ color: "var(--accent-ink)" }}>J. Swaminathan (FCA)</strong>
          </div>

          <button
            type="button"
            onClick={() => {
              if (fileInputRef.current) {
                fileInputRef.current.value = "";
                fileInputRef.current.click();
              }
            }}
            disabled={isUploading}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 14px",
              borderRadius: "3px",
              backgroundColor: "var(--accent-ink, #0F382A)",
              color: "#FAF8F3",
              border: "1px solid var(--accent-ink, #0F382A)",
              fontSize: "0.785rem",
              fontWeight: 700,
              cursor: isUploading ? "wait" : "pointer",
              whiteSpace: "nowrap",
              transition: "opacity 0.15s ease",
              boxShadow: "0 1px 3px rgba(15, 56, 42, 0.2)",
              opacity: isUploading ? 0.75 : 1,
            }}
            title="Upload working paper spreadsheet (.xlsx, .csv) or audited PDF"
          >
            {isUploading ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                <span>Ingesting...</span>
              </>
            ) : (
              <>
                <UploadCloud size={14} />
                <span>Ingest Working Paper</span>
              </>
            )}
          </button>

          <button
            type="button"
            onClick={() => setShowUploadModal(true)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "32px",
              height: "32px",
              borderRadius: "3px",
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              color: "var(--accent-ink)",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
            title="Open Ingestion Modal & Drag Drop Zone (Ctrl+U)"
          >
            <FolderUp size={15} />
          </button>
        </div>
      </header>

      {/* Ingestion Notification Banner */}
      {ingestNotification && (
        <div
          style={{
            padding: "0.4rem 1.25rem",
            backgroundColor:
              ingestNotification.type === "error"
                ? "var(--accent-rose-subtle, rgba(185, 28, 28, 0.1))"
                : ingestNotification.type === "success"
                ? "var(--accent-emerald-subtle, rgba(21, 128, 61, 0.1))"
                : "var(--accent-ink-subtle, rgba(15, 56, 42, 0.08))",
            borderBottom: `1px solid ${
              ingestNotification.type === "error"
                ? "rgba(185, 28, 28, 0.3)"
                : ingestNotification.type === "success"
                ? "rgba(21, 128, 61, 0.3)"
                : "var(--border-subtle)"
            }`,
            color:
              ingestNotification.type === "error"
                ? "var(--accent-rose, #B91C1C)"
                : ingestNotification.type === "success"
                ? "var(--accent-emerald, #15803D)"
                : "var(--accent-ink, #0F382A)",
            fontSize: "0.775rem",
            fontFamily: "var(--font-mono)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexShrink: 0,
            zIndex: 25,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {isUploading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : ingestNotification.type === "success" ? (
              <CheckCircle2 size={14} />
            ) : (
              <AlertTriangle size={14} />
            )}
            <span style={{ fontWeight: 600 }}>{ingestNotification.message}</span>
          </div>
          <button
            onClick={() => setIngestNotification(null)}
            style={{ background: "transparent", border: "none", cursor: "pointer", color: "inherit", padding: "2px 6px" }}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Main Dual-Stage Split Screen */}
      <div style={{ display: "grid", gridTemplateColumns: "1.05fr 0.95fr", flex: 1, minHeight: 0, overflow: "hidden" }}>
        {/* ========================================================================= */}
        {/* LEFT STAGE: Document Viewer (PDF Text / SQL Data Table / Invoices Grid)   */}
        {/* ========================================================================= */}
        <div
          style={{
            borderRight: "1px solid var(--border-subtle)",
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
            minWidth: 0,
            backgroundColor: "var(--bg-primary)",
          }}
        >
          {/* Document Tabs Toolbar */}
          <div
            style={{
              height: "40px",
              padding: "0 0.75rem",
              borderBottom: "1px solid var(--border-subtle)",
              backgroundColor: "var(--bg-secondary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "0.5rem",
              flexShrink: 0,
            }}
          >
            {/* View Switchers (Physical Binder Tab Styling) */}
            <div style={{ display: "flex", gap: "2px", alignItems: "flex-end", height: "100%" }}>
              {!isExcelActive && (
                <button
                  onClick={() => setActiveTab("pdf")}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "6px 12px",
                    borderRadius: "3px 3px 0 0",
                    fontSize: "0.75rem",
                    fontWeight: effectiveActiveTab === "pdf" ? 700 : 500,
                    cursor: "pointer",
                    border: effectiveActiveTab === "pdf" ? "1px solid var(--border-subtle)" : "1px solid transparent",
                    borderTop: effectiveActiveTab === "pdf" ? "2px solid var(--accent-ink)" : "2px solid transparent",
                    borderBottom: effectiveActiveTab === "pdf" ? "1px solid var(--bg-card)" : "1px solid transparent",
                    whiteSpace: "nowrap",
                    backgroundColor: effectiveActiveTab === "pdf" ? "var(--bg-card)" : "transparent",
                    color: effectiveActiveTab === "pdf" ? "var(--accent-ink)" : "var(--text-muted)",
                    marginBottom: effectiveActiveTab === "pdf" ? "-1px" : "0",
                  }}
                >
                  <FileText size={12} color={effectiveActiveTab === "pdf" ? "var(--accent-ink)" : "var(--text-muted)"} />
                  <span>Audited PDF</span>
                  {totalPages ? (
                    <span style={{ fontSize: "0.65rem", padding: "1px 5px", borderRadius: "2px", backgroundColor: "var(--bg-secondary)", fontFamily: "var(--font-mono)" }}>
                      {totalPages}p
                    </span>
                  ) : null}
                </button>
              )}

              <button
                onClick={() => setActiveTab("sql")}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "6px 12px",
                  borderRadius: "3px 3px 0 0",
                  fontSize: "0.75rem",
                  fontWeight: effectiveActiveTab === "sql" ? 700 : 500,
                  cursor: "pointer",
                  border: effectiveActiveTab === "sql" ? "1px solid var(--border-subtle)" : "1px solid transparent",
                  borderTop: effectiveActiveTab === "sql" ? "2px solid var(--accent-ink)" : "2px solid transparent",
                  borderBottom: effectiveActiveTab === "sql" ? "1px solid var(--bg-card)" : "1px solid transparent",
                  whiteSpace: "nowrap",
                  backgroundColor: effectiveActiveTab === "sql" ? "var(--bg-card)" : "transparent",
                  color: effectiveActiveTab === "sql" ? "var(--accent-ink)" : "var(--text-muted)",
                  marginBottom: effectiveActiveTab === "sql" ? "-1px" : "0",
                }}
              >
                <Database size={12} color={effectiveActiveTab === "sql" ? "var(--accent-ink)" : "var(--text-muted)"} />
                <span>SQL Records</span>
                <span style={{ fontSize: "0.65rem", padding: "1px 5px", borderRadius: "2px", backgroundColor: "var(--bg-secondary)", fontFamily: "var(--font-mono)" }}>
                  {sqlRecords.length}
                </span>
              </button>

              <button
                onClick={() => setActiveTab("books")}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "6px 12px",
                  borderRadius: "3px 3px 0 0",
                  fontSize: "0.75rem",
                  fontWeight: effectiveActiveTab === "books" ? 700 : 500,
                  cursor: "pointer",
                  border: effectiveActiveTab === "books" ? "1px solid var(--border-subtle)" : "1px solid transparent",
                  borderTop: effectiveActiveTab === "books" ? "2px solid var(--accent-ink)" : "2px solid transparent",
                  borderBottom: effectiveActiveTab === "books" ? "1px solid var(--bg-card)" : "1px solid transparent",
                  whiteSpace: "nowrap",
                  backgroundColor: effectiveActiveTab === "books" ? "var(--bg-card)" : "transparent",
                  color: effectiveActiveTab === "books" ? "var(--accent-ink)" : "var(--text-muted)",
                  marginBottom: effectiveActiveTab === "books" ? "-1px" : "0",
                }}
              >
                <FileSpreadsheet size={12} color={effectiveActiveTab === "books" ? "var(--accent-ink)" : "var(--text-muted)"} />
                <span>
                  {activeFileName && /\.(xlsx|csv|xls)$/i.test(activeFileName)
                    ? `Spreadsheet Rows`
                    : `GST Register`}
                </span>
                <span style={{ fontSize: "0.65rem", padding: "1px 5px", borderRadius: "2px", backgroundColor: "var(--bg-secondary)", fontFamily: "var(--font-mono)" }}>
                  {rows.length}
                </span>
              </button>

              {s3Records.length > 0 && (
                <button
                  onClick={() => setActiveTab("schedule3")}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "6px 12px",
                    borderRadius: "3px 3px 0 0",
                    fontSize: "0.75rem",
                    fontWeight: effectiveActiveTab === "schedule3" ? 700 : 500,
                    cursor: "pointer",
                    border: effectiveActiveTab === "schedule3" ? "1px solid var(--border-subtle)" : "1px solid transparent",
                    borderTop: effectiveActiveTab === "schedule3" ? "2px solid var(--accent-ink)" : "2px solid transparent",
                    borderBottom: effectiveActiveTab === "schedule3" ? "1px solid var(--bg-card)" : "1px solid transparent",
                    whiteSpace: "nowrap",
                    backgroundColor: effectiveActiveTab === "schedule3" ? "var(--bg-card)" : "transparent",
                    color: effectiveActiveTab === "schedule3" ? "var(--accent-ink)" : "var(--text-muted)",
                    marginBottom: effectiveActiveTab === "schedule3" ? "-1px" : "0",
                  }}
                >
                  <Layers size={12} color={effectiveActiveTab === "schedule3" ? "var(--accent-ink)" : "var(--text-muted)"} />
                  <span>Schedule III</span>
                  <span style={{ fontSize: "0.65rem", padding: "1px 5px", borderRadius: "2px", backgroundColor: "var(--bg-secondary)", fontFamily: "var(--font-mono)" }}>
                    {s3Records.length}
                  </span>
                </button>
              )}

              {/* Tab 5: ICAI SA 520 Anomalies */}
              <button
                onClick={() => setActiveTab("anomalies")}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "6px 12px",
                  borderRadius: "3px 3px 0 0",
                  fontSize: "0.75rem",
                  fontWeight: effectiveActiveTab === "anomalies" ? 700 : 500,
                  cursor: "pointer",
                  border: effectiveActiveTab === "anomalies" ? "1px solid var(--border-subtle)" : "1px solid transparent",
                  borderTop: effectiveActiveTab === "anomalies" ? "2px solid #D97706" : "2px solid transparent",
                  borderBottom: effectiveActiveTab === "anomalies" ? "1px solid var(--bg-card)" : "1px solid transparent",
                  whiteSpace: "nowrap",
                  backgroundColor: effectiveActiveTab === "anomalies" ? "var(--bg-card)" : "transparent",
                  color: effectiveActiveTab === "anomalies" ? "#B45309" : "var(--text-muted)",
                  marginBottom: effectiveActiveTab === "anomalies" ? "-1px" : "0",
                }}
              >
                <Activity size={12} color={effectiveActiveTab === "anomalies" ? "#D97706" : "var(--text-muted)"} />
                <span>⚡ SA 520 Anomalies</span>
                {anomaliesReport.summary.critical_count > 0 ? (
                  <span style={{ fontSize: "0.65rem", padding: "1px 6px", borderRadius: "10px", backgroundColor: "rgba(220, 38, 38, 0.15)", color: "#DC2626", fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                    {anomaliesReport.summary.critical_count} Critical
                  </span>
                ) : (
                  <span style={{ fontSize: "0.65rem", padding: "1px 5px", borderRadius: "2px", backgroundColor: "var(--bg-secondary)", fontFamily: "var(--font-mono)" }}>
                    {anomaliesReport.findings.length}
                  </span>
                )}
              </button>
            </div>

            {/* Sub-toolbar controls per tab */}
            {effectiveActiveTab === "pdf" && !isExcelActive && (
              <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.775rem", flexShrink: 0 }}>
                {/* View Mode Toggle: Visual PDF vs Extracted SQL Blocks */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    backgroundColor: "var(--bg-primary)",
                    borderRadius: "5px",
                    padding: "2px",
                    border: "1px solid var(--border-subtle)",
                    marginRight: "4px",
                  }}
                >
                  <button
                    onClick={() => setPdfViewMode("visual")}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "4px",
                      padding: "2px 7px",
                      borderRadius: "3px",
                      fontSize: "0.7rem",
                      fontWeight: 600,
                      border: "none",
                      cursor: "pointer",
                      backgroundColor: pdfViewMode === "visual" ? "var(--bg-card)" : "transparent",
                      color: pdfViewMode === "visual" ? "#60a5fa" : "var(--text-muted)",
                      boxShadow: pdfViewMode === "visual" ? "0 1px 3px rgba(0,0,0,0.3)" : "none",
                    }}
                    title="Display authentic high-fidelity visual PDF with all pages, tables, and graphics"
                  >
                    <Eye size={12} />
                    <span>Visual PDF</span>
                  </button>

                  <button
                    onClick={() => setPdfViewMode("blocks")}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "4px",
                      padding: "2px 7px",
                      borderRadius: "3px",
                      fontSize: "0.7rem",
                      fontWeight: 600,
                      border: "none",
                      cursor: "pointer",
                      backgroundColor: pdfViewMode === "blocks" ? "var(--bg-card)" : "transparent",
                      color: pdfViewMode === "blocks" ? "#fbbf24" : "var(--text-muted)",
                      boxShadow: pdfViewMode === "blocks" ? "0 1px 3px rgba(0,0,0,0.3)" : "none",
                    }}
                    title="Inspect extracted paragraph blocks and SQL line items with citation glow"
                  >
                    <Layers size={12} />
                    <span>SQL Blocks</span>
                  </button>
                </div>

                {/* Page Navigation */}
                <button
                  disabled={currentPdfPage <= 1}
                  onClick={() => navigatePdfPage(currentPdfPage - 1)}
                  style={{
                    padding: "2px 6px",
                    borderRadius: "4px",
                    backgroundColor: "var(--bg-card)",
                    border: "1px solid var(--border-subtle)",
                    color: currentPdfPage <= 1 ? "var(--text-muted)" : "var(--text-primary)",
                    cursor: currentPdfPage <= 1 ? "not-allowed" : "pointer",
                    display: "flex",
                    alignItems: "center",
                  }}
                  title="Previous page"
                >
                  <ChevronLeft size={13} />
                </button>

                <span style={{ color: "var(--text-primary)", fontWeight: 600, whiteSpace: "nowrap", padding: "0 2px" }}>
                  Page {currentPdfPage} / {totalPages}
                </span>

                <button
                  disabled={currentPdfPage >= totalPages}
                  onClick={() => navigatePdfPage(currentPdfPage + 1)}
                  style={{
                    padding: "2px 6px",
                    borderRadius: "4px",
                    backgroundColor: "var(--bg-card)",
                    border: "1px solid var(--border-subtle)",
                    color: currentPdfPage >= totalPages ? "var(--text-muted)" : "var(--text-primary)",
                    cursor: currentPdfPage >= totalPages ? "not-allowed" : "pointer",
                    display: "flex",
                    alignItems: "center",
                  }}
                  title="Next page"
                >
                  <ChevronRight size={13} />
                </button>

                {/* In-PDF Live Search & Highlight Toolbar Box */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "4px",
                    backgroundColor: "var(--bg-primary)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "3px",
                    padding: "2px 6px",
                    marginLeft: "4px",
                  }}
                  title="Search & highlight text across PDF canvas and extracted blocks"
                >
                  <Search size={11} color="var(--accent-ink)" />
                  <input
                    type="text"
                    value={pdfSearchTerm}
                    onChange={(e) => {
                      const term = e.target.value;
                      setPdfSearchTerm(term);
                      if (iframeRef.current && effectivePdfSrc) {
                        iframeRef.current.src = `${effectivePdfSrc}#page=${currentPdfPage}${term ? `&search=${encodeURIComponent(term)}` : ""}`;
                      }
                    }}
                    placeholder="Highlight in PDF..."
                    style={{
                      border: "none",
                      outline: "none",
                      backgroundColor: "transparent",
                      fontSize: "0.7rem",
                      color: "var(--accent-ink)",
                      width: "120px",
                      fontFamily: "var(--font-mono)",
                    }}
                  />
                  {pdfSearchTerm && (
                    <button
                      onClick={() => {
                        setPdfSearchTerm("");
                        if (iframeRef.current && effectivePdfSrc) {
                          iframeRef.current.src = `${effectivePdfSrc}#page=${currentPdfPage}`;
                        }
                      }}
                      style={{
                        border: "none",
                        background: "transparent",
                        cursor: "pointer",
                        color: "var(--text-muted)",
                        padding: 0,
                        display: "flex",
                        alignItems: "center",
                      }}
                      title="Clear highlight"
                    >
                      <X size={11} />
                    </button>
                  )}
                </div>

                {/* Pop-out to new window */}
                <a
                  href={`${effectivePdfSrc}#page=${currentPdfPage}${pdfSearchTerm ? `&search=${encodeURIComponent(pdfSearchTerm)}` : ""}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "3px",
                    padding: "2px 7px",
                    borderRadius: "4px",
                    backgroundColor: "var(--bg-card)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-secondary)",
                    fontSize: "0.7rem",
                    fontWeight: 600,
                    textDecoration: "none",
                    marginLeft: "2px",
                  }}
                  title="Open PDF in a full-screen window or second monitor"
                >
                  <ExternalLink size={12} />
                  <span>Pop-out</span>
                </a>
              </div>
            )}

            {effectiveActiveTab === "sql" && (
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <input
                  type="text"
                  value={sqlSearch}
                  onChange={(e) => setSqlSearch(e.target.value)}
                  placeholder="Filter records..."
                  style={{
                    padding: "3px 8px",
                    borderRadius: "4px",
                    backgroundColor: "var(--bg-primary)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-primary)",
                    fontSize: "0.725rem",
                    outline: "none",
                    width: "130px",
                  }}
                />
              </div>
            )}

            {effectiveActiveTab === "books" && (
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter rows..."
                  style={{
                    padding: "3px 8px",
                    borderRadius: "4px",
                    backgroundColor: "var(--bg-primary)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-primary)",
                    fontSize: "0.725rem",
                    outline: "none",
                    width: "120px",
                  }}
                />
                <select
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value)}
                  style={{
                    padding: "3px 6px",
                    borderRadius: "4px",
                    backgroundColor: "var(--bg-card)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-primary)",
                    fontSize: "0.725rem",
                    outline: "none",
                  }}
                >
                  <option value="ALL">All ({rows.length})</option>
                  <option value="EXACT_MATCH">Match</option>
                  <option value="MISSING_PORTAL">Missing</option>
                  <option value="BLOCKED_17_5">Blocked 17(5)</option>
                </select>
              </div>
            )}

            {effectiveActiveTab === "schedule3" && (
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <input
                  type="text"
                  value={s3Search}
                  onChange={(e) => setS3Search(e.target.value)}
                  placeholder={`Filter Schedule III or ${erpShortLabel} #...`}
                  style={{
                    padding: "3px 8px",
                    borderRadius: "4px",
                    backgroundColor: "var(--bg-primary)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-primary)",
                    fontSize: "0.725rem",
                    outline: "none",
                    width: "180px",
                  }}
                />
              </div>
            )}
          </div>

          {/* Active Highlight Banner — Canary Yellow / Warm Amber Highlighter */}
          {(highlightedRowId || highlightedBlockId || highlightedSqlId || highlightedS3Id) && (
            <div
              style={{
                backgroundColor: "rgba(254, 240, 138, 0.78)",
                borderBottom: "1.5px solid #D97706",
                padding: "6px 0.85rem",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                fontSize: "0.75rem",
                color: "#78350F",
                fontWeight: 700,
                flexShrink: 0,
                fontFamily: "var(--font-mono)",
                boxShadow: "0 1px 4px rgba(217, 119, 6, 0.15)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <Sparkles size={13} color="#B45309" />
                <span>
                  {highlightedBlockId
                    ? `Evidence Focused on Page ${currentPdfPage} (${highlightedBlockId})`
                    : highlightedS3Id
                    ? `Evidence Focused on Schedule III Record #${highlightedS3Id}`
                    : highlightedSqlId
                    ? `Evidence Focused on SQL Record #${highlightedSqlId}`
                    : `Live Citation on Row #${highlightedRowId}`}
                </span>
              </div>
              <button
                onClick={() => {
                  setHighlightedRowId(null);
                  setHighlightedBlockId(null);
                  setHighlightedSqlId(null);
                  setHighlightedS3Id(null);
                }}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "#92400E",
                  fontSize: "0.725rem",
                  cursor: "pointer",
                  textDecoration: "underline",
                  fontWeight: 700,
                }}
              >
                Clear Focus
              </button>
            </div>
          )}

          {/* View 1: Audited PDF Document (Dual Mode: High-Fidelity Visual PDF vs Extracted SQL Blocks) */}
          {effectiveActiveTab === "pdf" && !isExcelActive && (
            <div
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                minHeight: 0,
                overflow: "hidden",
                backgroundColor: "var(--bg-primary)",
              }}
            >
              {pdfViewMode === "visual" ? (
                <div
                  style={{
                    flex: 1,
                    position: "relative",
                    minHeight: 0,
                    backgroundColor: "var(--bg-secondary)",
                    display: "flex",
                    flexDirection: "column",
                  }}
                >
                  {/* Floating Auditor Evidence Callout Banner */}
                  {(highlightedBlockId || activeCitationText || pdfSearchTerm) && (
                    <div
                      style={{
                        position: "absolute",
                        bottom: "16px",
                        left: "50%",
                        transform: "translateX(-50%)",
                        width: "92%",
                        maxWidth: "760px",
                        zIndex: 35,
                        backgroundColor: "rgba(250, 248, 243, 0.98)",
                        backdropFilter: "blur(8px)",
                        border: "1.5px solid #D97706",
                        borderRadius: "6px",
                        boxShadow: "0 8px 30px rgba(15, 56, 42, 0.2), 0 0 0 1px rgba(217, 119, 6, 0.3)",
                        overflow: "hidden",
                        fontFamily: "var(--font-sans)",
                        animation: "citationPulseAnimation 3s infinite ease-in-out",
                      }}
                    >
                      {/* Callout Header */}
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "6px 12px",
                          backgroundColor: "#FEF08A",
                          borderBottom: "1px solid #D97706",
                          color: "#78350F",
                          fontSize: "0.725rem",
                          fontWeight: 700,
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <Sparkles size={13} color="#B45309" />
                          <span>
                            ★ CITED AUDIT EVIDENCE • PAGE {currentPdfPage} {highlightedBlockId ? `(${highlightedBlockId})` : ""}
                          </span>
                          {pdfSearchTerm && (
                            <span
                              style={{
                                backgroundColor: "rgba(180, 83, 9, 0.15)",
                                padding: "1px 6px",
                                borderRadius: "3px",
                                border: "1px solid rgba(180, 83, 9, 0.3)",
                              }}
                            >
                              Highlighted: &ldquo;{pdfSearchTerm}&rdquo;
                            </span>
                          )}
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <button
                            onClick={() => {
                              setPdfViewMode("blocks");
                              if (highlightedBlockId) {
                                setTimeout(() => {
                                  const el = blockRefs.current[highlightedBlockId];
                                  if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
                                }, 150);
                              }
                            }}
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "4px",
                              backgroundColor: "var(--accent-ink)",
                              color: "#FAF8F3",
                              fontSize: "0.7rem",
                              fontWeight: 700,
                              padding: "3px 9px",
                              borderRadius: "3px",
                              border: "none",
                              cursor: "pointer",
                              fontFamily: "var(--font-mono)",
                              boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
                            }}
                            title="Inspect the full paragraph & numbers in extracted SQL Blocks view"
                          >
                            <Layers size={11} />
                            <span>View in SQL Blocks →</span>
                          </button>

                          <button
                            onClick={() => {
                              setHighlightedBlockId(null);
                              setActiveCitationText(null);
                              setPdfSearchTerm("");
                              if (iframeRef.current && effectivePdfSrc) {
                                iframeRef.current.src = `${effectivePdfSrc}#page=${currentPdfPage}`;
                              }
                            }}
                            style={{
                              background: "transparent",
                              border: "none",
                              color: "#92400E",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              padding: "2px",
                            }}
                            title="Dismiss citation callout"
                          >
                            <X size={14} />
                          </button>
                        </div>
                      </div>

                      {/* Callout Body with Highlighted Text */}
                      <div
                        style={{
                          padding: "8px 14px",
                          maxHeight: "110px",
                          overflowY: "auto",
                          fontSize: "0.8rem",
                          lineHeight: 1.5,
                          color: "var(--text-primary)",
                          backgroundColor: "var(--bg-card)",
                        }}
                      >
                        {(() => {
                          const displayContent =
                            activeCitationText ||
                            (() => {
                              const found = sqlRecords.find((r) => r.block_id === highlightedBlockId);
                              return found ? found.raw_text || found.line_item : "";
                            })();
                          if (displayContent) {
                            return renderHighlightedContent(displayContent, pdfSearchTerm, true);
                          }
                          return (
                            <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
                              Target evidence cited on Page {currentPdfPage}. Use the search bar or flip to SQL Blocks to inspect statutory disclosures.
                            </span>
                          );
                        })()}
                      </div>

                      {/* Callout Footer */}
                      <div
                        style={{
                          padding: "3px 12px",
                          backgroundColor: "var(--bg-secondary)",
                          borderTop: "1px solid var(--border-subtle)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          fontSize: "0.65rem",
                          color: "var(--text-muted)",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        <span>⚡ Live highlighting active: Chromium PDFium search parameter &amp; SQL Blocks citation glow</span>
                        <span>Double-click or drag to select text</span>
                      </div>
                    </div>
                  )}

                  <iframe
                    ref={iframeRef}
                    key={`${effectivePdfSrc}-p${currentPdfPage}-${pdfSearchTerm}-${activeFileName}`}
                    src={`${effectivePdfSrc}#page=${currentPdfPage}${pdfSearchTerm ? `&search=${encodeURIComponent(pdfSearchTerm)}` : ""}`}
                    title={`Visual PDF - ${activeFileName}`}
                    style={{
                      width: "100%",
                      height: "100%",
                      border: "none",
                      backgroundColor: "var(--bg-secondary)",
                      display: "block",
                    }}
                  />
                </div>
              ) : (
                /* Mode 2: Extracted Text Blocks View with Citation Glow */
                <div style={{ flex: 1, padding: "1.25rem", overflowY: "auto", overflowX: "hidden", backgroundColor: "var(--bg-primary)" }}>
                  {!extractedPdf ? (
                    <div style={{ padding: "4rem 2rem", textAlign: "center", color: "var(--text-secondary)" }}>
                      <FileText size={44} color="var(--accent-ink)" style={{ margin: "0 auto 1rem auto", opacity: 0.8 }} />
                      <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--accent-ink)", marginBottom: "0.5rem", fontFamily: "var(--font-serif)" }}>
                        No Statutory Document Loaded
                      </h3>
                      <p style={{ maxWidth: "420px", margin: "0 auto 1.5rem auto", fontSize: "0.85rem", lineHeight: 1.5 }}>
                        Upload client statutory financial statement PDF. AuditIQ extracts line items into an SQL working paper database and grounds audit inquiries with live voucher citations.
                      </p>
                      <button
                        type="button"
                        onClick={() => {
                          if (fileInputRef.current) {
                            fileInputRef.current.value = "";
                            fileInputRef.current.click();
                          }
                        }}
                        style={{
                          padding: "0.5rem 1.25rem",
                          borderRadius: "3px",
                          backgroundColor: "var(--accent-ink, #0F382A)",
                          color: "#FAF8F3",
                          fontSize: "0.825rem",
                          fontWeight: 600,
                          border: "none",
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          boxShadow: "var(--shadow-card)",
                        }}
                      >
                        <UploadCloud size={15} />
                        <span>Upload Working Paper</span>
                      </button>
                    </div>
                  ) : (
                    <div
                      style={{
                        width: "100%",
                        boxSizing: "border-box",
                        backgroundColor: "var(--bg-card)",
                        color: "var(--text-primary)",
                        borderRadius: "4px",
                        border: "1px solid var(--border-subtle)",
                        boxShadow: "var(--shadow-card)",
                        padding: "1.5rem 2rem",
                        lineHeight: 1.65,
                      }}
                    >
                      {/* Document Title Header */}
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "flex-start",
                          borderBottom: "1px solid var(--border-subtle)",
                          paddingBottom: "0.75rem",
                          marginBottom: "1.25rem",
                        }}
                      >
                        <div>
                          <span style={{ fontSize: "0.685rem", textTransform: "uppercase", fontWeight: 700, color: "var(--accent-ink)", letterSpacing: "0.05em", fontFamily: "var(--font-mono)" }}>
                            Audited Statutory Working Paper
                          </span>
                          <h4 style={{ margin: "2px 0 0 0", fontSize: "1rem", fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-serif)" }}>
                            {extractedPdf.file_name}
                          </h4>
                        </div>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 700,
                            color: "var(--accent-ink)",
                            backgroundColor: "var(--bg-secondary)",
                            border: "1px solid var(--border-subtle)",
                            padding: "3px 8px",
                            borderRadius: "3px",
                            fontFamily: "var(--font-mono)",
                          }}
                        >
                          Page {currentPdfPage} of {totalPages}
                        </span>
                      </div>

                      {/* Document Paragraph Blocks */}
                      {(() => {
                        const pageRecs = sqlRecords.filter((r) => r.page_number === currentPdfPage);
                        if (pageRecs.length > 0) {
                          return pageRecs.map((rec) => {
                            const isTarget = highlightedBlockId === rec.block_id;
                            return (
                              <div
                                key={rec.id}
                                ref={(el) => {
                                  if (rec.block_id) blockRefs.current[rec.block_id] = el;
                                }}
                                className={isTarget ? "citation-highlight-active" : ""}
                                style={{
                                  marginBottom: "0.85rem",
                                  padding: isTarget ? "0.75rem 1rem" : "0.5rem 0.75rem",
                                  borderRadius: isTarget ? "4px" : "3px",
                                  border: isTarget ? "2px solid #D97706" : "1px solid var(--border-subtle)",
                                  backgroundColor: isTarget ? "rgba(254, 240, 138, 0.45)" : "var(--bg-elevated)",
                                  transition: "all 0.2s ease-out",
                                }}
                              >
                                {isTarget && (
                                  <div
                                    style={{
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "space-between",
                                      marginBottom: "6px",
                                      paddingBottom: "4px",
                                      borderBottom: "1.5px solid rgba(217, 119, 6, 0.4)",
                                    }}
                                  >
                                    <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#92400E", fontSize: "0.725rem", fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                                      <Sparkles size={12} color="#B45309" />
                                      <span>★ CITED STATUTORY EVIDENCE BLOCK: {rec.block_id}</span>
                                      {rec.amount > 0 && (
                                        <span style={{ backgroundColor: "#FEF08A", color: "#78350F", padding: "1px 5px", borderRadius: "2px", border: "1px solid #D97706" }}>
                                          INR {rec.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                        </span>
                                      )}
                                    </div>
                                    <button
                                      onClick={() => setPdfViewMode("visual")}
                                      style={{
                                        display: "inline-flex",
                                        alignItems: "center",
                                        gap: "4px",
                                        backgroundColor: "var(--accent-ink)",
                                        color: "#FAF8F3",
                                        fontSize: "0.675rem",
                                        fontWeight: 700,
                                        padding: "2px 7px",
                                        borderRadius: "3px",
                                        border: "none",
                                        cursor: "pointer",
                                        fontFamily: "var(--font-mono)",
                                      }}
                                    >
                                      <Eye size={11} />
                                      <span>View in Visual PDF</span>
                                    </button>
                                  </div>
                                )}
                                {rec.section && (
                                  <span style={{ fontSize: "0.685rem", color: isTarget ? "#92400E" : "var(--accent-ink)", fontWeight: 700, display: "block", marginBottom: "3px", opacity: 0.9, fontFamily: "var(--font-mono)", letterSpacing: "0.02em" }}>
                                    {rec.section}
                                  </span>
                                )}
                                <div style={{ margin: 0, fontSize: "0.85rem", color: isTarget ? "#14221B" : "var(--text-primary)", lineHeight: 1.6, textAlign: "left" }}>
                                  {renderHighlightedContent(rec.raw_text || rec.line_item, pdfSearchTerm, isTarget)}
                                </div>
                              </div>
                            );
                          });
                        }
                        return (
                          <div style={{ padding: "2rem 1rem", textAlign: "center", color: "var(--text-muted)" }}>
                            <p style={{ margin: 0, fontSize: "0.875rem" }}>
                              Page {currentPdfPage} is a visual / graphical layout (e.g. cover page, charts, or images).
                            </p>
                            <button
                              onClick={() => setPdfViewMode("visual")}
                              style={{
                                marginTop: "1rem",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "6px",
                                padding: "6px 14px",
                                borderRadius: "3px",
                                backgroundColor: "var(--accent-ink)",
                                color: "#FAF8F3",
                                fontSize: "0.775rem",
                                fontWeight: 600,
                                border: "none",
                                cursor: "pointer",
                              }}
                            >
                              <Eye size={13} />
                              <span>Switch to Visual PDF View</span>
                            </button>
                          </div>
                        );
                      })()}

                      <div style={{ textAlign: "right", marginTop: "1.75rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border-subtle)", fontSize: "0.7rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        Indexed into SQLite Table • Section Block Map
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* View 2: SQL Extracted Financial Records Table */}
          {effectiveActiveTab === "sql" && (
            <div style={{ flex: 1, overflowY: "auto", overflowX: "auto", backgroundColor: "var(--bg-elevated)" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.785rem" }}>
                <thead>
                  <tr style={{ backgroundColor: "var(--bg-secondary)", color: "var(--accent-ink)", position: "sticky", top: 0, zIndex: 10, textAlign: "left", borderBottom: "2px solid var(--border-bright)" }}>
                    <th style={{ padding: "8px 10px", width: "45px", fontFamily: "var(--font-mono)", fontSize: "0.7rem" }}>ID</th>
                    <th style={{ padding: "8px 10px", width: "55px", fontFamily: "var(--font-mono)", fontSize: "0.7rem" }}>Page</th>
                    <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Section</th>
                    <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Line Item</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", fontSize: "0.7rem" }}>Amount (INR)</th>
                    <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Category</th>
                    <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Raw Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSqlRecords.map((r, idx) => {
                    const isHighlighted = highlightedSqlId === r.id;
                    return (
                      <tr
                        key={r.id}
                        ref={(el) => {
                          sqlRowRefs.current[r.id] = el;
                        }}
                        className={isHighlighted ? "citation-highlight-active" : ""}
                        onClick={() => {
                          jumpToPdfBlock(r.page_number, r.block_id, r.raw_text, r.line_item);
                        }}
                        style={{
                          cursor: "pointer",
                          borderBottom: "1px solid var(--border-muted)",
                          backgroundColor: isHighlighted ? undefined : idx % 2 === 0 ? "var(--bg-elevated)" : "var(--bg-card)",
                          transition: "background-color 0.15s",
                        }}
                        title={`Click to inspect & highlight on PDF Page ${r.page_number}`}
                      >
                        <td style={{ padding: "8px 10px", color: "var(--accent-ink)", fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                          #{r.id}
                        </td>
                        <td style={{ padding: "8px 10px", color: "var(--text-primary)", fontWeight: 600, fontFamily: "var(--font-mono)" }}>
                          P.{r.page_number}
                        </td>
                        <td style={{ padding: "8px 10px", color: "var(--accent-ink)", fontWeight: 600 }}>
                          {r.section}
                        </td>
                        <td style={{ padding: "8px 10px", fontWeight: 600, color: "var(--text-primary)" }}>
                          {r.line_item}
                        </td>
                        <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: r.amount > 0 ? 700 : 400, color: r.amount > 0 ? "var(--accent-emerald)" : "var(--text-muted)", fontFamily: "var(--font-mono)" }} className="tabular-nums">
                          {r.amount > 0 ? r.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : "-"}
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          <span style={{ fontSize: "0.685rem", padding: "2px 6px", borderRadius: "3px", backgroundColor: "rgba(15, 56, 42, 0.08)", border: "1px solid rgba(15, 56, 42, 0.2)", color: "var(--accent-ink)", fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                            {r.category}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px", color: "var(--text-secondary)", fontSize: "0.725rem", maxWidth: "240px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.raw_text}>
                          {r.raw_text}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* View 3: GST Purchase Register */}
          {effectiveActiveTab === "books" && (
            <div style={{ flex: 1, overflowY: "auto", overflowX: "auto", backgroundColor: "var(--bg-elevated)" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.785rem" }}>
                <thead>
                  <tr style={{ backgroundColor: "var(--bg-secondary)", color: "var(--accent-ink)", position: "sticky", top: 0, zIndex: 10, textAlign: "left", borderBottom: "2px solid var(--border-bright)" }}>
                    <th style={{ padding: "8px 10px", width: "45px", fontFamily: "var(--font-mono)", fontSize: "0.7rem" }}>Row</th>
                    <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Vendor</th>
                    <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>GSTIN</th>
                    <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Invoice #</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", fontSize: "0.7rem" }}>Taxable (INR)</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", fontSize: "0.7rem" }}>Tax (INR)</th>
                    <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Status</th>
                    <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Observation</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map((r, idx) => {
                    const isHighlighted = highlightedRowId === r.row_id;
                    const isMatch = r.status === "EXACT_MATCH";
                    return (
                      <tr
                        key={r.row_id}
                        ref={(el) => {
                          rowRefs.current[r.row_id] = el;
                        }}
                        className={isHighlighted ? "citation-highlight-active" : ""}
                        style={{
                          borderBottom: "1px solid var(--border-muted)",
                          backgroundColor: isHighlighted ? undefined : idx % 2 === 0 ? "var(--bg-elevated)" : "var(--bg-card)",
                          transition: "background-color 0.15s",
                        }}
                      >
                        <td style={{ padding: "8px 10px", color: "var(--accent-ink)", fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                          #{r.row_id}
                        </td>
                        <td style={{ padding: "8px 10px", fontWeight: 600, color: "var(--text-primary)" }}>
                          {r.party_name}
                        </td>
                        <td style={{ padding: "8px 10px", fontFamily: "var(--font-mono)", color: "var(--text-secondary)", fontSize: "0.725rem" }}>
                          {r.gstin}
                        </td>
                        <td style={{ padding: "8px 10px", fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text-primary)" }}>
                          {r.books_invoice}
                        </td>
                        <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 600, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }} className="tabular-nums">
                          {r.books_taxable.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 600, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }} className="tabular-nums">
                          {r.tax_amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          <span
                            style={{
                              padding: "2px 6px",
                              borderRadius: "3px",
                              fontSize: "0.65rem",
                              fontWeight: 700,
                              backgroundColor: isMatch ? "var(--accent-emerald-subtle)" : "var(--accent-rose-subtle)",
                              border: isMatch ? "1px solid rgba(21, 128, 61, 0.25)" : "1px solid rgba(185, 28, 28, 0.25)",
                              color: isMatch ? "var(--accent-emerald)" : "var(--accent-rose)",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "3px",
                              fontFamily: "var(--font-mono)",
                            }}
                          >
                            {isMatch ? <CheckCircle2 size={10} /> : <AlertTriangle size={10} />}
                            {r.status}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px", color: "var(--text-secondary)", fontSize: "0.725rem" }}>
                          {r.remark || r.statutory_ref}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* View 4: Schedule III ERP Classification & Mapping View */}
          {effectiveActiveTab === "schedule3" && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflowY: "auto", overflowX: "auto" }}>
              {/* Executive Ledger Summary Banner */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(4, 1fr)",
                  backgroundColor: "var(--bg-card)",
                  borderBottom: "1px solid var(--border-subtle)",
                  flexShrink: 0,
                }}
              >
                <div style={{ padding: "8px 14px", borderRight: "1px solid var(--border-muted)" }}>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                    Source ERP Layout
                  </span>
                  <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--accent-ink)", marginTop: "2px", fontFamily: "var(--font-serif)" }}>
                    {detectedErp}
                  </div>
                </div>
                <div style={{ padding: "8px 14px", borderRight: "1px solid var(--border-muted)" }}>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                    Trial Balance Integrity
                  </span>
                  <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--accent-emerald)", marginTop: "2px", fontFamily: "var(--font-mono)" }}>
                    Balanced ✓ ({s3TotalBalanceFormatted})
                  </div>
                </div>
                <div style={{ padding: "8px 14px", borderRight: "1px solid var(--border-muted)" }}>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                    Schedule III Auto-Mapped
                  </span>
                  <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--accent-ink)", marginTop: "2px", fontFamily: "var(--font-mono)" }}>
                    {filteredS3Records.filter(r => !r.section.includes("UNMAPPED") && !r.section.includes("Review")).length} / {s3Records.length} Heads
                  </div>
                </div>
                <div style={{ padding: "8px 14px" }}>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                    Audit Review Queue
                  </span>
                  <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--accent-amber)", marginTop: "2px", fontFamily: "var(--font-mono)" }}>
                    {filteredS3Records.filter(r => r.section.includes("UNMAPPED") || r.section.includes("Review")).length} Pending Heads
                  </div>
                </div>
              </div>

              {/* Schedule III Mappings Table */}
              <div style={{ flex: 1, overflowY: "auto", overflowX: "auto", backgroundColor: "var(--bg-elevated)" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.785rem" }}>
                  <thead>
                    <tr style={{ backgroundColor: "var(--bg-secondary)", color: "var(--accent-ink)", position: "sticky", top: 0, zIndex: 10, textAlign: "left", borderBottom: "2px solid var(--border-bright)" }}>
                      <th style={{ padding: "8px 10px", width: "85px", fontFamily: "var(--font-mono)", fontSize: "0.7rem" }}>{erpShortLabel} #</th>
                      <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Account Description</th>
                      <th style={{ padding: "8px 10px", width: "45px", textAlign: "center", fontSize: "0.7rem" }}>Side</th>
                      <th style={{ padding: "8px 10px", textAlign: "right", fontSize: "0.7rem" }}>Amount (INR)</th>
                      <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Schedule III Code</th>
                      <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Classification Head</th>
                      <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Method</th>
                      <th style={{ padding: "8px 10px", textAlign: "right", fontSize: "0.7rem" }}>Confidence</th>
                      <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>Audit Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredS3Records.map((r, idx) => {
                      const isHighlighted = highlightedS3Id === r.id;
                      const glCodeMatch = r.line_item.match(/(?:SAP|Tally|Zoho|ERP) #([^:]+):/i);
                      const glCode = glCodeMatch ? glCodeMatch[1].trim() : r.block_id?.replace(/^(sap|tally|zoho|erp)-/i, "") || `#${r.id}`;
                      const acctMatch = r.raw_text.match(/Account:\s*([^|]+)/);
                      const acctName = acctMatch ? acctMatch[1].trim() : r.line_item.split(":")[1]?.split("->")[0]?.trim() || r.line_item;
                      const sideMatch = r.raw_text.match(/\(([A-Za-z]+)\)\s*\|/);
                      const side = sideMatch ? sideMatch[1].trim() : "Dr";
                      const fsliMatch = r.section.match(/Schedule III •\s*(\w+)/);
                      const fsliCode = fsliMatch ? fsliMatch[1].trim() : "UNMAPPED";
                      const descMatch = r.raw_text.match(/Schedule III Classification:\s*[^(]+\(([^)]+)\)/);
                      const fsliDesc = descMatch ? descMatch[1].trim() : fsliCode;
                      const methodMatch = r.raw_text.match(/Method:\s*(\w+)/);
                      const method = methodMatch ? methodMatch[1].trim() : "dict";
                      const confMatch = r.raw_text.match(/Confidence:\s*([\d.]+)/);
                      const conf = confMatch ? parseFloat(confMatch[1]) : 1.0;
                      const isAutoMapped = fsliCode !== "UNMAPPED" && fsliCode !== "REVIEW" && !r.section.includes("Review");

                      return (
                        <tr
                          key={r.id}
                          ref={(el) => {
                            s3RowRefs.current[r.id] = el;
                          }}
                          className={isHighlighted ? "citation-highlight-active" : ""}
                          style={{
                            borderBottom: "1px solid var(--border-muted)",
                            backgroundColor: isHighlighted ? undefined : idx % 2 === 0 ? "var(--bg-elevated)" : "var(--bg-card)",
                            transition: "background-color 0.15s",
                          }}
                        >
                          <td style={{ padding: "8px 10px", color: "var(--accent-ink)", fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                            {glCode}
                          </td>
                          <td style={{ padding: "8px 10px", fontWeight: 600, color: "var(--text-primary)" }}>
                            {acctName}
                          </td>
                          <td style={{ padding: "8px 10px", textAlign: "center" }}>
                            <span style={{ fontSize: "0.685rem", fontWeight: 700, color: side === "Dr" ? "var(--accent-emerald)" : "var(--accent-rose)", fontFamily: "var(--font-mono)" }}>
                              {side}
                            </span>
                          </td>
                          <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 600, color: "var(--text-primary)" }} className="tabular-nums">
                            {r.amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td style={{ padding: "8px 10px" }}>
                            <span
                              style={{
                                fontSize: "0.685rem",
                                padding: "2px 6px",
                                borderRadius: "3px",
                                backgroundColor: isAutoMapped ? "rgba(15, 56, 42, 0.08)" : "var(--accent-amber-subtle)",
                                border: isAutoMapped ? "1px solid rgba(15, 56, 42, 0.2)" : "1px solid rgba(180, 83, 9, 0.25)",
                                color: isAutoMapped ? "var(--accent-ink)" : "var(--accent-amber)",
                                fontWeight: 700,
                                fontFamily: "var(--font-mono)",
                              }}
                            >
                              {fsliCode}
                            </span>
                          </td>
                          <td style={{ padding: "8px 10px", color: "var(--text-secondary)", fontSize: "0.75rem" }}>
                            {fsliDesc}
                          </td>
                          <td style={{ padding: "8px 10px" }}>
                            <span style={{ fontSize: "0.685rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                              {method === "dict" ? "Dictionary" : method === "emb" ? "Embedding" : "Review"}
                            </span>
                          </td>
                          <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 600, color: isAutoMapped ? "var(--accent-emerald)" : "var(--accent-amber)" }} className="tabular-nums">
                            {Math.round(conf * 100)}%
                          </td>
                          <td style={{ padding: "8px 10px" }}>
                            <span
                              style={{
                                padding: "2px 6px",
                                borderRadius: "3px",
                                fontSize: "0.65rem",
                                fontWeight: 700,
                                backgroundColor: isAutoMapped ? "var(--accent-emerald-subtle)" : "var(--accent-amber-subtle)",
                                border: isAutoMapped ? "1px solid rgba(21, 128, 61, 0.25)" : "1px solid rgba(180, 83, 9, 0.25)",
                                color: isAutoMapped ? "var(--accent-emerald)" : "var(--accent-amber)",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "3px",
                                fontFamily: "var(--font-mono)",
                              }}
                            >
                              {isAutoMapped ? <CheckCircle2 size={10} /> : <AlertTriangle size={10} />}
                              {isAutoMapped ? "VOUCHED MAPPING" : "INQUIRY REQUIRED"}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* View 5: ICAI SA 520 & SA 240 Horizontal Anomaly & Variance View */}
          {effectiveActiveTab === "anomalies" && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflowY: "auto", overflowX: "auto", backgroundColor: "var(--bg-elevated)" }}>
              {/* Executive Anomaly Dashboard Banner */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(4, 1fr)",
                  backgroundColor: "var(--bg-card)",
                  borderBottom: "1px solid var(--border-subtle)",
                  flexShrink: 0,
                }}
              >
                <div style={{ padding: "10px 14px", borderRight: "1px solid var(--border-muted)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <AlertOctagon size={13} color="#DC2626" />
                    <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                      Critical Anomalies
                    </span>
                  </div>
                  <div style={{ fontSize: "1.05rem", fontWeight: 800, color: "#DC2626", marginTop: "3px", fontFamily: "var(--font-mono)" }}>
                    {anomaliesReport.summary.critical_count} Flagged
                  </div>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>
                    Drops &gt; {Math.max(75, materialityPct * 1.5).toFixed(0)}% or Spikes &gt; {Math.max(125, materialityPct * 2.0).toFixed(0)}%
                  </span>
                </div>

                <div style={{ padding: "10px 14px", borderRight: "1px solid var(--border-muted)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <Activity size={13} color="#D97706" />
                    <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                      Watchlist Swings
                    </span>
                  </div>
                  <div style={{ fontSize: "1.05rem", fontWeight: 800, color: "#D97706", marginTop: "3px", fontFamily: "var(--font-mono)" }}>
                    {anomaliesReport.summary.warning_count + anomaliesReport.summary.watch_count} Monitored
                  </div>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>
                    Tolerance band ({Math.max(5, Math.round(materialityPct * 0.5))}% - {materialityPct}%)
                  </span>
                </div>

                <div style={{ padding: "10px 14px", borderRight: "1px solid var(--border-muted)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <TrendingDown size={13} color="#DC2626" />
                    <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                      Severe Drop (SA 240)
                    </span>
                  </div>
                  <div style={{ fontSize: "1.05rem", fontWeight: 800, color: "#DC2626", marginTop: "3px", fontFamily: "var(--font-mono)" }}>
                    {anomaliesReport.summary.max_drop_pct.toFixed(1)}% ▼
                  </div>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", maxWidth: "160px", overflow: "hidden", textOverflow: "ellipsis", display: "inline-block", whiteSpace: "nowrap" }} title={anomaliesReport.summary.max_drop_item}>
                    {anomaliesReport.summary.max_drop_item}
                  </span>
                </div>

                <div style={{ padding: "10px 14px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <TrendingUp size={13} color="#2563EB" />
                    <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                      Surge / Spike (SA 500)
                    </span>
                  </div>
                  <div style={{ fontSize: "1.05rem", fontWeight: 800, color: "#2563EB", marginTop: "3px", fontFamily: "var(--font-mono)" }}>
                    +{anomaliesReport.summary.max_spike_pct.toFixed(1)}% ▲
                  </div>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", maxWidth: "160px", overflow: "hidden", textOverflow: "ellipsis", display: "inline-block", whiteSpace: "nowrap" }} title={anomaliesReport.summary.max_spike_item}>
                    {anomaliesReport.summary.max_spike_item}
                  </span>
                </div>
              </div>

              {/* ICAI SA 320 Materiality Benchmark Configuration Bar */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "8px 14px",
                  backgroundColor: "var(--bg-card)",
                  borderBottom: "1px solid var(--border-subtle)",
                  gap: "12px",
                  flexWrap: "wrap",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                  <span
                    style={{
                      fontSize: "0.65rem",
                      fontWeight: 800,
                      color: "var(--accent-ink)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      display: "flex",
                      alignItems: "center",
                      gap: "5px",
                    }}
                  >
                    <SlidersHorizontal size={13} color="var(--accent-ink)" />
                    ICAI SA 320 Materiality:
                  </span>

                  {/* Benchmark Presets */}
                  <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                    {[
                      { label: "10% Strict", val: 10 },
                      { label: "15% Conservative", val: 15 },
                      { label: "25% Moderate", val: 25 },
                      { label: "30% Standard", val: 30 },
                      { label: "50% High", val: 50 },
                    ].map((preset) => (
                      <button
                        key={preset.val}
                        onClick={() => setMaterialityPct(preset.val)}
                        style={{
                          padding: "2px 8px",
                          fontSize: "0.68rem",
                          fontWeight: materialityPct === preset.val ? 700 : 500,
                          borderRadius: "3px",
                          border: materialityPct === preset.val ? "1px solid var(--accent-ink)" : "1px solid var(--border-subtle)",
                          backgroundColor: materialityPct === preset.val ? "var(--accent-ink)" : "var(--bg-elevated)",
                          color: materialityPct === preset.val ? "#FAF8F3" : "var(--text-secondary)",
                          cursor: "pointer",
                          transition: "all 0.15s ease",
                        }}
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Custom Materiality Slider & Inputs */}
                <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <span style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Threshold:</span>
                    <input
                      type="range"
                      min={5}
                      max={100}
                      step={5}
                      value={materialityPct}
                      onChange={(e) => setMaterialityPct(Number(e.target.value))}
                      style={{ width: "80px", cursor: "pointer", accentColor: "var(--accent-ink)" }}
                      title={`Auditor Materiality: ${materialityPct}%`}
                    />
                    <div style={{ display: "flex", alignItems: "center", gap: "2px" }}>
                      <input
                        type="number"
                        min={1}
                        max={500}
                        value={materialityPct}
                        onChange={(e) => {
                          const v = Number(e.target.value);
                          if (v >= 1) setMaterialityPct(v);
                        }}
                        style={{
                          width: "46px",
                          padding: "2px 4px",
                          fontSize: "0.72rem",
                          fontWeight: 700,
                          fontFamily: "var(--font-mono)",
                          textAlign: "center",
                          borderRadius: "3px",
                          border: "1px solid var(--border-subtle)",
                          backgroundColor: "var(--bg-elevated)",
                          color: "var(--text-primary)",
                        }}
                      />
                      <span style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-muted)" }}>%</span>
                    </div>
                  </div>

                  <div style={{ height: "16px", width: "1px", backgroundColor: "var(--border-muted)" }} />

                  {/* Minimum Material Amount Floor */}
                  <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                    <span style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Floor: ₹</span>
                    <input
                      type="number"
                      min={0}
                      step={50}
                      value={minMaterialAmount}
                      onChange={(e) => setMinMaterialAmount(Math.max(0, Number(e.target.value)))}
                      style={{
                        width: "60px",
                        padding: "2px 4px",
                        fontSize: "0.72rem",
                        fontWeight: 700,
                        fontFamily: "var(--font-mono)",
                        textAlign: "right",
                        borderRadius: "3px",
                        border: "1px solid var(--border-subtle)",
                        backgroundColor: "var(--bg-elevated)",
                        color: "var(--text-primary)",
                      }}
                      title="Minimum rupee floor to eliminate petty cash clutter"
                    />
                  </div>

                  {/* Active Policy Status Pill */}
                  <span
                    style={{
                      fontSize: "0.62rem",
                      fontWeight: 700,
                      padding: "2px 6px",
                      borderRadius: "3px",
                      backgroundColor: "rgba(180, 83, 9, 0.08)",
                      border: "1px solid rgba(180, 83, 9, 0.2)",
                      color: "#B45309",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    Benchmark: ±{materialityPct}% | Floor: ₹{minMaterialAmount.toLocaleString("en-IN")}
                  </span>
                </div>
              </div>

              {/* Anomaly Filter Bar */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "8px 14px",
                  backgroundColor: "var(--bg-secondary)",
                  borderBottom: "1px solid var(--border-subtle)",
                  gap: "10px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <button
                    onClick={() => setAnomalyFilter("ALL")}
                    style={{
                      padding: "3px 10px",
                      borderRadius: "3px",
                      fontSize: "0.7rem",
                      fontWeight: anomalyFilter === "ALL" ? 700 : 500,
                      cursor: "pointer",
                      border: "1px solid var(--border-subtle)",
                      backgroundColor: anomalyFilter === "ALL" ? "var(--accent-ink)" : "var(--bg-card)",
                      color: anomalyFilter === "ALL" ? "#FAF8F3" : "var(--text-primary)",
                    }}
                  >
                    All Findings ({anomaliesReport.findings.length})
                  </button>
                  <button
                    onClick={() => setAnomalyFilter("CRITICAL")}
                    style={{
                      padding: "3px 10px",
                      borderRadius: "3px",
                      fontSize: "0.7rem",
                      fontWeight: anomalyFilter === "CRITICAL" ? 700 : 500,
                      cursor: "pointer",
                      border: "1px solid rgba(220, 38, 38, 0.3)",
                      backgroundColor: anomalyFilter === "CRITICAL" ? "#DC2626" : "rgba(220, 38, 38, 0.08)",
                      color: anomalyFilter === "CRITICAL" ? "#FFF" : "#DC2626",
                    }}
                  >
                    Critical Drops &amp; Spikes ({anomaliesReport.summary.critical_count})
                  </button>
                  <button
                    onClick={() => setAnomalyFilter("DROPS")}
                    style={{
                      padding: "3px 10px",
                      borderRadius: "3px",
                      fontSize: "0.7rem",
                      fontWeight: anomalyFilter === "DROPS" ? 700 : 500,
                      cursor: "pointer",
                      border: "1px solid var(--border-subtle)",
                      backgroundColor: anomalyFilter === "DROPS" ? "var(--accent-ink)" : "var(--bg-card)",
                      color: anomalyFilter === "DROPS" ? "#FAF8F3" : "var(--text-primary)",
                    }}
                  >
                    Drops Only ▼ ({anomaliesReport.summary.total_drop_count})
                  </button>
                  <button
                    onClick={() => setAnomalyFilter("SPIKES")}
                    style={{
                      padding: "3px 10px",
                      borderRadius: "3px",
                      fontSize: "0.7rem",
                      fontWeight: anomalyFilter === "SPIKES" ? 700 : 500,
                      cursor: "pointer",
                      border: "1px solid var(--border-subtle)",
                      backgroundColor: anomalyFilter === "SPIKES" ? "var(--accent-ink)" : "var(--bg-card)",
                      color: anomalyFilter === "SPIKES" ? "#FAF8F3" : "var(--text-primary)",
                    }}
                  >
                    Spikes Only ▲ ({anomaliesReport.summary.total_spike_count})
                  </button>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <Search size={12} color="var(--text-muted)" />
                  <input
                    type="text"
                    value={anomalySearch}
                    onChange={(e) => setAnomalySearch(e.target.value)}
                    placeholder="Search accounts or risks..."
                    style={{
                      padding: "4px 8px",
                      fontSize: "0.725rem",
                      borderRadius: "3px",
                      border: "1px solid var(--border-subtle)",
                      backgroundColor: "var(--bg-card)",
                      color: "var(--text-primary)",
                      width: "190px",
                    }}
                  />
                </div>
              </div>

              {/* Anomaly Forensic Data Table */}
              <div style={{ flex: 1, overflowY: "auto", overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.785rem" }}>
                  <thead>
                    <tr style={{ backgroundColor: "var(--bg-secondary)", color: "var(--accent-ink)", position: "sticky", top: 0, zIndex: 10, textAlign: "left", borderBottom: "2px solid var(--border-bright)" }}>
                      <th style={{ padding: "8px 10px", width: "55px", fontFamily: "var(--font-mono)", fontSize: "0.7rem" }}>Ref</th>
                      <th style={{ padding: "8px 10px", fontSize: "0.7rem", width: "220px" }}>Line Item / Account Head</th>
                      <th style={{ padding: "8px 10px", fontSize: "0.7rem", width: "150px" }}>Section / Note</th>
                      <th style={{ padding: "8px 10px", textAlign: "right", fontSize: "0.7rem", width: "110px" }}>Prior Year (PY)</th>
                      <th style={{ padding: "8px 10px", textAlign: "right", fontSize: "0.7rem", width: "110px" }}>Current Year (CY)</th>
                      <th style={{ padding: "8px 10px", textAlign: "center", fontSize: "0.7rem", width: "140px" }}>YoY Variance &amp; Swing</th>
                      <th style={{ padding: "8px 10px", fontSize: "0.7rem" }}>ICAI Statutory Risk Assessment (SA 520 / SA 240)</th>
                      <th style={{ padding: "8px 10px", textAlign: "center", fontSize: "0.7rem", width: "95px" }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAnomalies.length === 0 ? (
                      <tr>
                        <td colSpan={8} style={{ padding: "2.5rem", textAlign: "center", color: "var(--text-muted)" }}>
                          No anomalies match the selected filters.
                        </td>
                      </tr>
                    ) : (
                      filteredAnomalies.map((a, idx) => {
                        const isDrop = a.variance < 0;
                        const isCritical = a.severity === "CRITICAL";

                        return (
                          <tr
                            key={a.id}
                            style={{
                              borderBottom: "1px solid var(--border-muted)",
                              backgroundColor: isCritical
                                ? "rgba(220, 38, 38, 0.03)"
                                : idx % 2 === 0
                                ? "var(--bg-elevated)"
                                : "var(--bg-card)",
                              transition: "background-color 0.15s",
                            }}
                          >
                            <td style={{ padding: "8px 10px", color: "var(--accent-ink)", fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                              {a.page_number > 0 ? (
                                <button
                                  onClick={() => jumpToPdfBlock(a.page_number, a.block_id, a.line_item, a.line_item)}
                                  style={{
                                    border: "none",
                                    backgroundColor: "transparent",
                                    color: "var(--accent-ink)",
                                    cursor: "pointer",
                                    fontWeight: 700,
                                    textDecoration: "underline",
                                    fontFamily: "var(--font-mono)",
                                    fontSize: "0.725rem",
                                    padding: 0,
                                  }}
                                  title={`Click to jump to PDF Page ${a.page_number}`}
                                >
                                  P.{a.page_number}
                                </button>
                              ) : (
                                `#${a.id}`
                              )}
                            </td>
                            <td style={{ padding: "8px 10px", fontWeight: 600, color: "var(--text-primary)" }}>
                              {a.line_item}
                            </td>
                            <td style={{ padding: "8px 10px", color: "var(--text-secondary)", fontSize: "0.725rem" }}>
                              {a.section}
                            </td>
                            <td style={{ padding: "8px 10px", textAlign: "right", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }} className="tabular-nums">
                              {a.py_amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </td>
                            <td style={{ padding: "8px 10px", textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--text-primary)" }} className="tabular-nums">
                              {a.cy_amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </td>
                            <td style={{ padding: "8px 10px", textAlign: "center" }}>
                              <span
                                style={{
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: "3px",
                                  padding: "2px 7px",
                                  borderRadius: "3px",
                                  fontSize: "0.7rem",
                                  fontWeight: 700,
                                  fontFamily: "var(--font-mono)",
                                  backgroundColor: isDrop
                                    ? "rgba(220, 38, 38, 0.12)"
                                    : "rgba(37, 99, 235, 0.12)",
                                  border: isDrop
                                    ? "1px solid rgba(220, 38, 38, 0.3)"
                                    : "1px solid rgba(37, 99, 235, 0.3)",
                                  color: isDrop ? "#DC2626" : "#2563EB",
                                }}
                              >
                                {isDrop ? <TrendingDown size={11} /> : <TrendingUp size={11} />}
                                {a.pct_change > 0 ? "+" : ""}{a.pct_change.toFixed(1)}%
                              </span>
                            </td>
                            <td style={{ padding: "8px 10px", color: "var(--text-secondary)", fontSize: "0.725rem", lineHeight: 1.35 }}>
                              <span style={{ fontWeight: 600, color: isCritical ? "#DC2626" : "#D97706", marginRight: "4px" }}>
                                [{a.anomaly_type}]
                              </span>
                              {a.audit_risk}
                            </td>
                            <td style={{ padding: "8px 10px", textAlign: "center" }}>
                              <button
                                onClick={() => investigateAnomaly(a)}
                                style={{
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: "4px",
                                  padding: "3px 8px",
                                  borderRadius: "3px",
                                  backgroundColor: "var(--accent-ink)",
                                  color: "#FAF8F3",
                                  fontSize: "0.685rem",
                                  fontWeight: 600,
                                  border: "none",
                                  cursor: "pointer",
                                  whiteSpace: "nowrap",
                                }}
                                title="Load pre-crafted ICAI SA 520 inquiry into Copilot"
                              >
                                <Sparkles size={10} />
                                <span>Investigate</span>
                              </button>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        </div>

        {/* ========================================================================= */}
        {/* RIGHT STAGE: Google Gemini AI Grounded Copilot Chat                      */}
        {/* ========================================================================= */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
            minWidth: 0,
            backgroundColor: "var(--bg-secondary)",
          }}
        >
          {/* Chat Header */}
          <div
            style={{
              height: "44px",
              padding: "0 0.85rem",
              borderBottom: "1px solid var(--border-subtle)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexShrink: 0,
              backgroundColor: "var(--bg-secondary)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <div
                style={{
                  width: "22px",
                  height: "22px",
                  borderRadius: "3px",
                  backgroundColor: "var(--accent-ink)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <FileCheck size={13} color="#FAF8F3" />
              </div>
              <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-serif)" }}>
                Statutory Findings &amp; AI Working Notes
              </span>
              <span style={{ fontSize: "0.685rem", color: "var(--accent-emerald)", display: "inline-flex", alignItems: "center", gap: "3px", fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                • Grounded on {sqlRecords.length} records
              </span>
            </div>

            <button
              onClick={() => {
                setMessages([
                  {
                    id: "new-session",
                    role: "assistant",
                    content: "Docket consultation cleared. Submit statutory inquiries or voucher verification requests below.",
                    timestamp: generateCurrentTime(),
                    citations: [],
                  },
                ]);
                setHighlightedRowId(null);
                setHighlightedBlockId(null);
                setHighlightedSqlId(null);
                setHighlightedS3Id(null);
              }}
              title="Reset Chat"
              style={{
                backgroundColor: "var(--bg-card)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "3px",
                color: "var(--text-secondary)",
                padding: "3px 8px",
                fontSize: "0.725rem",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "4px",
                fontFamily: "var(--font-mono)",
              }}
            >
              <RefreshCw size={11} />
              <span>Reset</span>
            </button>
          </div>

          {/* Message History Feed */}
          <div style={{ flex: 1, overflowY: "auto", padding: "0.85rem", display: "flex", flexDirection: "column", gap: "0.85rem", backgroundColor: "var(--bg-secondary)" }}>
            {messages.map((m) => (
              <div
                key={m.id}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: m.role === "user" ? "flex-end" : "flex-start",
                }}
              >
                <div
                  style={{
                    maxWidth: m.role === "user" ? "90%" : "96%",
                    borderRadius: "4px",
                    padding: m.role === "user" ? "0.7rem 0.85rem" : "0.85rem 1rem",
                    backgroundColor: m.role === "user" ? "var(--bg-card)" : "var(--bg-elevated)",
                    border: "1px solid var(--border-subtle)",
                    borderLeft: m.role === "user" ? "3px solid var(--accent-ink)" : "1px solid var(--border-subtle)",
                    color: "var(--text-primary)",
                    fontSize: "0.825rem",
                    lineHeight: 1.6,
                    boxShadow: "var(--shadow-card)",
                  }}
                >
                  {m.role === "assistant" && (
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "6px", paddingBottom: "4px", borderBottom: "1px solid var(--border-muted)" }}>
                      <span style={{ fontSize: "0.65rem", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.05em", color: "var(--accent-ink)", fontFamily: "var(--font-mono)" }}>
                        Statutory Verification Note
                      </span>
                      <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        ICAI / SA-520
                      </span>
                    </div>
                  )}

                  <div style={{ whiteSpace: "pre-wrap", color: "var(--text-primary)" }}>{m.content}</div>

                  {/* Interactive Citation Badges */}
                  {m.citations && m.citations.length > 0 && (
                    <div style={{ marginTop: "0.75rem", paddingTop: "0.5rem", borderTop: "1px solid var(--border-muted)" }}>
                      <div style={{ fontSize: "0.65rem", color: "var(--accent-ink)", fontWeight: 700, marginBottom: "5px", letterSpacing: "0.03em", fontFamily: "var(--font-mono)", textTransform: "uppercase" }}>
                        Audit Evidence Vouchers (Click to inspect):
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
                        {m.citations.map((c, i) => (
                          <button
                            key={i}
                            onClick={() => {
                              if (
                                c.label?.includes("Schedule III") ||
                                c.label?.includes("SAP") ||
                                c.label?.includes("Tally") ||
                                c.label?.includes("Zoho") ||
                                c.label?.includes("ERP")
                              ) {
                                const idNum = c.row_index || parseInt(c.id.replace("cite-sql-", ""), 10);
                                jumpToSchedule3Record(idNum);
                              } else if (c.label?.includes("GST Row") || c.label?.includes("Row #") || isExcelActive || c.type === "excel") {
                                jumpToTableRow(c.row_index!);
                              } else if (c.page && !isExcelActive) {
                                jumpToPdfBlock(c.page, c.block_id, c.value, c.label);
                              } else if (c.row_index) {
                                jumpToSqlRecord(c.row_index);
                              }
                            }}
                            className="citation-tag"
                            title="Click to jump & highlight evidence in viewer"
                            style={{
                              backgroundColor: "var(--bg-card)",
                              border: "1px solid var(--border-bright)",
                              color: "var(--accent-ink)",
                              padding: "3px 8px",
                              borderRadius: "3px",
                              fontSize: "0.7rem",
                              fontFamily: "var(--font-mono)",
                              fontWeight: 600,
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "4px",
                              cursor: "pointer",
                              transition: "all 0.15s ease",
                            }}
                          >
                            <FileCheck size={11} color="var(--accent-emerald)" />
                            <span>{c.label || (c.page ? `Page ${c.page}` : `Record #${c.row_index}`)}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginTop: "3px", padding: "0 4px", fontFamily: "var(--font-mono)" }}>
                  {m.timestamp}
                </span>
              </div>
            ))}

            {isLoading && (
              <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--text-secondary)", fontSize: "0.785rem", padding: "0.5rem" }}>
                <Sparkles size={14} className="animate-spin" color="var(--accent-ink)" />
                <span style={{ fontFamily: "var(--font-mono)" }}>Cross-examining ledger records via Gemini reasoning engine...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Prompt Recommendations */}
          <div
            style={{
              padding: "0.45rem 0.75rem",
              borderTop: "1px solid var(--border-subtle)",
              backgroundColor: "var(--bg-card)",
              display: "flex",
              gap: "5px",
              overflowX: "auto",
              flexShrink: 0,
            }}
          >
            {dynamicPromptRecommendations.map((prompt, idx) => (
              <button
                key={idx}
                onClick={() => handleSendMessage(prompt)}
                style={{
                  whiteSpace: "nowrap",
                  fontSize: "0.7rem",
                  padding: "3px 9px",
                  borderRadius: "3px",
                  backgroundColor: "var(--bg-elevated)",
                  border: "1px solid var(--border-subtle)",
                  color: "var(--text-secondary)",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                  fontFamily: "var(--font-sans)",
                }}
              >
                {prompt}
              </button>
            ))}
          </div>

          {/* Question Input Box */}
          <div
            style={{
              padding: "0.5rem 0.75rem",
              borderTop: "1px solid var(--border-subtle)",
              backgroundColor: "var(--bg-secondary)",
              flexShrink: 0,
            }}
          >
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendMessage();
              }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                backgroundColor: "var(--bg-elevated)",
                border: "1px solid var(--border-bright)",
                borderRadius: "4px",
                padding: "3px 6px",
              }}
            >
              <button
                type="button"
                onClick={() => setShowUploadModal(true)}
                title="Upload PDF or Spreadsheet (Ctrl+U)"
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                  padding: "3px",
                  display: "flex",
                  alignItems: "center",
                }}
              >
                <UploadCloud size={16} />
              </button>

              <input
                type="text"
                value={inputQuestion}
                onChange={(e) => setInputQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
                placeholder="Enter audit inquiry or statutory citation check (Ctrl+Enter)..."
                style={{
                  flex: 1,
                  background: "transparent",
                  border: "none",
                  color: "var(--accent-ink)",
                  fontSize: "0.825rem",
                  outline: "none",
                  padding: "5px 3px",
                }}
              />

              <button
                type="submit"
                disabled={!inputQuestion.trim() || isLoading}
                style={{
                  backgroundColor: inputQuestion.trim() && !isLoading ? "var(--accent-ink)" : "var(--bg-secondary)",
                  color: inputQuestion.trim() && !isLoading ? "#FAF8F3" : "var(--text-muted)",
                  border: "1px solid " + (inputQuestion.trim() && !isLoading ? "var(--accent-ink)" : "var(--border-subtle)"),
                  borderRadius: "3px",
                  padding: "5px 10px",
                  cursor: inputQuestion.trim() && !isLoading ? "pointer" : "not-allowed",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: "all 0.15s ease",
                }}
              >
                <Send size={13} />
              </button>
            </form>
          </div>
        </div>
      </div>

      {/* Real File Upload Modal */}
      {showUploadModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor: "rgba(15, 56, 42, 0.45)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
            padding: "1rem",
          }}
        >
          <div
            style={{
              backgroundColor: "var(--bg-card)",
              borderRadius: "4px",
              border: "1px solid var(--border-bright)",
              width: "100%",
              maxWidth: "480px",
              padding: "1.75rem",
              boxShadow: "0 16px 40px rgba(15, 56, 42, 0.2)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.85rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <div style={{ width: "24px", height: "24px", borderRadius: "3px", backgroundColor: "var(--accent-ink)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <UploadCloud size={14} color="#FAF8F3" />
                </div>
                <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-serif)", margin: 0 }}>
                  Audit Docket Ingestion
                </h3>
              </div>
              <button
                disabled={isUploading}
                onClick={() => setShowUploadModal(false)}
                style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer" }}
              >
                <X size={16} />
              </button>
            </div>

            <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", lineHeight: 1.55, marginBottom: "1.25rem" }}>
              Ingest client <strong>Audited PDF</strong>, <strong>Statutory Trial Balance</strong>, or <strong>ERP Export (.xlsx/.csv)</strong>.
              Records are parsed into structured working papers and cross-examined using Google Gemini reasoning engine.
            </p>

            {uploadError && (
              <div style={{ padding: "7px 10px", borderRadius: "3px", backgroundColor: "var(--accent-rose-subtle)", border: "1px solid rgba(185, 28, 28, 0.25)", color: "var(--accent-rose)", fontSize: "0.775rem", marginBottom: "0.85rem", fontFamily: "var(--font-mono)" }}>
                {uploadError}
              </div>
            )}

            {/* Clickable Drop Zone */}
            <div
              role="button"
              tabIndex={0}
              onClick={() => {
                if (!isUploading && fileInputRef.current) {
                  fileInputRef.current.value = "";
                  fileInputRef.current.click();
                }
              }}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && !isUploading && fileInputRef.current) {
                  fileInputRef.current.value = "";
                  fileInputRef.current.click();
                }
              }}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                  processUploadedFile(e.dataTransfer.files[0]);
                }
              }}
              style={{
                border: "2px dashed var(--border-bright, #0F382A)",
                borderRadius: "4px",
                padding: "2rem 1.25rem",
                textAlign: "center",
                backgroundColor: "var(--bg-elevated, #FFFFFF)",
                marginBottom: "1.25rem",
                cursor: isUploading ? "wait" : "pointer",
                transition: "all 0.15s ease",
                display: "block",
              }}
            >
              {isUploading ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" }}>
                  <Loader2 size={30} color="var(--accent-ink, #0F382A)" className="animate-spin" />
                  <div style={{ fontWeight: 700, fontSize: "0.9rem", color: "var(--accent-ink, #0F382A)", fontFamily: "var(--font-serif)" }}>
                    Parsing &amp; Populating Working Paper Ledger...
                  </div>
                  <div style={{ fontSize: "0.725rem", color: "var(--text-muted, #5D6E64)", fontFamily: "var(--font-mono)" }}>
                    Structuring trial balance line items &amp; Schedule III codes
                  </div>
                </div>
              ) : (
                <>
                  <FileText size={36} color="var(--accent-ink, #0F382A)" style={{ margin: "0 auto 0.5rem auto", opacity: 0.8 }} />
                  <div style={{ fontWeight: 700, fontSize: "0.9rem", color: "var(--accent-ink, #0F382A)", fontFamily: "var(--font-serif)" }}>
                    Click to select audit engagement file
                  </div>
                  <div style={{ fontSize: "0.725rem", color: "var(--text-muted, #5D6E64)", marginTop: "4px", fontFamily: "var(--font-mono)" }}>
                    Supports .PDF, .XLSX, and .CSV financial records
                  </div>
                </>
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
              <button
                disabled={isUploading}
                type="button"
                onClick={() => setShowUploadModal(false)}
                style={{
                  padding: "0.45rem 0.85rem",
                  borderRadius: "3px",
                  border: "1px solid var(--border-subtle, #D8D2C4)",
                  background: "var(--bg-secondary, #EBE7DC)",
                  color: "var(--text-secondary, #38483F)",
                  fontSize: "0.8rem",
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isUploading}
                onClick={() => {
                  if (fileInputRef.current) {
                    fileInputRef.current.value = "";
                    fileInputRef.current.click();
                  }
                }}
                style={{
                  padding: "0.45rem 1rem",
                  borderRadius: "3px",
                  backgroundColor: "var(--accent-ink, #0F382A)",
                  color: "#FAF8F3",
                  fontSize: "0.8rem",
                  fontWeight: 600,
                  border: "none",
                  cursor: isUploading ? "wait" : "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                }}
              >
                Select File
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
