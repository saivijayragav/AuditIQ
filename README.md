# AuditIQ Core

Deterministic ingestion, reconciliation and review of Indian statutory audit data
(Ind AS / Schedule III of the Companies Act, 2013).

> Status: **P0 scaffold** — repository, core primitives and store are in place.
> ERP trial-balance ingestion, FSLI mapping, reconciliation and review are being
> added phase by phase (see the plan).

## What this repository does

AuditIQ Core ties a client's books to their presented financial statements:

1. **Data ingestion & preparation** — read ERP trial balances (Tally / SAP / Zoho)
   and the client's draft financial statements; normalize units/periods; map every
   ledger head to a Schedule III Financial Statement Line Item (FSLI).
2. **Reconciliation** — tie trial-balance balances to the draft financial
   statements, line item by line item, with materiality gates and exceptions.
3. **Financial statement review** — Schedule III presentation, classification and
   disclosure checks plus variance / materiality review.

Analyzing a *published* annual report is a separate, opt-in feature.

## Layout

```
config/taxonomy/        Committed reference assets (FSLI schema, aliases, seeds)
src/auditiq/core/       Taxonomy, units, periods, enums
src/auditiq/store/      SQLAlchemy schema + session helpers
src/auditiq/ingest/     ERP + financial-statement ingestion and preparation
src/auditiq/...         recon / review (added in later phases)
data/                   Local run data (gitignored)
tests/                  Test suite
```

The legacy `AuditIQ/` and `Financial_Report_Analysis_Agent/` folders are local
reference implementations only and are gitignored.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
auditiq --help
```

> If `python -m venv` fails with *"ensurepip is not available"* (some minimal
> Linux/WSL images), install the venv package (`apt install python3-venv`) or
> bootstrap pip with `curl -sSL https://bootstrap.pypa.io/get-pip.py | python3 -`.

## CLI

```bash
auditiq version
auditiq store init
auditiq store status
auditiq taxonomy show --statement BS
auditiq taxonomy show --search borrowings

# Ingest an ERP trial balance (layout auto-detected: tally | sap | zoho | generic)
auditiq ingest tb path/to/tb.xlsx --client T00 --period FY25-26 --name "Test Co"
auditiq ingest tb path/to/tb.xlsx --client T00 --period FY25-26 --source sap --unit crores
```

Ingestion is idempotent: re-ingesting the same file for the same engagement
replaces its prior lines (matched by content hash). Each run reports total debit
vs total credit so an out-of-balance trial balance is flagged immediately.

## FSLI mapping

Every ledger head is mapped to a Schedule III FSLI through a five-layer cascade
that degrades gracefully and never needs the network:

```
cache  ->  alias dictionary  ->  embedding gate  ->  constrained LLM  ->  review queue
```

* **cache** — heads already resolved for this engagement (reviewer decisions feed back).
* **alias dictionary** — `config/taxonomy/aliases.csv` (deterministic).
* **embedding gate** — auto-accepts the top FSLI only when similarity `>= tau_e`
  *and* the top-1 vs top-2 margin `>= delta`.
* **constrained LLM** — optional, **off by default**; only ever returns a code from
  the candidate shortlist or `UNKNOWN`.
* **review queue** — everything else is written as `pending_review` for a human.

```bash
# Map an engagement (dictionary + embedding; encoder auto-detected)
auditiq map --client T00 --period FY25-26

# Force a specific encoder, or dictionary-only
auditiq map --client T00 --period FY25-26 --encoder tfidf
auditiq map --client T00 --period FY25-26 --encoder none

# Enable the optional LLM layer (needs GOOGLE_API_KEY and the [llm] extra)
auditiq map --client T00 --period FY25-26 --llm

# Tune the gates on a labelled dev set -> data/thresholds/<client>.json (re-runnable per client)
auditiq tune path/to/labelled.csv --split dev --client T00
```

Results land in the `tb_mapping` table (`fsli_code`, `method`, `confidence`,
`status`). The embedding gate needs the `[mapping]` extra (`pip install -e ".[mapping]"`);
without it the cascade runs dictionary-only.
