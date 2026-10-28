# AuditIQ — Statutory Audit Intelligence & GST Copilot

Deterministic ingestion, statutory audit analytics (SA 520, SA 240), Schedule III compliance, GST reconciliation (Section 16/17), and an AI-grounded split-screen document copilot with live evidence highlighting.

---

## Quick Start: How to Run the Project

You can run AuditIQ in **under 2 minutes** using two terminal windows (one for the Python FastAPI backend, and one for the Next.js frontend).

### Prerequisites

* **Python 3.12** installed
* **Node.js 20+** and **npm** installed
* Git

---

### Step 1: Start the Backend API (FastAPI)

Open a terminal in the project root:

```bash
# 1. Create and activate virtual environment
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# 2. Install dependencies & install auditiq in editable mode
pip install -r requirements.txt
pip install -e .

# 3. Initialize the database
auditiq store init

# 4. Start the backend API server (runs at http://127.0.0.1:8765)
auditiq serve
```

> **Backend API Swagger UI**: Visit [`http://127.0.0.1:8765/docs`](http://127.0.0.1:8765/docs) to test all REST endpoints interactively.

---

### Step 2: Start the Frontend UI (Next.js & Better-Auth)

Open a second terminal window in the project root:

```bash
# 1. Navigate to the UI directory
cd ui

# 2. Install frontend dependencies
npm install

# 3. Start the Next.js development server
npm run dev
```

> **Web Application**: Open [`http://localhost:3000`](http://localhost:3000) in your browser.

---

### Step 3: Access the Grounded Copilot Workspace

1. Open [`http://localhost:3000`](http://localhost:3000) to view the **AuditIQ Landing Page**.
2. Click **"Sign In"** and use the **1-Click Demo Auditor Sign In** (`auditor@auditiq.internal`).
3. You will enter the **Grounded Copilot Workspace** (`/workspace`):
   * **Left Stage**: Interactive Document & Data Grid Viewer (73 FY 2023-24 GST Invoices, GSTR-2B portal data, and audited financial statements PDF).
   * **Right Stage**: ChatGPT / NotebookLM AI Copilot Chat.
   * **Live Evidence Highlighting**: Click any citation pill (e.g. `[📍 Row 5 • CAR/2023/042 • S.17(5)]`) to automatically scroll and trigger a **pulsing amber highlight** on the exact evidence row on the left.

---

## Running Automated Tests

Run the complete test suite (GST reconciliation, JET fraud testing, and SA 520 analytics):

```bash
# Activate .venv
.venv\Scripts\activate

# Run all 49 domain & integration unit tests
pytest -q tests/test_analytics.py tests/test_jet.py tests/test_gst.py
```

Expected result:

```
49 passed in ~10s
```

---

## Core Capabilities & Modules

### 1. GST Reconciliation & ITC Compliance (`src/auditiq/gst/`)

Multi-pass matching between **Tally / ERP Books Purchase Registers** and **GSTN Portal GSTR-2B** inward supplies:

* **Section 16(2)(aa) Matching**: Flags vendor invoices claimed in books but missing in GSTR-2B (reversal risk under Finance Act 2021).
* **Section 17(5) Blocked Credit Detection**: Auto-identifies ineligible ITC (motor vehicles, food & beverages, outdoor catering, club memberships, personal consumption).
* **Fuzzy Invoice Number Normalizer**: Handles delimiters, leading zeros, and vendor numbering quirks (e.g., `INV/2023-24/0042` $\leftrightarrow$ `INV20232442`).
* **Value & Rate Discrepancies**: Flags excess claims and tax differences outside tolerance gates.

**CLI Commands**:

```bash
# Run reconciliation on Books vs Portal files
auditiq gst recon --books data/GST/Tally_Purchase_Register_FY2023_24.xlsx --portal data/GST/GSTR2B_Portal_FY2023_24.xlsx

# Inspect any official GSTN JSON, CSV, or Excel file
auditiq gst inspect data/GST/Section_wise_CSV_files/GSTR2/b2b.csv --source portal

# Generate synthetic realistic FY 2023-24 paired audit datasets
auditiq gst generate-demo --output-dir data/GST --invoices 73
```

---

### 2. Grounded Document Copilot (`src/auditiq/copilot/` & `ui/app/workspace/`)

A dual-stage interface inspired by NotebookLM and ChatGPT for statutory auditors:

* **Document Agnostic**: Ingests Excel workbooks (`.xlsx`), CSV files, and audited Financial Statement PDFs.
* **Verifiable Grounding**: The LLM / AI pipe is constrained to active document rows. Every assertion outputs structured citations with document name, row ID, invoice number, and statutory reference.
* **Interactive Live Highlight**: Clicking any badge in the chat communicates across stages, centering the document viewer and triggering CSS `@keyframes citationPulse` on the target row or paragraph.

---

### 3. SA 240 Journal Entry Testing & Fraud Detection (`src/auditiq/gl/`)

Forensic journal entry testing (JET) complying with **Standard on Auditing 240**:

* **Benford's Law First-Digit Analysis**: Goodness-of-fit testing against logarithmic distribution ($P(d) = \log_{10}(1 + 1/d)$) to detect fabricated figures.
* **Round-Sum Spikes**: Identifies unusual clusters of round numbers (e.g. multiples of ₹10,000, ₹50,000, ₹1,00,000).
* **Weekend & Out-of-Hours Postings**: Flags journal vouchers posted on Sundays and bank holidays.
* **High-Value Manual Journals**: Surfaces debit/credit pairs exceeding engagement materiality.

**CLI Commands**:

```bash
auditiq jet analyze path/to/tally_daybook.xlsx --materiality 500000
```

---

### 4. SA 520 Analytical Procedures & Schedule III Mapping (`src/auditiq/analytics/`)

Automated ratio analysis and analytical review procedures under **SA 520** and Companies Act Schedule III:

* **11 Mandatory Ratios**: Current Ratio, Debt-Equity Ratio, Debt Service Coverage, Return on Equity, Inventory Turnover, Trade Receivables Turnover, Trade Payables Turnover, Net Capital Turnover, Net Profit Margin, Return on Capital Employed, Return on Investment.
* **YoY Fluctuation Gates**: Flags abnormal swings exceeding 15% (watch) and 25% (material).
* **Cross-Ratio Sanity Checks**: Validates interrelated movements (e.g., debt expansion vs. interest coverage deterioration).

**CLI Commands**:

```bash
# View the statutory ratio catalogue
auditiq analytics catalog --statutory-only

# Run analytical procedures for an engagement
auditiq analytics run --client T00 --period FY25-26
```

---

### 5. Schedule III FSLI Cascade & Reconciliation (`src/auditiq/reconciliation/`)

Ties trial-balance ledger heads to draft financial statement line items (FSLI):

```
cache  ->  alias dictionary  ->  embedding gate  ->  constrained LLM  ->  review queue
```

* **Materiality Thresholds**: Sets Overall Materiality ($M$) and Performance Materiality ($PM$).
* **Tie-out & Attribution**: Automatically categorizes variances into unmapped exposure, reclassification timing, or genuine book-to-report mismatches.

**CLI Commands**:

```bash
auditiq map --client T00 --period FY25-26
auditiq materiality suggest --client T00 --period FY25-26
auditiq recon run --client T00 --period FY25-26
```

---

## Repository Structure

```
AuditIQ/
├── src/auditiq/
│   ├── analytics/          # SA 520 ratio computation, swing detection, cross-checks
│   ├── api/                # FastAPI application, OpenAPI schema, endpoints
│   ├── copilot/            # Grounded search service, citation models, session state
│   ├── core/               # Taxonomy, Indian accounting standards, enums, units
│   ├── gl/                 # SA 240 Journal Entry Testing & Benford's Law
│   ├── gst/                # GST reconciliation engine, normalizer, template parser
│   ├── ingest/             # ERP adapters (Tally, SAP, Zoho) and PDF statement parser
│   ├── reconciliation/     # Side A (Books) vs Side B (FS) tie-out & materiality
│   └── store/              # SQLAlchemy SQLite models, migrations, and queries
├── ui/                     # Next.js App Router Frontend
│   ├── app/
│   │   ├── page.tsx        # AuditIQ Landing Page
│   │   ├── login/page.tsx  # Sign-In with 1-click Demo Auditor
│   │   ├── signup/page.tsx # Firm & Auditor registration
│   │   ├── workspace/page.tsx # Dual-Stage Grounded Copilot Workspace
│   │   └── api/auth/[...all]/ # Better-Auth API endpoint
│   ├── lib/
│   │   ├── auth.ts         # Better-Auth server configuration
│   │   └── auth-client.ts  # Better-Auth client hooks
│   └── next.config.mjs     # API rewrites to FastAPI (port 8765)
├── data/GST/               # Synthetic FY 2023-24 paired Tally & GSTR-2B datasets
├── tests/                  # 49 unit tests (analytics, JET, GST recon, contract)
├── .agents/skills/         # Installed AI agent skills (e.g., Impeccable)
├── requirements.txt        # Python backend dependencies
└── README.md
```

---

## Environment Variables

Copy or edit `.env` in the root directory:

```ini
# Optional: External LLM & AI Pipe Keys
AI_PIPE_KEY=your_key_here
GOOGLE_API_KEY=your_gemini_key_here
GROQ_API_KEY=your_groq_key_here

# Better-Auth Secret (Frontend)
BETTER_AUTH_SECRET=auditiq-super-secret-jwt-key-32-chars-long
BETTER_AUTH_URL=http://localhost:3000
```

---

## License

Built for statutory auditors, CA practitioners, and enterprise compliance teams complying with ICAI, NFRA, and Indian GST regulations.
