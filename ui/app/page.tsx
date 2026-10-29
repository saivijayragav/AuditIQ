"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  FileSpreadsheet,
  FileSearch,
  ArrowRight,
  AlertTriangle,
  Scale,
  Lock,
  ExternalLink,
  ChevronRight,
  CheckCircle2,
  FileCheck,
  FileText,
} from "lucide-react";

export default function HomePage() {
  const [activeDemoRow, setActiveDemoRow] = useState<number>(5);

  const demoRows = [
    {
      id: 1,
      inv: "INV-2023-01",
      party: "Tata Steel Ltd",
      tax: "36,000.00",
      status: "MATCH",
      statusColor: "var(--accent-emerald)",
      statusBg: "var(--accent-emerald-subtle)",
      findingTitle: "Vouched & Reconciled",
      findingBody: "Input tax credit matched with supplier GSTR-1 filing under Section 16(2)(aa). Tax paid to government confirmed.",
      voucherTag: "Row #1 • Inv INV-2023-01 • S.16(2)(aa) Vouched",
    },
    {
      id: 5,
      inv: "CAR/042",
      party: "Auto Care Corp",
      tax: "9,000.00",
      status: "BLOCKED",
      statusColor: "var(--accent-rose)",
      statusBg: "var(--accent-rose-subtle)",
      findingTitle: "Section 17(5)(a) Ineligible Credit",
      findingBody: "Invoice CAR/042 represents motor vehicle servicing and repairs. Ineligible input tax credit under Section 17(5)(a). Recommended add-back with Section 50 interest.",
      voucherTag: "Row #5 • Inv CAR/042 • Ineligible S.17(5)",
    },
    {
      id: 6,
      inv: "INF/990",
      party: "Infosys BPM Ltd",
      tax: "14,400.00",
      status: "MATCH",
      statusColor: "var(--accent-emerald)",
      statusBg: "var(--accent-emerald-subtle)",
      findingTitle: "Vouched IT Consulting",
      findingBody: "B2B software consulting fee vouched against service contract. Complete documentation available in digital working paper.",
      voucherTag: "Row #6 • Inv INF/990 • Vouched",
    },
    {
      id: 12,
      inv: "LOG/881",
      party: "Blue Dart Express",
      tax: "2,750.00",
      status: "MATCH",
      statusColor: "var(--accent-emerald)",
      statusBg: "var(--accent-emerald-subtle)",
      findingTitle: "Freight Inward Vouched",
      findingBody: "Couriers and freight inward verified. Consistent with standard operational logistical run rates.",
      voucherTag: "Row #12 • Inv LOG/881 • Vouched",
    },
  ];

  const currentFinding = demoRows.find((r) => r.id === activeDemoRow) || demoRows[1];

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}>
      {/* Top Engagement Bar */}
      <header
        style={{
          borderBottom: "1px solid var(--border-subtle)",
          padding: "0.85rem 2rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          position: "sticky",
          top: 0,
          zIndex: 50,
          backgroundColor: "var(--bg-secondary)",
          backdropFilter: "blur(8px)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
          <div
            style={{
              width: "34px",
              height: "34px",
              borderRadius: "4px",
              backgroundColor: "var(--accent-ink)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "var(--shadow-card)",
            }}
          >
            <Scale size={18} color="#FAF8F3" />
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
            <span style={{ fontSize: "1.25rem", fontWeight: 800, color: "var(--accent-ink)", fontFamily: "var(--font-serif)", letterSpacing: "-0.02em" }}>
              AuditIQ
            </span>
            <span
              style={{
                fontSize: "0.625rem",
                textTransform: "uppercase",
                backgroundColor: "var(--bg-card)",
                color: "var(--accent-ink)",
                padding: "2px 7px",
                borderRadius: "3px",
                fontWeight: 700,
                border: "1px solid var(--border-bright)",
                fontFamily: "var(--font-mono)",
                letterSpacing: "0.04em",
              }}
            >
              ICAI / SA-520 AUDIT SUITE
            </span>
          </div>
        </div>

        <nav style={{ display: "flex", alignItems: "center", gap: "1.75rem" }}>
          <a href="#docket-teaser" style={{ color: "var(--text-secondary)", fontSize: "0.85rem", fontWeight: 600, textDecoration: "none", transition: "color 0.15s" }}>
            Live Ledger Demo
          </a>
          <a href="#schedule3" style={{ color: "var(--text-secondary)", fontSize: "0.85rem", fontWeight: 600, textDecoration: "none", transition: "color 0.15s" }}>
            Schedule III Taxonomy
          </a>
          <a href="#standards" style={{ color: "var(--text-secondary)", fontSize: "0.85rem", fontWeight: 600, textDecoration: "none", transition: "color 0.15s" }}>
            Statutory Rigor
          </a>
          <a href="#erp" style={{ color: "var(--text-secondary)", fontSize: "0.85rem", fontWeight: 600, textDecoration: "none", transition: "color 0.15s" }}>
            ERP Adapters
          </a>
        </nav>

        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
          <Link
            href="/login"
            style={{
              padding: "0.45rem 0.9rem",
              fontSize: "0.825rem",
              fontWeight: 600,
              color: "var(--accent-ink, #0F382A)",
              border: "1px solid var(--border-subtle, #D8D2C4)",
              borderRadius: "3px",
              backgroundColor: "var(--bg-card, #FAF8F3)",
              textDecoration: "none",
              fontFamily: "var(--font-mono)",
              transition: "all 0.15s ease",
            }}
          >
            Sign In
          </Link>
          <Link
            href="/signup"
            style={{
              padding: "0.45rem 0.9rem",
              fontSize: "0.825rem",
              fontWeight: 600,
              color: "var(--accent-emerald, #15803D)",
              border: "1px solid rgba(21, 128, 61, 0.35)",
              borderRadius: "3px",
              backgroundColor: "var(--accent-emerald-subtle, rgba(21, 128, 61, 0.08))",
              textDecoration: "none",
              fontFamily: "var(--font-mono)",
              transition: "all 0.15s ease",
            }}
          >
            Sign Up
          </Link>
          <Link
            href="/workspace"
            style={{
              padding: "0.45rem 1.15rem",
              fontSize: "0.825rem",
              fontWeight: 600,
              borderRadius: "3px",
              backgroundColor: "var(--accent-ink, #0F382A)",
              color: "#FAF8F3",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              textDecoration: "none",
              boxShadow: "0 1px 4px rgba(15, 56, 42, 0.15)",
              fontFamily: "var(--font-mono)",
              transition: "all 0.15s ease",
            }}
          >
            <FileText size={14} />
            <span>Launch Docket</span>
          </Link>
        </div>
      </header>

      {/* Hero Section */}
      <section
        style={{
          maxWidth: "1240px",
          margin: "0 auto",
          padding: "4.5rem 1.5rem 3rem 1.5rem",
          textAlign: "center",
        }}
      >
        {/* Engagement Stamp */}
        <div style={{ display: "inline-flex", alignItems: "center", gap: "8px", padding: "4px 12px", borderRadius: "3px", backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border-bright)", marginBottom: "1.5rem", fontFamily: "var(--font-mono)", fontSize: "0.7rem", color: "var(--accent-ink)", fontWeight: 700, letterSpacing: "0.05em" }}>
          <span style={{ display: "inline-block", width: "7px", height: "7px", borderRadius: "50%", backgroundColor: "var(--accent-emerald)" }} />
          STATUTORY AUDIT INTELLIGENCE FOR CHARTERED ACCOUNTANTS
        </div>

        <h1
          style={{
            fontSize: "clamp(2.5rem, 5vw, 3.8rem)",
            fontWeight: 700,
            letterSpacing: "-0.03em",
            lineHeight: 1.15,
            marginBottom: "1.25rem",
            color: "var(--accent-ink)",
            fontFamily: "var(--font-serif)",
            maxWidth: "960px",
            margin: "0 auto 1.25rem auto",
          }}
        >
          Statutory Audit Intelligence Grounded in Primary Ledger Evidence
        </h1>

        <p
          style={{
            maxWidth: "760px",
            margin: "0 auto 2.5rem auto",
            fontSize: "1.1rem",
            color: "var(--text-secondary)",
            lineHeight: 1.6,
          }}
        >
          Ingest audited financial statement PDFs, ERP trial balances (<strong style={{ color: "var(--accent-ink)" }}>SAP, Tally, Zoho</strong>), and GSTR-2B purchase registers directly into an SQL working paper docket. Interrogate financial statements with Google Gemini, verified by live, cross-referenced voucher citations.
        </p>

        <div style={{ display: "flex", justifyContent: "center", gap: "1rem", flexWrap: "wrap", marginBottom: "3rem" }}>
          <Link
            href="/workspace"
            style={{
              padding: "0.85rem 2.25rem",
              fontSize: "0.95rem",
              fontWeight: 700,
              borderRadius: "4px",
              backgroundColor: "var(--accent-ink)",
              color: "#FAF8F3",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              boxShadow: "var(--shadow-card)",
              textDecoration: "none",
              fontFamily: "var(--font-serif)",
              letterSpacing: "0.01em",
              transition: "transform 0.15s ease",
            }}
          >
            <span>Open Auditor Working Paper</span>
            <ArrowRight size={17} />
          </Link>
          <Link
            href="/login"
            style={{
              padding: "0.85rem 1.85rem",
              fontSize: "0.95rem",
              fontWeight: 600,
              borderRadius: "4px",
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-bright)",
              color: "var(--accent-ink)",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              textDecoration: "none",
              fontFamily: "var(--font-mono)",
              boxShadow: "var(--shadow-card)",
            }}
          >
            <Lock size={15} color="var(--accent-ink)" />
            <span>Auditor Sign In</span>
          </Link>
        </div>

        {/* Feature Badges */}
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            gap: "1.5rem",
            flexWrap: "wrap",
            fontSize: "0.75rem",
            color: "var(--text-muted)",
            fontFamily: "var(--font-mono)",
            marginBottom: "3.5rem",
          }}
        >
          <span>✓ ICAI Standards on Auditing (SA 520 / SA 240)</span>
          <span>✓ Schedule III Balance Sheet Auto-Taxonomy</span>
          <span>✓ GST S.16(2)(aa) &amp; S.17(5) Reconciled</span>
          <span>✓ 100% Deterministic Evidence Grounding</span>
        </div>

        {/* Live Interactive Split-Screen Teaser Dossier */}
        <div
          id="docket-teaser"
          style={{
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "6px",
            boxShadow: "var(--shadow-card)",
            textAlign: "left",
            maxWidth: "1100px",
            margin: "0 auto",
            overflow: "hidden",
          }}
        >
          {/* Working Paper Dossier Header */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "0.75rem 1.25rem",
              backgroundColor: "var(--bg-secondary)",
              borderBottom: "1px solid var(--border-subtle)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <div style={{ display: "flex", gap: "5px" }}>
                <div style={{ width: "9px", height: "9px", borderRadius: "50%", backgroundColor: "var(--accent-rose)" }} />
                <div style={{ width: "9px", height: "9px", borderRadius: "50%", backgroundColor: "var(--accent-amber)" }} />
                <div style={{ width: "9px", height: "9px", borderRadius: "50%", backgroundColor: "var(--accent-emerald)" }} />
              </div>
              <span style={{ fontSize: "0.825rem", color: "var(--accent-ink)", fontFamily: "var(--font-mono)", fontWeight: 700 }}>
                ICAI Working Paper Dossier • Dual-Stage Grounded Verification (FY 2023-24 Statutory Audit)
              </span>
            </div>
            <Link
              href="/workspace"
              style={{
                fontSize: "0.75rem",
                color: "var(--accent-ink)",
                display: "flex",
                alignItems: "center",
                gap: "4px",
                fontWeight: 700,
                textDecoration: "none",
                fontFamily: "var(--font-mono)",
              }}
            >
              Open Live In Workspace <ExternalLink size={12} />
            </Link>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1.15fr 0.85fr", gap: "0" }}>
            {/* Left Mock: Physical Ledger Table */}
            <div
              style={{
                padding: "1.25rem",
                borderRight: "1px solid var(--border-subtle)",
                backgroundColor: "var(--bg-elevated)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <FileSpreadsheet size={15} color="var(--accent-ink)" />
                  <span style={{ fontSize: "0.825rem", fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-mono)" }}>
                    Tally_Purchase_Register_FY2023_24.xlsx
                  </span>
                </div>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                  Click row to inspect voucher
                </span>
              </div>

              <div style={{ fontSize: "0.75rem", fontFamily: "var(--font-mono)", display: "flex", flexDirection: "column" }}>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "40px 95px 120px 85px 85px",
                    color: "var(--accent-ink)",
                    fontWeight: 700,
                    padding: "6px 8px",
                    borderBottom: "2px solid var(--border-bright)",
                    backgroundColor: "var(--bg-secondary)",
                  }}
                >
                  <span>Row</span>
                  <span>Invoice #</span>
                  <span>Party Name</span>
                  <span style={{ textAlign: "right" }}>Tax (INR)</span>
                  <span style={{ textAlign: "right" }}>Status</span>
                </div>

                {demoRows.map((row) => {
                  const isSelected = activeDemoRow === row.id;
                  return (
                    <div
                      key={row.id}
                      onClick={() => setActiveDemoRow(row.id)}
                      className={isSelected ? "citation-highlight-active" : ""}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "40px 95px 120px 85px 85px",
                        padding: "7px 8px",
                        borderBottom: "1px solid var(--border-muted)",
                        backgroundColor: isSelected ? undefined : "var(--bg-card)",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                      }}
                    >
                      <span style={{ color: "var(--accent-ink)", fontWeight: 700 }}>#{row.id}</span>
                      <span style={{ fontWeight: 600 }}>{row.inv}</span>
                      <span style={{ color: "var(--text-primary)" }}>{row.party}</span>
                      <span style={{ textAlign: "right" }} className="tabular-nums">
                        {row.tax}
                      </span>
                      <span style={{ textAlign: "right" }}>
                        <span
                          style={{
                            padding: "1px 5px",
                            borderRadius: "3px",
                            fontSize: "0.65rem",
                            fontWeight: 700,
                            backgroundColor: row.statusBg,
                            color: row.statusColor,
                            border: `1px solid ${row.statusColor}40`,
                          }}
                        >
                          {row.status}
                        </span>
                      </span>
                    </div>
                  );
                })}
              </div>

              <div style={{ marginTop: "1rem", fontSize: "0.685rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                Standard: Indian CGST Act S.16(2)(aa) 4-Way Matching Against GSTR-2B
              </div>
            </div>

            {/* Right Mock: Senior Partner Audit Memorandum */}
            <div
              style={{
                padding: "1.25rem",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                backgroundColor: "var(--bg-card)",
              }}
            >
              <div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid var(--border-muted)", paddingBottom: "6px", marginBottom: "0.85rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <FileCheck size={15} color="var(--accent-ink)" />
                    <span style={{ fontSize: "0.775rem", fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-mono)", textTransform: "uppercase" }}>
                      Statutory Audit Opinion
                    </span>
                  </div>
                  <span style={{ fontSize: "0.65rem", color: "var(--accent-emerald)", fontFamily: "var(--font-mono)", fontWeight: 700 }}>
                    ICAI / SA-520
                  </span>
                </div>

                <div
                  style={{
                    backgroundColor: "var(--bg-elevated)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "4px",
                    padding: "12px 14px",
                    boxShadow: "var(--shadow-card)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", color: currentFinding.statusColor, fontWeight: 700, fontSize: "0.8rem", marginBottom: "6px", fontFamily: "var(--font-serif)" }}>
                    <AlertTriangle size={14} />
                    <span>{currentFinding.findingTitle}</span>
                  </div>

                  <p style={{ color: "var(--text-primary)", fontSize: "0.8rem", lineHeight: 1.55, margin: 0 }}>
                    {currentFinding.findingBody}
                  </p>

                  <div style={{ marginTop: "10px", paddingTop: "8px", borderTop: "1px solid var(--border-muted)" }}>
                    <div style={{ fontSize: "0.65rem", color: "var(--accent-ink)", fontWeight: 700, fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: "4px" }}>
                      Audited Evidence Voucher:
                    </div>
                    <span
                      className="citation-tag"
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
                      }}
                    >
                      <CheckCircle2 size={11} color="var(--accent-emerald)" />
                      {currentFinding.voucherTag}
                    </span>
                  </div>
                </div>
              </div>

              <div
                style={{
                  fontSize: "0.725rem",
                  color: "var(--text-muted)",
                  borderTop: "1px solid var(--border-subtle)",
                  paddingTop: "8px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  fontFamily: "var(--font-mono)",
                }}
              >
                <span>Live Grounding Engine</span>
                <span style={{ color: "var(--accent-emerald)", fontWeight: 700 }}>● 100% Deterministic</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Section: 3 Pillars */}
      <section
        id="standards"
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "4.5rem 1.5rem",
        }}
      >
        <div style={{ textAlign: "center", marginBottom: "3rem" }}>
          <h2 style={{ fontSize: "2.1rem", fontWeight: 700, letterSpacing: "-0.02em", color: "var(--accent-ink)", fontFamily: "var(--font-serif)", marginBottom: "0.75rem" }}>
            Engineered for Statutory Audit Rigor
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "1rem", maxWidth: "620px", margin: "0 auto" }}>
            Compliant with ICAI Standards on Auditing, NFRA inspection mandates, and the Companies Act 2013 Schedule III framework.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: "1.5rem" }}>
          {/* Card 1 */}
          <div
            style={{
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "4px",
              padding: "1.85rem",
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
              boxShadow: "var(--shadow-card)",
            }}
          >
            <div
              style={{
                width: "38px",
                height: "38px",
                borderRadius: "4px",
                backgroundColor: "var(--bg-secondary)",
                border: "1px solid var(--border-bright)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--accent-ink)",
              }}
            >
              <FileSearch size={20} />
            </div>
            <h3 style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-serif)" }}>
              Schedule III Auto-Taxonomy
            </h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: 1.6 }}>
              Automated classification of general ledger accounts into statutory Balance Sheet and P&amp;L heads under Division II (Ind AS) and Division I (AS). Uses exact dictionary lookup paired with embedding fallbacks.
            </p>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--accent-ink)", fontSize: "0.825rem", fontWeight: 700, marginTop: "auto", fontFamily: "var(--font-mono)" }}>
              <span>Division II Schedule III Taxonomy</span>
              <ChevronRight size={14} />
            </div>
          </div>

          {/* Card 2 */}
          <div
            style={{
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "4px",
              padding: "1.85rem",
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
              boxShadow: "var(--shadow-card)",
            }}
          >
            <div
              style={{
                width: "38px",
                height: "38px",
                borderRadius: "4px",
                backgroundColor: "var(--bg-secondary)",
                border: "1px solid var(--border-bright)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--accent-emerald)",
              }}
            >
              <Scale size={20} />
            </div>
            <h3 style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-serif)" }}>
              GST ITC S.16(2)(aa) &amp; S.17(5)
            </h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: 1.6 }}>
              Multi-pass fuzzy reconciliation engine matching Books Purchase Registers with GSTR-2B portal data. Automatically flags missing vendor filings, GSTIN mismatches, and ineligible blocked credits.
            </p>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--accent-emerald)", fontSize: "0.825rem", fontWeight: 700, marginTop: "auto", fontFamily: "var(--font-mono)" }}>
              <span>Tax Law Engine &amp; GSTR-2B Vouching</span>
              <ChevronRight size={14} />
            </div>
          </div>

          {/* Card 3 */}
          <div
            style={{
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "4px",
              padding: "1.85rem",
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
              boxShadow: "var(--shadow-card)",
            }}
          >
            <div
              style={{
                width: "38px",
                height: "38px",
                borderRadius: "4px",
                backgroundColor: "var(--bg-secondary)",
                border: "1px solid var(--border-bright)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--accent-amber)",
              }}
            >
              <AlertTriangle size={20} />
            </div>
            <h3 style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-serif)" }}>
              SA 240 Fraud &amp; Anomaly Testing
            </h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: 1.6 }}>
              Journal Entry Testing (JET) compliant with ICAI SA 240. Analyzes Benford&apos;s Law distribution deviations, round-sum transaction spikes, unusual posting hours, and unexpected debit-credit combinations.
            </p>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--accent-amber)", fontSize: "0.825rem", fontWeight: 700, marginTop: "auto", fontFamily: "var(--font-mono)" }}>
              <span>Forensic Journal Entry Analysis</span>
              <ChevronRight size={14} />
            </div>
          </div>
        </div>
      </section>

      {/* Multi-ERP Compatibility Banner */}
      <section
        id="erp"
        style={{
          borderTop: "1px solid var(--border-subtle)",
          borderBottom: "1px solid var(--border-subtle)",
          backgroundColor: "var(--bg-secondary)",
          padding: "3.5rem 1.5rem",
        }}
      >
        <div style={{ maxWidth: "1100px", margin: "0 auto", textAlign: "center" }}>
          <span style={{ fontSize: "0.7rem", color: "var(--accent-ink)", fontFamily: "var(--font-mono)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Client Data Interoperability
          </span>
          <h3 style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-serif)", marginTop: "0.4rem", marginBottom: "2rem" }}>
            Native Support for Major Indian Enterprise Accounting Systems
          </h3>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "1.25rem", textAlign: "left" }}>
            <div style={{ backgroundColor: "var(--bg-card)", padding: "1.25rem", borderRadius: "4px", border: "1px solid var(--border-bright)" }}>
              <div style={{ fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-mono)", fontSize: "0.95rem", marginBottom: "4px" }}>
                SAP ERP / S4 HANA
              </div>
              <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: 0, lineHeight: 1.5 }}>
                Direct ingestion of FBL3N General Ledger Line Items, S_ALR trial balances, and chart of accounts.
              </p>
            </div>

            <div style={{ backgroundColor: "var(--bg-card)", padding: "1.25rem", borderRadius: "4px", border: "1px solid var(--border-bright)" }}>
              <div style={{ fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-mono)", fontSize: "0.95rem", marginBottom: "4px" }}>
                TallyPrime / Tally.ERP 9
              </div>
              <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: 0, lineHeight: 1.5 }}>
                Parses Daybook exports, Detailed Trial Balances, and Purchase Registers with multi-tier ledger grouping.
              </p>
            </div>

            <div style={{ backgroundColor: "var(--bg-card)", padding: "1.25rem", borderRadius: "4px", border: "1px solid var(--border-bright)" }}>
              <div style={{ fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-mono)", fontSize: "0.95rem", marginBottom: "4px" }}>
                Zoho Books &amp; Cloud ERP
              </div>
              <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: 0, lineHeight: 1.5 }}>
                Extracts General Ledger transactions, Chart of Accounts mapping, and invoice detail schedules seamlessly.
              </p>
            </div>

            <div style={{ backgroundColor: "var(--bg-card)", padding: "1.25rem", borderRadius: "4px", border: "1px solid var(--border-bright)" }}>
              <div style={{ fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-mono)", fontSize: "0.95rem", marginBottom: "4px" }}>
                Audited PDF Statements
              </div>
              <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: 0, lineHeight: 1.5 }}>
                Full-text OCR block indexing into SQLite with page-coordinate navigation and interactive citation highlighting.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer
        style={{
          padding: "3rem 1.5rem",
          textAlign: "center",
          color: "var(--text-muted)",
          fontSize: "0.825rem",
          backgroundColor: "var(--bg-primary)",
        }}
      >
        <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "8px", marginBottom: "0.75rem" }}>
            <Scale size={16} color="var(--accent-ink)" />
            <span style={{ fontWeight: 700, color: "var(--accent-ink)", fontFamily: "var(--font-serif)", fontSize: "1rem" }}>
              AuditIQ Statutory Engagement System
            </span>
          </div>
          <p style={{ margin: "0 auto 1rem auto", maxWidth: "640px", lineHeight: 1.5 }}>
            Designed for senior statutory audit partners, FCA practitioners, and compliance teams. Grounded on Indian Companies Act 2013, ICAI Standards on Auditing, and CGST Rules.
          </p>
          <div style={{ display: "flex", justifyContent: "center", gap: "1.5rem", marginTop: "1rem", fontFamily: "var(--font-mono)", fontSize: "0.775rem" }}>
            <Link href="/workspace" style={{ color: "var(--accent-ink)", fontWeight: 700, textDecoration: "none" }}>
              Working Paper Docket
            </Link>
            <Link href="/login" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>
              Auditor Authentication
            </Link>
            <Link href="/signup" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>
              Register Practice
            </Link>
          </div>
          <div style={{ marginTop: "1.5rem", fontSize: "0.725rem", color: "var(--text-muted)" }}>
            © 2026 AuditIQ. All rights reserved.
          </div>
        </div>
      </footer>
    </div>
  );
}
