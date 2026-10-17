# AuditIQ Core

Deterministic ingestion, reconciliation and review of Indian statutory audit data
(Ind AS / Schedule III of the Companies Act, 2013).

> Status: **P2** — ERP ingestion, the FSLI mapping cascade, modular
> financial-statement ingestion and reconciliation are in place. Financial
> statement review is being added phase by phase (see the plan).

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
config/taxonomy/        Committed reference assets (FSLI schema, aliases, seeds, groups)
src/auditiq/core/       Taxonomy, units, periods, enums, presentation groups
src/auditiq/store/      SQLAlchemy schema + session helpers
src/auditiq/ingest/     ERP + financial-statement ingestion and preparation
src/auditiq/reconciliation/  Side A / Side B tie-out, materiality gates, attribution
src/auditiq/...         review (added in a later phase)
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

## Financial-statement ingestion (reconciliation Side B)

The client's **draft financial statements** are the default other side of
reconciliation. Ingestion is modular: document-type readers implement a stable
`FsReader` interface and produce a reader-neutral document; segmentation, FSLI
labelling, unit/period normalisation, validation and persistence are shared. PDF
is the reader shipped today; Excel/CSV/HTML/DOCX slot in behind the same
interface. PDF support needs the `[report]` extra (`pip install -e ".[report]"`).

Every reported figure is converted to **absolute rupees** and bound to a financial
year (current column → engagement period, prior column → preceding year), and each
persisted `fs_line` carries an evidence pointer. Face **subtotal** rows are marked
(`measure = subtotal`) and excluded from the tie-out.

FS presentation labels are mapped to FSLIs by the **same five-layer cascade** as
ledger heads; `config/taxonomy/aliases.csv` carries the stable Schedule III
vocabulary and the embedding gate covers the rest.

A face line that **aggregates** several FSLIs (today *Revenue from Operations* on
a Division I face) is resolved to a **presentation group** before the cascade, so
it is tied out as one unit instead of being forced onto an arbitrary member.
Groups are committed config: `config/taxonomy/fsli_groups.csv` (membership, must
be disjoint) and `config/taxonomy/group_aliases.csv` (labels).

```bash
auditiq ingest fs path/to/draft_fs.pdf --client T00 --period FY25-26 [--unit lakhs]
auditiq fs coverage path/to/draft_fs.pdf --client T00    # mapped vs unmapped labels
```

## Reconciliation

Side A is the mapped trial balance; Side B is the client's draft financial
statements. Reconciliation covers the balance sheet and statement of profit and
loss (the taxonomy defines no cash-flow or equity FSLIs). Both sides are brought
into presentation space using each FSLI's normal balance, then joined over recon
units (FSLIs and presentation groups) so `only_a` / `only_b` are first-class.

Two gates, deliberately separate:

* **Rounding** — the only ignorable difference, derived from the reporting unit
  and the number of decimals presented (`crores` to 2 dp → ₹50,000 tolerance).
* **Materiality** — never accepts a difference, only grades severity
  (`≥ M` material, `PM ≤ |·| < M` watch). Materiality must be set; there is no
  silent fallback.

Reconciliation consumes the **persisted** mappings (`auditiq map` must have run)
and reports unmapped/pending heads as *exposure*, never summing them into the
books. Material variances escalate to the exception queue; differences are
attributed deterministically (unmapped exposure, mirror-pair reclass, current-year
result, residual).

```bash
auditiq materiality suggest --client T00 --period FY25-26      # 0.5% of revenue, for review
auditiq materiality set --client T00 --period FY25-26 --value 1000000 --basis-name "0.5% of revenue"
auditiq recon run   --client T00 --period FY25-26 [--materiality 1000000] [--pm 0.75] [--statement BS]
auditiq recon show  --client T00 --period FY25-26 [--severity material]
auditiq recon explain AST_TR --client T00 --period FY25-26
```

```bash
# Read the real published ITC report as an extraction sanity check
pip install -e ".[report]"
auditiq fs coverage Financial_Report_Analysis_Agent/itc-r-and-a-consolidated-fin-statements-2026.pdf
```
