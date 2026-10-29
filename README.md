# AuditIQ — Statutory Audit Intelligence & GST Copilot

Deterministic ingestion, statutory audit analytics (ICAI SA 520, SA 240, SA 701), Schedule III compliance, GST reconciliation (Section 16/17), and an AI-grounded split-screen document copilot with live evidence highlighting across native PDF and SQL structures.

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
# Alternatively, via uvicorn directly:
uvicorn auditiq.api.app:create_app --factory --host 127.0.0.1 --port 8765
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

1. Open [`http://localhost:3000`](http://localhost:3000) to view the **AuditIQ Landing Page** designed with the **Green-Ink Working Paper** design system.
2. Click **"Sign In"** or **"Register CA Firm"** to sign in via Better-Auth (or use **1-Click Senior Partner Demo Access**).
3. Open the **Grounded Copilot Workspace** (`/workspace`):
   * **Left Stage (Document Viewer)**: Switch between **Visual PDF**, **Extracted SQL Blocks**, **SQL Records Table**, and **GST / Spreadsheet Rows**.
   * **Right Stage (Grounded Copilot)**: Google Gemini statutory audit copilot with grounded citations.
   * **Dynamic Working Paper Banner**: Automatically classifies the active document (e.g. `[ Audit Report (ITC Limited) ]`, `[ SAP ERP Trial Balance ]`, `[ Zoho Books Trial Balance ]`, or `[ GSTR-2B Purchase Register ]`).
   * **Live Evidence Highlighting**: Click any citation voucher to automatically navigate the PDF, trigger Chromium PDFium in-canvas highlighting, and pulse target figures in **Auditor Canary Yellow** (`#FEF08A`, `#D97706`).

---

## Core Capabilities & Architecture

### 1. High-Performance Enterprise PDF Ingestion (`src/auditiq/copilot/service.py`)

Designed to parse and index massive annual reports (such as the 404-page, 45 MB ITC Report & Accounts 2026) in **under 3.5 seconds**:

* **Google Chromium PDFium Engine (`pypdfium2`)**: Direct C++ PDF rendering engine with **zero stream token limits** and native CFF/Type1/TrueType font parsing.
* **Resilient Enterprise Fallback**: Backed by `pypdf` configured with generous parsing budgets (`200,000,000` tokens) and isolated per-page exception handling.
* **Single-Transaction Bulk Indexing (`insert_records_bulk`)**: Uses SQLite `executemany` in a single transaction, indexing 9,500+ statutory line items in under 0.1s.

---

### 2. Dual-Mode Document Highlighting (`ui/app/workspace/page.tsx`)

* **Visual PDF Canvas Highlighting**:
  - Automatically appends `#page=${page}&search=${term}` to the viewer URL. Chromium PDFium natively executes an in-document find and highlights matches directly on the PDF canvas.
  - Features an interactive **"Highlight in PDF"** toolbar input box for live searching.
  - Displays a floating **Statutory Evidence Callout Banner** docked at the bottom of the PDF viewer displaying the exact cited statement with highlighted numbers and an instant `[ View in SQL Blocks → ]` toggle.
* **SQL Blocks View Highlighting**:
  - Highlights exact search keywords with `.auditor-highlight-search` (Canary Yellow `#FEF08A` background with `#D97706` amber border).
  - Highlights all statutory amounts, currencies, and percentages inside the active evidence block with `.auditor-highlight-number`.
  - Displays a prominent `★ CITED STATUTORY EVIDENCE BLOCK` header with amount badge and `[ View in Visual PDF ]` shortcut.
* **Synchronized SQL Records Table**:
  - Clicking any row in the **SQL Records** table jumps to that exact page in the PDF and highlights the line item.

---

### 3. Dynamic Document Classification & Contextual Prompts

The header banner and chat prompts automatically adapt based on document content:

| Active Working Paper | Classified Banner Pill | Dynamic Prompt Recommendations |
| :--- | :--- | :--- |
| **ITC Annual Report PDF** | `[ Audit Report (ITC Limited) ] • 404 Pages` | Key Audit Matters (KAM SA 701), Segment Revenues (Note 30), Disputed Indirect Taxes (Page 203), CSR Spend |
| **CSK / Audited PDF** | `[ Statutory Audit Report (PDF) ] • 135 Pages` | Independent Auditor's Report, Note 25 Revenue from Operations, Note 27 Cost of Operations |
| **SAP ERP Trial Balance** | `[ SAP ERP Trial Balance ] • Balanced` | Property, Plant & Equipment (AST_PPE) Schedule III mapping, Debit/Credit sanity checks |
| **Zoho Books** | `[ Zoho Books Trial Balance ] • Balanced` | Current Investments (AST_CI), Input Tax Credit (AST_OCA) mapping |
| **Tally ERP 9 / Prime** | `[ Tally ERP 9 / Prime ] • Balanced` | Tally Trial Balance validation, Journal Entry Testing on Daybook |
| **GST Register / GSTR-2B** | `[ GSTR-2B Purchase Register ] • 73 Invoices` | Section 17(5) blocked credits, Section 16(2)(aa) missing vendor invoices |

---

### 4. GST Reconciliation & ITC Compliance (`src/auditiq/gst/`)

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

### 5. SA 240 Journal Entry Testing & Fraud Detection (`src/auditiq/gl/`)

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

### 6. SA 520 Analytical Procedures & Schedule III Mapping (`src/auditiq/analytics/`)

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

### 7. Schedule III FSLI Cascade & Reconciliation (`src/auditiq/reconciliation/`)

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

## Design System: "The Green-Ink Working Paper"

AuditIQ is crafted around the tactile, rigorous aesthetic of physical statutory working papers:

* **Color Palette**:
  - Ledger Ivory (`#F4F1EA`) & Card Parchment (`#FAF8F3`) base surfaces.
  - Deep Forest Ink (`#0F382A`) for typography, active binders, and statutory borders.
  - Auditor Canary Yellow (`#FEF08A`) with Warm Amber (`#D97706`) for grounded evidence highlights.
  - Emerald Green (`#15803D`) and Deep Rose (`#B91C1C`) for compliance status flags.
* **Typography**: Classic serif financial headings paired with high-legibility tabular mono font stacks for monetary figures and invoice numbers.
* **Accounting Double-Rule**: Classic Pacioli double-close borders on balance totals.

---

## Running Automated Tests

Run the complete test suite:

```bash
# Activate .venv
.venv\Scripts\activate

# Run all domain & integration unit tests
pytest -q tests/test_analytics.py tests/test_jet.py tests/test_gst.py

# Verify TypeScript compilation & Next.js linting
npx tsc -p ui/tsconfig.json --noEmit
npm --prefix ui run lint
```

---

## Repository Structure

```
AuditIQ/
├── src/auditiq/
│   ├── analytics/          # SA 520 ratio computation, swing detection, cross-checks
│   ├── api/                # FastAPI application, OpenAPI schema, endpoints
│   ├── copilot/            # Grounded AI service, pypdfium2 extractor, SQLite store
│   │   ├── ai.py           # Google Gemini AI grounded reasoning engine
│   │   ├── models.py       # Session, Citation, ExtractedPdf Pydantic schemas
│   │   ├── service.py      # PDFium & pypdf ingestion pipeline
│   │   └── sql_store.py    # SQLite financial_records store & bulk insertion
│   ├── core/               # Taxonomy, Indian accounting standards, enums, units
│   ├── gl/                 # SA 240 Journal Entry Testing & Benford's Law
│   ├── gst/                # GST reconciliation engine, normalizer, template parser
│   ├── ingest/             # ERP adapters (Tally, SAP, Zoho) and PDF statement parser
│   ├── reconciliation/     # Side A (Books) vs Side B (FS) tie-out & materiality
│   └── store/              # SQLAlchemy SQLite models, migrations, and queries
├── ui/                     # Next.js App Router Frontend
│   ├── app/
│   │   ├── page.tsx        # AuditIQ Landing Page (Green-Ink design)
│   │   ├── login/page.tsx  # Sign-In with 1-click Demo Auditor
│   │   ├── signup/page.tsx # Firm & Auditor registration
│   │   ├── workspace/page.tsx # Dual-Stage Grounded Copilot Workspace
│   │   └── api/auth/[...all]/ # Better-Auth API endpoint
│   ├── public/             # Sample audited PDFs and demo working papers
│   ├── lib/
│   │   ├── auth.ts         # Better-Auth server configuration
│   │   └── auth-client.ts  # Better-Auth client hooks
│   └── next.config.mjs     # API rewrites to FastAPI (port 8765)
├── data/GST/               # Synthetic FY 2023-24 paired Tally & GSTR-2B datasets
├── tests/                  # Unit tests (analytics, JET, GST recon, contract)
├── requirements.txt        # Python backend dependencies (FastAPI, pypdfium2, fonttools)
├── .gitignore              # Configured ignore patterns (ignoring root PDFs & scratch)
└── README.md               # Comprehensive documentation
```

---

## Environment Variables

Copy or edit `.env` in the root directory:

```ini
# Google Gemini API Key (for Grounded Copilot AI reasoning)
GOOGLE_API_KEY=your_gemini_api_key_here

# Optional: External LLM & AI Pipe Keys
AI_PIPE_KEY=your_key_here
GROQ_API_KEY=your_groq_key_here

# Better-Auth Secret (Frontend)
BETTER_AUTH_SECRET=auditiq-super-secret-jwt-key-32-chars-long
BETTER_AUTH_URL=http://localhost:3000
```

---

## License

Built for statutory auditors, CA practitioners, and enterprise compliance teams complying with ICAI, NFRA, and Indian GST regulations.
