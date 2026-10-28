"use client";

import React from "react";
import Link from "next/link";
import {
  ShieldCheck,
  FileSpreadsheet,
  FileSearch,
  Sparkles,
  ArrowRight,
  AlertTriangle,
  Scale,
  BrainCircuit,
  Lock,
  ExternalLink,
  ChevronRight,
} from "lucide-react";

export default function HomePage() {
  return (
    <div style={{ minHeight: "100vh", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}>
      {/* Navigation Bar */}
      <header
        style={{
          borderBottom: "1px solid var(--border-subtle)",
          padding: "1rem 2rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          position: "sticky",
          top: 0,
          zIndex: 50,
          backgroundColor: "rgba(11, 15, 25, 0.95)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div
            style={{
              width: "36px",
              height: "36px",
              borderRadius: "8px",
              backgroundColor: "var(--accent-blue)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 2px 8px rgba(37, 99, 235, 0.3)",
            }}
          >
            <ShieldCheck size={22} color="#ffffff" />
          </div>
          <div>
            <span style={{ fontSize: "1.25rem", fontWeight: 800, letterSpacing: "-0.03em" }}>
              Audit<span style={{ color: "#3b82f6" }}>IQ</span>
            </span>
            <span
              style={{
                marginLeft: "8px",
                fontSize: "0.65rem",
                textTransform: "uppercase",
                backgroundColor: "rgba(59, 130, 246, 0.12)",
                color: "#60a5fa",
                padding: "2px 6px",
                borderRadius: "4px",
                fontWeight: 700,
                border: "1px solid rgba(59, 130, 246, 0.25)",
              }}
            >
              Enterprise CA
            </span>
          </div>
        </div>

        <nav style={{ display: "flex", alignItems: "center", gap: "2rem" }}>
          <a href="#features" style={{ color: "var(--text-secondary)", fontSize: "0.9rem", transition: "color 0.2s" }}>
            Capabilities
          </a>
          <a href="#standards" style={{ color: "var(--text-secondary)", fontSize: "0.9rem", transition: "color 0.2s" }}>
            Statutory Standards
          </a>
          <a href="#demo" style={{ color: "var(--text-secondary)", fontSize: "0.9rem", transition: "color 0.2s" }}>
            Live Grounded Demo
          </a>
        </nav>

        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <Link
            href="/login"
            style={{
              padding: "0.5rem 1rem",
              fontSize: "0.9rem",
              fontWeight: 600,
              color: "var(--text-primary)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "6px",
              backgroundColor: "rgba(255, 255, 255, 0.03)",
              transition: "all 0.2s",
            }}
          >
            Sign In
          </Link>
          <Link
            href="/workspace"
            style={{
              padding: "0.5rem 1.25rem",
              fontSize: "0.9rem",
              fontWeight: 600,
              borderRadius: "6px",
              backgroundColor: "var(--accent-blue)",
              color: "#ffffff",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              boxShadow: "0 2px 8px rgba(37, 99, 235, 0.35)",
              transition: "all 0.2s",
            }}
          >
            <Sparkles size={16} />
            Launch Copilot
          </Link>
        </div>
      </header>

      {/* Hero Section */}
      <section
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "5rem 1.5rem 3.5rem 1.5rem",
          textAlign: "center",
        }}
      >
        <h1
          style={{
            fontSize: "3.5rem",
            fontWeight: 800,
            letterSpacing: "-0.04em",
            lineHeight: 1.15,
            marginBottom: "1.5rem",
            color: "#f8fafc",
          }}
        >
          Statutory Audit Intelligence with Real-Time Document Grounding
        </h1>

        <p
          style={{
            maxWidth: "760px",
            margin: "0 auto 2.5rem auto",
            fontSize: "1.125rem",
            color: "var(--text-secondary)",
            lineHeight: 1.6,
          }}
        >
          Ingest audited financial statement PDFs, general ledgers, and GSTR-2B purchase registers directly into an SQL structure. Ask statutory audit questions and verify answers with live, pulsing visual evidence highlights.
        </p>

        <div style={{ display: "flex", justifyContent: "center", gap: "1rem", flexWrap: "wrap", marginBottom: "3.5rem" }}>
          <Link
            href="/workspace"
            style={{
              padding: "0.875rem 2rem",
              fontSize: "1rem",
              fontWeight: 600,
              borderRadius: "6px",
              backgroundColor: "var(--accent-blue)",
              color: "#ffffff",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              boxShadow: "0 4px 12px rgba(37, 99, 235, 0.3)",
            }}
          >
            <span>Open Auditor Workspace</span>
            <ArrowRight size={18} />
          </Link>
          <Link
            href="/login"
            style={{
              padding: "0.875rem 1.75rem",
              fontSize: "1rem",
              fontWeight: 600,
              borderRadius: "6px",
              backgroundColor: "rgba(255, 255, 255, 0.04)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-primary)",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <Lock size={16} color="var(--text-secondary)" />
            <span>Auditor Sign In</span>
          </Link>
        </div>

        {/* Live Interactive Split-Screen Teaser Card */}
        <div
          id="demo"
          style={{
            backgroundColor: "var(--bg-secondary)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "12px",
            padding: "1rem",
            boxShadow: "0 12px 32px rgba(0, 0, 0, 0.5)",
            textAlign: "left",
            maxWidth: "1050px",
            margin: "0 auto",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "0.5rem 0.75rem 0.75rem 0.75rem",
              borderBottom: "1px solid var(--border-subtle)",
              marginBottom: "1rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <div style={{ width: "10px", height: "10px", borderRadius: "50%", backgroundColor: "#ef4444" }} />
              <div style={{ width: "10px", height: "10px", borderRadius: "50%", backgroundColor: "#f59e0b" }} />
              <div style={{ width: "10px", height: "10px", borderRadius: "50%", backgroundColor: "#10b981" }} />
              <span style={{ marginLeft: "8px", fontSize: "0.8rem", color: "var(--text-muted)", fontFamily: "monospace" }}>
                Dual-Stage Grounded Workspace (FY 2023-24 Statutory Audit)
              </span>
            </div>
            <Link
              href="/workspace"
              style={{
                fontSize: "0.775rem",
                color: "#60a5fa",
                display: "flex",
                alignItems: "center",
                gap: "4px",
                fontWeight: 600,
              }}
            >
              Try Live Workspace <ExternalLink size={12} />
            </Link>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: "1rem" }}>
            {/* Left Mock: Document Table with Glowing Highlight */}
            <div
              style={{
                backgroundColor: "var(--bg-card)",
                borderRadius: "8px",
                padding: "1rem",
                border: "1px solid var(--border-subtle)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <FileSpreadsheet size={16} color="#10b981" />
                  <span style={{ fontSize: "0.825rem", fontWeight: 700 }}>Tally_Purchase_Register_FY2023_24.xlsx</span>
                </div>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>73 Total Invoices</span>
              </div>

              <div style={{ fontSize: "0.75rem", fontFamily: "monospace", display: "flex", flexDirection: "column", gap: "6px" }}>
                <div style={{ display: "grid", gridTemplateColumns: "40px 90px 110px 80px 70px", color: "var(--text-muted)", fontWeight: 700, paddingBottom: "4px", borderBottom: "1px solid var(--border-subtle)" }}>
                  <span>Row</span>
                  <span>Invoice #</span>
                  <span>Party Name</span>
                  <span style={{ textAlign: "right" }}>Tax (INR)</span>
                  <span style={{ textAlign: "right" }}>Status</span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "40px 90px 110px 80px 70px", padding: "6px 4px", borderRadius: "4px", backgroundColor: "rgba(255,255,255,0.02)" }}>
                  <span>#1</span>
                  <span>INV-2023-01</span>
                  <span>Tata Steel Ltd</span>
                  <span style={{ textAlign: "right" }} className="tabular-nums">36,000</span>
                  <span style={{ textAlign: "right", color: "#34d399" }}>MATCH</span>
                </div>

                {/* Highlighted Row */}
                <div
                  className="citation-highlight-active"
                  style={{
                    display: "grid",
                    gridTemplateColumns: "40px 90px 110px 80px 70px",
                    padding: "6px 4px",
                    borderRadius: "4px",
                    fontWeight: 700,
                  }}
                >
                  <span style={{ color: "#f59e0b" }}>#5</span>
                  <span style={{ color: "#fbbf24" }}>CAR/042</span>
                  <span>Auto Care Corp</span>
                  <span style={{ textAlign: "right", color: "#f87171" }} className="tabular-nums">9,000</span>
                  <span style={{ textAlign: "right", color: "#f87171" }}>BLOCKED</span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "40px 90px 110px 80px 70px", padding: "6px 4px", borderRadius: "4px", backgroundColor: "rgba(255,255,255,0.02)" }}>
                  <span>#6</span>
                  <span>INF/990</span>
                  <span>Infosys BPM</span>
                  <span style={{ textAlign: "right" }} className="tabular-nums">14,400</span>
                  <span style={{ textAlign: "right", color: "#34d399" }}>MATCH</span>
                </div>
              </div>
            </div>

            {/* Right Mock: Copilot Chat Message */}
            <div
              style={{
                backgroundColor: "var(--bg-card)",
                borderRadius: "8px",
                padding: "1rem",
                border: "1px solid var(--border-subtle)",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
              }}
            >
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "0.75rem" }}>
                  <BrainCircuit size={16} color="#60a5fa" />
                  <span style={{ fontSize: "0.825rem", fontWeight: 700, color: "#93c5fd" }}>AuditIQ Statutory Assistant</span>
                </div>
                <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: "0.75rem" }}>
                  Identified ineligible input tax credit under <strong>Section 17(5)(a)</strong> for motor vehicle repairs:
                </p>
                <div
                  style={{
                    backgroundColor: "rgba(245, 158, 11, 0.08)",
                    border: "1px solid rgba(245, 158, 11, 0.25)",
                    borderRadius: "6px",
                    padding: "8px 10px",
                    fontSize: "0.775rem",
                    marginBottom: "0.75rem",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#f59e0b", fontWeight: 700, marginBottom: "4px" }}>
                    <AlertTriangle size={14} />
                    <span>Section 17(5) Blocked Credit Found</span>
                  </div>
                  <p style={{ color: "var(--text-primary)" }}>
                    Invoice <strong>CAR/042</strong> from Auto Care Corp claims INR 9,000 tax for vehicle repairs.
                  </p>
                  <div style={{ marginTop: "6px" }}>
                    <span className="citation-tag">
                      Row 5 • Inv #CAR/042 • Section 17(5)
                    </span>
                  </div>
                </div>
              </div>

              <div
                style={{
                  fontSize: "0.725rem",
                  color: "var(--text-muted)",
                  borderTop: "1px solid var(--border-subtle)",
                  paddingTop: "6px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <span>Clicking any citation badge jumps to and pulses that row</span>
                <span style={{ color: "#34d399", fontWeight: 600 }}>100% Grounded</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Pillar Cards */}
      <section
        id="features"
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "4rem 1.5rem",
        }}
      >
        <div style={{ textAlign: "center", marginBottom: "3rem" }}>
          <h2 style={{ fontSize: "2rem", fontWeight: 800, letterSpacing: "-0.03em", marginBottom: "0.75rem" }}>
            Engineered for Statutory Audit Rigor
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "1rem", maxWidth: "600px", margin: "0 auto" }}>
            Built around the exact standards mandated by ICAI, NFRA, and the Indian CGST Act.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: "1.5rem" }}>
          {/* Card 1 */}
          <div
            style={{
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "8px",
              padding: "1.75rem",
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
            }}
          >
            <div
              style={{
                width: "42px",
                height: "42px",
                borderRadius: "6px",
                backgroundColor: "rgba(59, 130, 246, 0.12)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#60a5fa",
              }}
            >
              <FileSearch size={22} />
            </div>
            <h3 style={{ fontSize: "1.15rem", fontWeight: 700 }}>Grounded Document Copilot</h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: 1.6 }}>
              Inspect and query your Excel workbooks, CSV purchase registers, and financial statement PDFs. The copilot never hallucinates — every observation is pinned to an exact row or coordinate.
            </p>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#60a5fa", fontSize: "0.85rem", fontWeight: 600, marginTop: "auto" }}>
              <span>Interactive Citations</span>
              <ChevronRight size={14} />
            </div>
          </div>

          {/* Card 2 */}
          <div
            style={{
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "8px",
              padding: "1.75rem",
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
            }}
          >
            <div
              style={{
                width: "42px",
                height: "42px",
                borderRadius: "6px",
                backgroundColor: "rgba(16, 185, 129, 0.12)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#34d399",
              }}
            >
              <Scale size={22} />
            </div>
            <h3 style={{ fontSize: "1.15rem", fontWeight: 700 }}>GST ITC S.16(2)(aa) & S.17(5)</h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: 1.6 }}>
              Multi-pass fuzzy reconciliation engine matching Books Purchase Registers with GSTR-2B portal data. Flags missing vendor filings and ineligible blocked credits instantly.
            </p>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#34d399", fontSize: "0.85rem", fontWeight: 600, marginTop: "auto" }}>
              <span>Tax Law Engine</span>
              <ChevronRight size={14} />
            </div>
          </div>

          {/* Card 3 */}
          <div
            style={{
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "8px",
              padding: "1.75rem",
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
            }}
          >
            <div
              style={{
                width: "42px",
                height: "42px",
                borderRadius: "6px",
                backgroundColor: "rgba(245, 158, 11, 0.12)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#fbbf24",
              }}
            >
              <AlertTriangle size={22} />
            </div>
            <h3 style={{ fontSize: "1.15rem", fontWeight: 700 }}>SA 240 Fraud & Anomaly Testing</h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: 1.6 }}>
              Automated Benford&apos;s Law first-digit analysis, round-sum transaction spikes, unusual posting hours, and journal entry testing (JET) complying with Standards on Auditing.
            </p>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#fbbf24", fontSize: "0.85rem", fontWeight: 600, marginTop: "auto" }}>
              <span>Forensic Detection</span>
              <ChevronRight size={14} />
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer
        style={{
          borderTop: "1px solid var(--border-subtle)",
          padding: "2.5rem 1.5rem",
          textAlign: "center",
          color: "var(--text-muted)",
          fontSize: "0.875rem",
        }}
      >
        <p>© 2026 AuditIQ. Built for statutory auditors, CA practitioners, and financial compliance teams.</p>
        <div style={{ display: "flex", justifyContent: "center", gap: "1.5rem", marginTop: "0.75rem" }}>
          <Link href="/workspace" style={{ color: "#60a5fa" }}>Grounded Workspace</Link>
          <Link href="/login" style={{ color: "var(--text-secondary)" }}>Auditor Login</Link>
          <Link href="/signup" style={{ color: "var(--text-secondary)" }}>Create Account</Link>
        </div>
      </footer>
    </div>
  );
}
