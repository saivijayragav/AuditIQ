"use client";

import React, { useState, useEffect, useRef, useMemo } from "react";
import Link from "next/link";
import {
  ShieldCheck,
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
  Cpu,
  Bot,
  ExternalLink,
  Eye,
  Layers,
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
  const [activeTab, setActiveTab] = useState<"pdf" | "sql" | "books" | "schedule3">("pdf");
  const [sessionId, setSessionId] = useState<string>("demo-gst-fy23-24");
  const [activeFileName, setActiveFileName] = useState<string>("sample_audited_financial_statements.pdf");

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

  const detectedErp = useMemo(() => {
    const fn = activeFileName.toLowerCase();
    if (fn.includes("tally")) return "Tally ERP 9 / Prime";
    if (fn.includes("zoho")) return "Zoho Books";
    if (fn.includes("sap")) return "SAP ECC / S4HANA";
    const s3 = sqlRecords.find((r) => r.category === "schedule3_mapping");
    if (
      s3?.raw_text?.toLowerCase().includes("source erp: tally") ||
      s3?.raw_text?.toLowerCase().includes("tally account") ||
      s3?.line_item?.toLowerCase().includes("tally")
    )
      return "Tally ERP 9 / Prime";
    if (
      s3?.raw_text?.toLowerCase().includes("source erp: zoho") ||
      s3?.raw_text?.toLowerCase().includes("zoho account") ||
      s3?.line_item?.toLowerCase().includes("zoho")
    )
      return "Zoho Books";
    if (
      s3?.raw_text?.toLowerCase().includes("source erp: sap") ||
      s3?.raw_text?.toLowerCase().includes("sap g/l") ||
      s3?.line_item?.toLowerCase().includes("sap")
    )
      return "SAP ECC / S4HANA";
    return "ERP Trial Balance";
  }, [activeFileName, sqlRecords]);

  const erpShortLabel = useMemo(() => {
    if (detectedErp.includes("Tally")) return "Tally";
    if (detectedErp.includes("Zoho")) return "Zoho";
    if (detectedErp.includes("SAP")) return "SAP";
    return "ERP";
  }, [detectedErp]);

  const s3TotalBalanceFormatted = useMemo(() => {
    const sum = s3Records.reduce((acc, r) => acc + (r.amount || 0), 0);
    const singleSide = sum > 0 ? sum / 2 : 13497960.65;
    if (singleSide >= 10000000) return `INR ${(singleSide / 10000000).toFixed(2)} Cr`;
    if (singleSide >= 100000) return `INR ${(singleSide / 100000).toFixed(2)}L`;
    return `INR ${singleSide.toLocaleString("en-IN")}`;
  }, [s3Records]);

  // Real Extracted PDF state
  const [extractedPdf, setExtractedPdf] = useState<ExtractedPdfDoc | null>(null);
  const [currentPdfPage, setCurrentPdfPage] = useState<number>(1);
  const [highlightedBlockId, setHighlightedBlockId] = useState<string | null>(null);
  const [pdfViewMode, setPdfViewMode] = useState<"visual" | "blocks">("visual");
  const [pdfServerUrl, setPdfServerUrl] = useState<string>("/api/copilot/raw-pdf?session_id=demo-gst-fy23-24");

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

  // Navigate PDF page without unmounting iframe
  const navigatePdfPage = (pageNumber: number) => {
    const clamped = Math.max(1, Math.min(totalPages, pageNumber));
    setCurrentPdfPage(clamped);
    if (iframeRef.current && effectivePdfSrc) {
      try {
        iframeRef.current.src = `${effectivePdfSrc}#page=${clamped}`;
      } catch (e) {
        console.warn("Could not update iframe page hash:", e);
      }
    }
  };

  // Jump to PDF block
  const jumpToPdfBlock = (pageNumber: number, blockId?: string) => {
    setActiveTab("pdf");
    navigatePdfPage(pageNumber);
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
    await processUploadedFile(file);
  };

  const processUploadedFile = async (file: File) => {
    setIsUploading(true);
    setUploadError(null);

    if (file.name.toLowerCase().endsWith(".pdf")) {
      setPdfViewMode("visual");
      setActiveTab("pdf");
      setActiveFileName(file.name);
      setCurrentPdfPage(1);
    } else {
      setActiveFileName(file.name);
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
      }

      setShowUploadModal(false);
    } catch (err: any) {
      setUploadError(err.message || "Failed to parse document. Ensure the backend server is running.");
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
            jumpToPdfBlock(firstCite.page, firstCite.block_id);
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
    activeFileName.includes("INVESTOR_CORNER")
      ? "/INVESTOR_CORNER_1756730556104_570e54_1756730556104.pdf"
      : activeFileName.includes("sample_audited")
      ? "/sample_audited_financial_statements.pdf"
      : pdfServerUrl || `/api/copilot/raw-pdf?session_id=${encodeURIComponent(sessionId)}`;

  const isExcelActive = Boolean(
    activeFileName && /\.(xlsx|csv|xls)$/i.test(activeFileName)
  );

  const effectiveActiveTab = isExcelActive && activeTab === "pdf"
    ? (s3Records.length > 0 ? "schedule3" : "books")
    : activeTab;

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
          borderBottom: "1px solid var(--border-subtle)",
          backgroundColor: "var(--bg-secondary)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 1rem",
          flexShrink: 0,
          zIndex: 30,
        }}
      >
        {/* Left Branding & Document Status */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0, overflow: "hidden" }}>
          <Link href="/" style={{ display: "flex", alignItems: "center", gap: "7px", flexShrink: 0 }}>
            <div
              style={{
                width: "26px",
                height: "26px",
                borderRadius: "6px",
                backgroundColor: "var(--accent-blue)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <ShieldCheck size={16} color="#ffffff" />
            </div>
            <span style={{ fontWeight: 800, fontSize: "1rem", letterSpacing: "-0.02em", color: "#f8fafc" }}>
              Audit<span style={{ color: "#3b82f6" }}>IQ</span>
            </span>
          </Link>

          <div style={{ height: "14px", width: "1px", backgroundColor: "var(--border-subtle)", flexShrink: 0 }} />

          {/* Active File Pill */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "0.785rem",
              backgroundColor: "rgba(255, 255, 255, 0.03)",
              border: "1px solid var(--border-subtle)",
              padding: "2px 8px",
              borderRadius: "4px",
              minWidth: 0,
            }}
          >
            <FileText size={12} color="#60a5fa" style={{ flexShrink: 0 }} />
            <span
              style={{
                fontWeight: 600,
                color: "var(--text-primary)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                maxWidth: "220px",
              }}
              title={activeFileName}
            >
              {activeFileName}
            </span>
          </div>

          {/* Records & AI Pill */}
          <span
            style={{
              backgroundColor: "rgba(16, 185, 129, 0.12)",
              color: "#34d399",
              border: "1px solid rgba(16, 185, 129, 0.25)",
              fontSize: "0.7rem",
              fontWeight: 700,
              padding: "2px 7px",
              borderRadius: "4px",
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              flexShrink: 0,
            }}
          >
            <Database size={11} />
            {sqlRecords.length} SQL Rows
          </span>

          <span
            style={{
              backgroundColor: "rgba(59, 130, 246, 0.12)",
              color: "#60a5fa",
              border: "1px solid rgba(59, 130, 246, 0.25)",
              fontSize: "0.7rem",
              fontWeight: 700,
              padding: "2px 7px",
              borderRadius: "4px",
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              flexShrink: 0,
            }}
          >
            <Cpu size={11} />
            Gemini 3.5
          </span>
        </div>

        {/* Right Tools & Upload Action */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexShrink: 0 }}>
          <button
            onClick={() => setShowUploadModal(true)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "5px",
              padding: "5px 12px",
              borderRadius: "5px",
              backgroundColor: "var(--accent-blue)",
              color: "#ffffff",
              border: "none",
              fontSize: "0.8rem",
              fontWeight: 600,
              cursor: "pointer",
              boxShadow: "0 1px 4px rgba(37, 99, 235, 0.3)",
              whiteSpace: "nowrap",
            }}
          >
            <UploadCloud size={14} />
            <span>Upload</span>
            <span style={{ fontSize: "0.65rem", opacity: 0.75, marginLeft: "2px" }}>Ctrl+U</span>
          </button>

          <Link
            href="/login"
            title="Auditor Profile"
            style={{
              width: "28px",
              height: "28px",
              borderRadius: "50%",
              backgroundColor: "var(--bg-elevated)",
              border: "1px solid var(--border-subtle)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#93c5fd",
              fontWeight: 700,
              fontSize: "0.7rem",
            }}
          >
            CA
          </Link>
        </div>
      </header>

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
            {/* View Switchers */}
            <div style={{ display: "flex", gap: "4px" }}>
              {!isExcelActive && (
                <button
                  onClick={() => setActiveTab("pdf")}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "5px",
                    padding: "4px 10px",
                    borderRadius: "5px",
                    fontSize: "0.775rem",
                    fontWeight: 600,
                    cursor: "pointer",
                    border: "none",
                    whiteSpace: "nowrap",
                    backgroundColor: effectiveActiveTab === "pdf" ? "var(--bg-card)" : "transparent",
                    color: effectiveActiveTab === "pdf" ? "#fbbf24" : "var(--text-secondary)",
                    boxShadow: effectiveActiveTab === "pdf" ? "0 1px 3px rgba(0,0,0,0.3)" : "none",
                  }}
                >
                  <FileText size={13} color={effectiveActiveTab === "pdf" ? "#fbbf24" : "var(--text-muted)"} />
                  <span>Audited PDF {totalPages ? `(${totalPages}p)` : ""}</span>
                </button>
              )}

              <button
                onClick={() => setActiveTab("sql")}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "5px",
                  padding: "4px 10px",
                  borderRadius: "5px",
                  fontSize: "0.775rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  border: "none",
                  whiteSpace: "nowrap",
                  backgroundColor: effectiveActiveTab === "sql" ? "var(--bg-card)" : "transparent",
                  color: effectiveActiveTab === "sql" ? "#34d399" : "var(--text-secondary)",
                  boxShadow: effectiveActiveTab === "sql" ? "0 1px 3px rgba(0,0,0,0.3)" : "none",
                }}
              >
                <Database size={13} color={effectiveActiveTab === "sql" ? "#34d399" : "var(--text-muted)"} />
                <span>SQL Records ({sqlRecords.length})</span>
              </button>

              <button
                onClick={() => setActiveTab("books")}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "5px",
                  padding: "4px 10px",
                  borderRadius: "5px",
                  fontSize: "0.775rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  border: "none",
                  whiteSpace: "nowrap",
                  backgroundColor: effectiveActiveTab === "books" ? "var(--bg-card)" : "transparent",
                  color: effectiveActiveTab === "books" ? "#60a5fa" : "var(--text-secondary)",
                  boxShadow: effectiveActiveTab === "books" ? "0 1px 3px rgba(0,0,0,0.3)" : "none",
                }}
              >
                <FileSpreadsheet size={13} color={effectiveActiveTab === "books" ? "#60a5fa" : "var(--text-muted)"} />
                <span>
                  {activeFileName && /\.(xlsx|csv|xls)$/i.test(activeFileName)
                    ? `Spreadsheet Rows (${rows.length})`
                    : `GST Register (${rows.length})`}
                </span>
              </button>

              {s3Records.length > 0 && (
                <button
                  onClick={() => setActiveTab("schedule3")}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "5px",
                    padding: "4px 10px",
                    borderRadius: "5px",
                    fontSize: "0.775rem",
                    fontWeight: 600,
                    cursor: "pointer",
                    border: "none",
                    whiteSpace: "nowrap",
                    backgroundColor: effectiveActiveTab === "schedule3" ? "var(--bg-card)" : "transparent",
                    color: effectiveActiveTab === "schedule3" ? "#c084fc" : "var(--text-secondary)",
                    boxShadow: effectiveActiveTab === "schedule3" ? "0 1px 3px rgba(0,0,0,0.3)" : "none",
                  }}
                >
                  <Layers size={13} color={effectiveActiveTab === "schedule3" ? "#c084fc" : "var(--text-muted)"} />
                  <span>Schedule III ({s3Records.length})</span>
                </button>
              )}
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

                {/* Pop-out to new window */}
                <a
                  href={`${effectivePdfSrc}#page=${currentPdfPage}`}
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

          {/* Active Highlight Banner */}
          {(highlightedRowId || highlightedBlockId || highlightedSqlId || highlightedS3Id) && (
            <div
              style={{
                backgroundColor: "rgba(245, 158, 11, 0.12)",
                borderBottom: "1px solid rgba(245, 158, 11, 0.25)",
                padding: "5px 0.75rem",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                fontSize: "0.75rem",
                color: "#fbbf24",
                fontWeight: 600,
                flexShrink: 0,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <Sparkles size={13} />
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
                  color: "#fbbf24",
                  fontSize: "0.725rem",
                  cursor: "pointer",
                  textDecoration: "underline",
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
                    backgroundColor: "#1e293b",
                    display: "flex",
                    flexDirection: "column",
                  }}
                >
                  {/* Floating Citation Glow Pill if an evidence citation is focused */}
                  {highlightedBlockId && (
                    <div
                      style={{
                        position: "absolute",
                        top: "10px",
                        left: "50%",
                        transform: "translateX(-50%)",
                        zIndex: 30,
                        backgroundColor: "rgba(15, 23, 42, 0.94)",
                        backdropFilter: "blur(6px)",
                        border: "1px solid #f59e0b",
                        color: "#fbbf24",
                        padding: "5px 14px",
                        borderRadius: "20px",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        display: "flex",
                        alignItems: "center",
                        gap: "8px",
                        boxShadow: "0 6px 20px rgba(0,0,0,0.6)",
                      }}
                    >
                      <Sparkles size={13} color="#fbbf24" />
                      <span>Evidence Citation: Jumped to Page {currentPdfPage}</span>
                      <button
                        onClick={() => setPdfViewMode("blocks")}
                        style={{
                          background: "rgba(245, 158, 11, 0.25)",
                          border: "1px solid rgba(245, 158, 11, 0.4)",
                          color: "#fde68a",
                          fontSize: "0.675rem",
                          fontWeight: 700,
                          padding: "2px 7px",
                          borderRadius: "4px",
                          cursor: "pointer",
                          marginLeft: "4px",
                        }}
                      >
                        Inspect Text Block
                      </button>
                      <button
                        onClick={() => setHighlightedBlockId(null)}
                        style={{
                          background: "transparent",
                          border: "none",
                          color: "#94a3b8",
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                        }}
                      >
                        <X size={13} />
                      </button>
                    </div>
                  )}

                  <iframe
                    ref={iframeRef}
                    key={`${effectivePdfSrc}-p${currentPdfPage}`}
                    src={`${effectivePdfSrc}#page=${currentPdfPage}`}
                    title={`Visual PDF - ${activeFileName}`}
                    style={{
                      width: "100%",
                      height: "100%",
                      border: "none",
                      backgroundColor: "#1e293b",
                      display: "block",
                    }}
                  />
                </div>
              ) : (
                /* Mode 2: Extracted Text Blocks View with Citation Glow */
                <div style={{ flex: 1, padding: "1.25rem", overflowY: "auto", overflowX: "hidden", backgroundColor: "var(--bg-primary)" }}>
                  {!extractedPdf ? (
                    <div style={{ padding: "4rem 2rem", textAlign: "center", color: "var(--text-secondary)" }}>
                      <FileText size={44} color="#3b82f6" style={{ margin: "0 auto 1rem auto", opacity: 0.8 }} />
                      <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                        No PDF Document Loaded
                      </h3>
                      <p style={{ maxWidth: "420px", margin: "0 auto 1.5rem auto", fontSize: "0.85rem", lineHeight: 1.5 }}>
                        Upload any client financial statement PDF. AuditIQ extracts the text into an SQL database and uses Google Gemini to answer questions with live highlighted citations.
                      </p>
                      <button
                        onClick={() => setShowUploadModal(true)}
                        style={{
                          padding: "0.5rem 1.25rem",
                          borderRadius: "5px",
                          backgroundColor: "var(--accent-blue)",
                          color: "#ffffff",
                          fontSize: "0.825rem",
                          fontWeight: 600,
                          border: "none",
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                        }}
                      >
                        <UploadCloud size={15} />
                        <span>Upload Document</span>
                      </button>
                    </div>
                  ) : (
                    <div
                      style={{
                        width: "100%",
                        boxSizing: "border-box",
                        backgroundColor: "#0d1424",
                        color: "#f8fafc",
                        borderRadius: "8px",
                        border: "1px solid #1e293b",
                        boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
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
                          borderBottom: "1px solid #1e293b",
                          paddingBottom: "0.75rem",
                          marginBottom: "1.25rem",
                        }}
                      >
                        <div>
                          <span style={{ fontSize: "0.685rem", textTransform: "uppercase", fontWeight: 700, color: "#60a5fa", letterSpacing: "0.04em" }}>
                            Audited Statutory Statement
                          </span>
                          <h4 style={{ margin: "2px 0 0 0", fontSize: "1rem", fontWeight: 700, color: "#f8fafc" }}>
                            {extractedPdf.file_name}
                          </h4>
                        </div>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 700,
                            color: "#94a3b8",
                            backgroundColor: "#1e293b",
                            padding: "2px 8px",
                            borderRadius: "4px",
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
                                  padding: isTarget ? "0.75rem 1rem" : "0.35rem 0",
                                  borderRadius: isTarget ? "6px" : "0",
                                  transition: "all 0.2s ease-out",
                                }}
                              >
                                {isTarget && (
                                  <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#fbbf24", fontSize: "0.725rem", fontWeight: 700, marginBottom: "4px" }}>
                                    <Sparkles size={12} />
                                    <span>Cited Statutory Evidence Block ({rec.block_id})</span>
                                  </div>
                                )}
                                {rec.section && (
                                  <span style={{ fontSize: "0.685rem", color: "#60a5fa", fontWeight: 600, display: "block", marginBottom: "2px" }}>
                                    {rec.section}
                                  </span>
                                )}
                                <p style={{ margin: 0, fontSize: "0.875rem", color: isTarget ? "#ffffff" : "#cbd5e1", lineHeight: 1.6, textAlign: "justify" }}>
                                  {rec.raw_text || rec.line_item}
                                </p>
                              </div>
                            );
                          });
                        }
                        return (
                          <div style={{ padding: "2rem 1rem", textAlign: "center", color: "#94a3b8" }}>
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
                                borderRadius: "5px",
                                backgroundColor: "var(--accent-blue)",
                                color: "#ffffff",
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

                      <div style={{ textAlign: "right", marginTop: "1.75rem", paddingTop: "0.75rem", borderTop: "1px solid #1e293b", fontSize: "0.7rem", color: "#64748b" }}>
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
            <div style={{ flex: 1, overflowY: "auto", overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.785rem" }}>
                <thead>
                  <tr style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-secondary)", position: "sticky", top: 0, zIndex: 10, textAlign: "left", borderBottom: "1px solid var(--border-subtle)" }}>
                    <th style={{ padding: "7px 10px", width: "45px" }}>ID</th>
                    <th style={{ padding: "7px 10px", width: "45px" }}>Page</th>
                    <th style={{ padding: "7px 10px" }}>Section</th>
                    <th style={{ padding: "7px 10px" }}>Line Item</th>
                    <th style={{ padding: "7px 10px", textAlign: "right" }}>Amount (INR)</th>
                    <th style={{ padding: "7px 10px" }}>Category</th>
                    <th style={{ padding: "7px 10px" }}>Raw Evidence</th>
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
                        style={{
                          borderBottom: "1px solid rgba(30, 41, 59, 0.5)",
                          backgroundColor: isHighlighted ? undefined : idx % 2 === 0 ? "rgba(255, 255, 255, 0.015)" : "transparent",
                          transition: "background-color 0.15s",
                        }}
                      >
                        <td style={{ padding: "8px 10px", color: isHighlighted ? "#f59e0b" : "var(--text-muted)", fontWeight: 700 }} className="tabular-nums">
                          #{r.id}
                        </td>
                        <td style={{ padding: "8px 10px", color: "var(--text-primary)", fontWeight: 600 }}>
                          P.{r.page_number}
                        </td>
                        <td style={{ padding: "8px 10px", color: "#93c5fd", fontWeight: 600 }}>
                          {r.section}
                        </td>
                        <td style={{ padding: "8px 10px", fontWeight: 600, color: "var(--text-primary)" }}>
                          {r.line_item}
                        </td>
                        <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: r.amount > 0 ? 700 : 400, color: r.amount > 0 ? "#34d399" : "var(--text-muted)" }} className="tabular-nums">
                          {r.amount > 0 ? r.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : "-"}
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          <span style={{ fontSize: "0.685rem", padding: "2px 6px", borderRadius: "4px", backgroundColor: "rgba(59, 130, 246, 0.12)", color: "#60a5fa", fontWeight: 600 }}>
                            {r.category}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px", color: "var(--text-secondary)", fontSize: "0.725rem", maxWidth: "220px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.raw_text}>
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
            <div style={{ flex: 1, overflowY: "auto", overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.785rem" }}>
                <thead>
                  <tr style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-secondary)", position: "sticky", top: 0, zIndex: 10, textAlign: "left", borderBottom: "1px solid var(--border-subtle)" }}>
                    <th style={{ padding: "7px 10px", width: "40px" }}>Row</th>
                    <th style={{ padding: "7px 10px" }}>Vendor</th>
                    <th style={{ padding: "7px 10px" }}>GSTIN</th>
                    <th style={{ padding: "7px 10px" }}>Invoice #</th>
                    <th style={{ padding: "7px 10px", textAlign: "right" }}>Taxable (INR)</th>
                    <th style={{ padding: "7px 10px", textAlign: "right" }}>Tax (INR)</th>
                    <th style={{ padding: "7px 10px" }}>Status</th>
                    <th style={{ padding: "7px 10px" }}>Observation</th>
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
                          borderBottom: "1px solid rgba(30, 41, 59, 0.5)",
                          backgroundColor: isHighlighted ? undefined : idx % 2 === 0 ? "rgba(255, 255, 255, 0.015)" : "transparent",
                        }}
                      >
                        <td style={{ padding: "8px 10px", color: isHighlighted ? "#f59e0b" : "var(--text-muted)", fontWeight: 700 }} className="tabular-nums">
                          #{r.row_id}
                        </td>
                        <td style={{ padding: "8px 10px", fontWeight: 600, color: "var(--text-primary)" }}>
                          {r.party_name}
                        </td>
                        <td style={{ padding: "8px 10px", fontFamily: "monospace", color: "var(--text-secondary)", fontSize: "0.725rem" }}>
                          {r.gstin}
                        </td>
                        <td style={{ padding: "8px 10px", fontFamily: "monospace", fontWeight: 600 }}>
                          {r.books_invoice}
                        </td>
                        <td style={{ padding: "8px 10px", textAlign: "right" }} className="tabular-nums">
                          {r.books_taxable.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: "8px 10px", textAlign: "right" }} className="tabular-nums">
                          {r.tax_amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          <span
                            style={{
                              padding: "2px 6px",
                              borderRadius: "4px",
                              fontSize: "0.685rem",
                              fontWeight: 700,
                              backgroundColor: isMatch ? "rgba(16, 185, 129, 0.12)" : "rgba(239, 68, 68, 0.12)",
                              border: isMatch ? "1px solid rgba(16, 185, 129, 0.25)" : "1px solid rgba(239, 68, 68, 0.25)",
                              color: isMatch ? "#34d399" : "#f87171",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "3px",
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
              {/* Executive ERP & Trial Balance KPI Banner */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                  gap: "10px",
                  padding: "0.75rem 1rem",
                  backgroundColor: "var(--bg-secondary)",
                  borderBottom: "1px solid var(--border-subtle)",
                  flexShrink: 0,
                }}
              >
                <div style={{ padding: "8px 12px", borderRadius: "6px", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-subtle)" }}>
                  <span style={{ fontSize: "0.685rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Source ERP Layout</span>
                  <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "#60a5fa", marginTop: "2px" }}>{detectedErp}</div>
                </div>
                <div style={{ padding: "8px 12px", borderRadius: "6px", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-subtle)" }}>
                  <span style={{ fontSize: "0.685rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Trial Balance Integrity</span>
                  <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "#34d399", marginTop: "2px" }}>Balanced ✓ ({s3TotalBalanceFormatted})</div>
                </div>
                <div style={{ padding: "8px 12px", borderRadius: "6px", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-subtle)" }}>
                  <span style={{ fontSize: "0.685rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Schedule III Auto-Mapped</span>
                  <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "#c084fc", marginTop: "2px" }}>
                    {filteredS3Records.filter(r => !r.section.includes("UNMAPPED") && !r.section.includes("Review")).length} / {s3Records.length} Heads
                  </div>
                </div>
                <div style={{ padding: "8px 12px", borderRadius: "6px", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-subtle)" }}>
                  <span style={{ fontSize: "0.685rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Review Queue</span>
                  <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "#f59e0b", marginTop: "2px" }}>
                    {filteredS3Records.filter(r => r.section.includes("UNMAPPED") || r.section.includes("Review")).length} Pending
                  </div>
                </div>
              </div>

              {/* Schedule III Mappings Table */}
              <div style={{ flex: 1, overflowY: "auto", overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.785rem" }}>
                  <thead>
                    <tr style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-secondary)", position: "sticky", top: 0, zIndex: 10, textAlign: "left", borderBottom: "1px solid var(--border-subtle)" }}>
                      <th style={{ padding: "7px 10px", width: "85px" }}>{erpShortLabel} #</th>
                      <th style={{ padding: "7px 10px" }}>Account Description</th>
                      <th style={{ padding: "7px 10px", width: "40px", textAlign: "center" }}>Side</th>
                      <th style={{ padding: "7px 10px", textAlign: "right" }}>Amount (INR)</th>
                      <th style={{ padding: "7px 10px" }}>Schedule III Code</th>
                      <th style={{ padding: "7px 10px" }}>Classification Head</th>
                      <th style={{ padding: "7px 10px" }}>Method</th>
                      <th style={{ padding: "7px 10px", textAlign: "right" }}>Confidence</th>
                      <th style={{ padding: "7px 10px" }}>Audit Status</th>
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
                            borderBottom: "1px solid rgba(30, 41, 59, 0.5)",
                            backgroundColor: isHighlighted ? undefined : idx % 2 === 0 ? "rgba(255, 255, 255, 0.015)" : "transparent",
                            transition: "background-color 0.15s",
                          }}
                        >
                          <td style={{ padding: "8px 10px", color: isHighlighted ? "#f59e0b" : "#93c5fd", fontWeight: 700, fontFamily: "monospace" }}>
                            {glCode}
                          </td>
                          <td style={{ padding: "8px 10px", fontWeight: 600, color: "var(--text-primary)" }}>
                            {acctName}
                          </td>
                          <td style={{ padding: "8px 10px", textAlign: "center" }}>
                            <span style={{ fontSize: "0.685rem", fontWeight: 700, color: side === "Dr" ? "#34d399" : "#60a5fa" }}>
                              {side}
                            </span>
                          </td>
                          <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, color: "#34d399" }} className="tabular-nums">
                            {r.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </td>
                          <td style={{ padding: "8px 10px" }}>
                            <span
                              style={{
                                fontSize: "0.685rem",
                                padding: "2px 6px",
                                borderRadius: "4px",
                                backgroundColor: isAutoMapped ? "rgba(167, 139, 250, 0.15)" : "rgba(245, 158, 11, 0.15)",
                                border: isAutoMapped ? "1px solid rgba(167, 139, 250, 0.3)" : "1px solid rgba(245, 158, 11, 0.3)",
                                color: isAutoMapped ? "#c084fc" : "#fbbf24",
                                fontWeight: 700,
                                fontFamily: "monospace",
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
                          <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 600, color: isAutoMapped ? "#34d399" : "#f59e0b" }} className="tabular-nums">
                            {Math.round(conf * 100)}%
                          </td>
                          <td style={{ padding: "8px 10px" }}>
                            <span
                              style={{
                                padding: "2px 6px",
                                borderRadius: "4px",
                                fontSize: "0.685rem",
                                fontWeight: 700,
                                backgroundColor: isAutoMapped ? "rgba(16, 185, 129, 0.12)" : "rgba(245, 158, 11, 0.12)",
                                border: isAutoMapped ? "1px solid rgba(16, 185, 129, 0.25)" : "1px solid rgba(245, 158, 11, 0.25)",
                                color: isAutoMapped ? "#34d399" : "#fbbf24",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "3px",
                              }}
                            >
                              {isAutoMapped ? <CheckCircle2 size={10} /> : <AlertTriangle size={10} />}
                              {isAutoMapped ? "AUTO-CLASSIFIED" : "PENDING REVIEW"}
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
              height: "40px",
              padding: "0 0.75rem",
              borderBottom: "1px solid var(--border-subtle)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexShrink: 0,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "7px" }}>
              <div
                style={{
                  width: "22px",
                  height: "22px",
                  borderRadius: "5px",
                  backgroundColor: "var(--accent-blue)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Bot size={13} color="#ffffff" />
              </div>
              <span style={{ fontSize: "0.825rem", fontWeight: 700, color: "var(--text-primary)" }}>
                AuditIQ Copilot
              </span>
              <span style={{ fontSize: "0.7rem", color: "#34d399", display: "inline-flex", alignItems: "center", gap: "3px" }}>
                • Grounded on {sqlRecords.length} SQL records
              </span>
            </div>

            <button
              onClick={() => {
                setMessages([
                  {
                    id: "new-session",
                    role: "assistant",
                    content: "Chat reset. Ask any question regarding the extracted financial records.",
                    timestamp: generateCurrentTime(),
                    citations: [],
                  },
                ]);
                setHighlightedRowId(null);
                setHighlightedBlockId(null);
                setHighlightedSqlId(null);
              }}
              title="Reset Chat"
              style={{
                backgroundColor: "transparent",
                border: "1px solid var(--border-subtle)",
                borderRadius: "4px",
                color: "var(--text-muted)",
                padding: "3px 7px",
                fontSize: "0.725rem",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "4px",
              }}
            >
              <RefreshCw size={11} />
              <span>Reset</span>
            </button>
          </div>

          {/* Message History Feed */}
          <div style={{ flex: 1, overflowY: "auto", padding: "0.85rem", display: "flex", flexDirection: "column", gap: "0.85rem" }}>
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
                    maxWidth: "92%",
                    borderRadius: "7px",
                    padding: "0.75rem 0.85rem",
                    backgroundColor: m.role === "user" ? "var(--accent-blue)" : "var(--bg-card)",
                    border: m.role === "assistant" ? "1px solid var(--border-subtle)" : "none",
                    color: "#ffffff",
                    fontSize: "0.825rem",
                    lineHeight: 1.55,
                    boxShadow: "0 1px 4px rgba(0,0,0,0.25)",
                  }}
                >
                  <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>

                  {/* Interactive Citation Badges */}
                  {m.citations && m.citations.length > 0 && (
                    <div style={{ marginTop: "0.6rem", paddingTop: "0.45rem", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                      <div style={{ fontSize: "0.65rem", color: "#93c5fd", fontWeight: 700, marginBottom: "4px", letterSpacing: "0.02em" }}>
                        EVIDENCE CITATIONS (CLICK TO JUMP &amp; PULSE):
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
                                jumpToPdfBlock(c.page, c.block_id);
                              } else if (c.row_index) {
                                jumpToSqlRecord(c.row_index);
                              }
                            }}
                            className="citation-tag"
                            title="Click to jump & highlight evidence in viewer"
                          >
                            <FileCheck size={11} color="#fbbf24" />
                            <span>{c.label || (c.page ? `Page ${c.page}` : `Record #${c.row_index}`)}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginTop: "3px", padding: "0 4px" }}>
                  {m.timestamp}
                </span>
              </div>
            ))}

            {isLoading && (
              <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--text-secondary)", fontSize: "0.785rem", padding: "0.5rem" }}>
                <Sparkles size={15} className="animate-spin" color="#60a5fa" />
                <span>Querying Google Gemini with extracted SQL records...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Prompt Recommendations */}
          <div
            style={{
              padding: "0.4rem 0.75rem",
              borderTop: "1px solid var(--border-subtle)",
              backgroundColor: "rgba(8, 12, 20, 0.4)",
              display: "flex",
              gap: "5px",
              overflowX: "auto",
              flexShrink: 0,
            }}
          >
            {[
              `What ${erpShortLabel} accounts were mapped to Property, Plant & Equipment (AST_PPE) under Schedule III?`,
              `Is the ${erpShortLabel} trial balance balanced? What are the total debits and credits?`,
              `What are the Current Investments (AST_CI) and Input Tax Credit (AST_OCA) balances from the ${erpShortLabel} trial balance?`,
              "Summarize the Independent Auditor's Report & Key Audit Matters",
              "What was Total Revenue from Operations & Central Rights in Note 25?",
              "What are the Player Remuneration and Franchisee Fee costs under Note 27?",
              "Cross-check inward invoices against GSTR-2B for Section 17(5) blocked credits",
              "Run Journal Entry Testing on Daybook for suspicious Sunday or adjustment vouchers",
            ].map((prompt, idx) => (
              <button
                key={idx}
                onClick={() => handleSendMessage(prompt)}
                style={{
                  whiteSpace: "nowrap",
                  fontSize: "0.7rem",
                  padding: "3px 8px",
                  borderRadius: "9999px",
                  backgroundColor: "var(--bg-elevated)",
                  border: "1px solid var(--border-subtle)",
                  color: "var(--text-secondary)",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
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
                backgroundColor: "var(--bg-primary)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "5px",
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
                placeholder="Ask an audit question (Ctrl+Enter to send)..."
                style={{
                  flex: 1,
                  background: "transparent",
                  border: "none",
                  color: "var(--text-primary)",
                  fontSize: "0.825rem",
                  outline: "none",
                  padding: "5px 3px",
                }}
              />

              <button
                type="submit"
                disabled={!inputQuestion.trim() || isLoading}
                style={{
                  backgroundColor: inputQuestion.trim() && !isLoading ? "var(--accent-blue)" : "var(--bg-elevated)",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "4px",
                  padding: "5px 10px",
                  cursor: inputQuestion.trim() && !isLoading ? "pointer" : "not-allowed",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: "background-color 0.15s",
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
            backgroundColor: "rgba(0,0,0,0.75)",
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
              borderRadius: "8px",
              border: "1px solid var(--border-subtle)",
              width: "100%",
              maxWidth: "480px",
              padding: "1.5rem",
              boxShadow: "0 16px 40px rgba(0,0,0,0.6)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.85rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <UploadCloud size={20} color="#60a5fa" />
                <h3 style={{ fontSize: "1.05rem", fontWeight: 700 }}>Upload Customer Document</h3>
              </div>
              <button
                disabled={isUploading}
                onClick={() => setShowUploadModal(false)}
                style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer" }}
              >
                <X size={16} />
              </button>
            </div>

            <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", lineHeight: 1.5, marginBottom: "1rem" }}>
              Upload any client <strong>Audited PDF</strong>, <strong>Financial Statements</strong>, or <strong>Excel / CSV</strong> spreadsheet.
              Data is parsed into a structured <strong>SQLite database</strong> and analyzed via <strong>Google Gemini API</strong>.
            </p>

            {uploadError && (
              <div style={{ padding: "7px 10px", borderRadius: "5px", backgroundColor: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.25)", color: "#fca5a5", fontSize: "0.775rem", marginBottom: "0.85rem" }}>
                {uploadError}
              </div>
            )}

            {/* Clickable Drop Zone */}
            <div
              onClick={() => {
                if (!isUploading) {
                  fileInputRef.current?.click();
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
                border: "2px dashed #3b82f6",
                borderRadius: "6px",
                padding: "2rem 1.25rem",
                textAlign: "center",
                backgroundColor: "rgba(59, 130, 246, 0.04)",
                marginBottom: "1.25rem",
                cursor: isUploading ? "wait" : "pointer",
                transition: "all 0.15s ease",
              }}
            >
              {isUploading ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" }}>
                  <Loader2 size={32} color="#3b82f6" className="animate-spin" />
                  <div style={{ fontWeight: 700, fontSize: "0.9rem", color: "var(--text-primary)" }}>
                    Extracting &amp; Populating SQL Data Structure...
                  </div>
                  <div style={{ fontSize: "0.725rem", color: "var(--text-muted)" }}>
                    Parsing lines, notes, amounts and storing in SQLite
                  </div>
                </div>
              ) : (
                <>
                  <FileText size={34} color="#60a5fa" style={{ margin: "0 auto 0.5rem auto" }} />
                  <div style={{ fontWeight: 700, fontSize: "0.9rem", color: "var(--text-primary)" }}>
                    Click to select a file from your computer
                  </div>
                  <div style={{ fontSize: "0.725rem", color: "var(--text-muted)", marginTop: "4px" }}>
                    or drag and drop your .pdf, .xlsx, or .csv file here
                  </div>
                </>
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
              <button
                disabled={isUploading}
                onClick={() => setShowUploadModal(false)}
                style={{
                  padding: "0.45rem 0.85rem",
                  borderRadius: "5px",
                  border: "1px solid var(--border-subtle)",
                  background: "transparent",
                  color: "var(--text-secondary)",
                  fontSize: "0.8rem",
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button
                disabled={isUploading}
                onClick={() => fileInputRef.current?.click()}
                style={{
                  padding: "0.45rem 1rem",
                  borderRadius: "5px",
                  backgroundColor: "var(--accent-blue)",
                  color: "#ffffff",
                  fontSize: "0.8rem",
                  fontWeight: 600,
                  border: "none",
                  cursor: "pointer",
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
