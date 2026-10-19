# AuditIQ HTTP API

The backend is a typed JSON API. It holds all business rules — the same services
the CLI calls — and ships **no frontend**. A separate client (React, Svelte,
whatever) talks to it over HTTP and is generated from, or checked against, the
OpenAPI document.

* Interactive docs: `GET /docs`
* Raw contract: `GET /openapi.json`
* Export for codegen: `auditiq api schema --out openapi.json`

```bash
pip install -e ".[web]"
auditiq serve                       # http://127.0.0.1:8765, loopback only
auditiq serve --port 9000 --reload  # dev mode
```

---

## Conventions

### Base path

Everything lives under `/api`. `/` is a small discovery payload; `/docs` and
`/openapi.json` are documentation.

### List endpoints return bare arrays

```json
[{"engagement_id": 1}, {"engagement_id": 2}]
```

There is no `{items, count}` envelope. The two exceptions are deliberate:

* `GET /api/engagements/{id}/tb-lines` returns `PageOut`
  (`items`, `total`, `limit`, `offset`) because it is paged.
* `GET /api/engagements/{id}/mappings?status=all` returns `MappingCountsOut`
  (`counts`, `total`) because it is a counter, not a list.

### Status codes

| Code | Meaning |
| --- | --- |
| `200` | Read / update succeeded |
| `201` | A resource was created — engagement, ingested document, reconciliation run |
| `400` | The request is malformed or asks for something the server will not do |
| `404` | No such engagement, unit, document or run |
| `409` | A precondition is not met (currently: materiality is unset) |
| `422` | Semantic validation failed (unknown FSLI, unreadable file, missing field) |
| `500` | Unexpected server error |
| `503` | The database schema is stale; run `auditiq store reset` |

### Error envelope

Every non-2xx response — including FastAPI's own body validation and unknown
routes — has exactly this shape:

```json
{
  "error": {
    "code": "materiality_unset",
    "message": "engagement 1 has no materiality; set one or pass --materiality",
    "details": {}
  }
}
```

`code` is a closed set: `bad_request`, `validation_failed`, `not_found`,
`materiality_unset`, `ingest_failed`, `schema_drift`, `internal_error`. Clients
should branch on `code`, never on `message`.

### CORS

Only local dev origins are allowed by default:

```
http://localhost:5173, http://127.0.0.1:5173, http://localhost:3000, http://127.0.0.1:3000
```

Override with a comma-separated `AUDITIQ_CORS_ORIGINS`. Credentials are not
allowed, so send no cookies — there is no auth in this phase.

### Path ingestion is off by default

`ingest/tb`, `ingest/fs` and `fs/coverage` accept either a multipart `file` or a
server-side `path` query parameter. Reading files off the server's disk is a CLI
affordance, so over HTTP it is rejected unless you set:

```bash
AUDITIQ_ALLOW_PATH_INGEST=1 auditiq serve
```

A browser client should always upload the file. The CLI is unaffected.

### Determinism

Ingestion, mapping, reconciliation and review are deterministic. The embedding
gate needs the `[mapping]` extra and degrades to dictionary-only when it is
absent. The LLM layer is opt-in per request (`{"use_llm": true}` on `/map`, or
`?use_llm=true` on `/ingest/fs` and `/fs/coverage`) and never runs in the
reconciliation path.

---

## Workflow

An engagement moves through these calls in order. Every step is idempotent or
explicitly resettable, so a client can re-run any of them.

```
POST   /api/engagements                              create
POST   /api/engagements/{id}/ingest/tb                Side A evidence (file)
POST   /api/engagements/{id}/map                     run the FSLI cascade
GET    /api/engagements/{id}/mappings                 pending heads
POST   /api/mappings/resolve                         approve a head
POST   /api/engagements/{id}/ingest/fs               Side B: the client's draft FS
POST   /api/engagements/{id}/materiality             required before recon
POST   /api/engagements/{id}/recon/run               tie out
GET    /api/engagements/{id}/recon                   latest persisted run
GET    /api/engagements/{id}/recon/explain/{unit}    per-unit attribution
GET    /api/engagements/{id}/exceptions              escalations
POST   /api/exceptions/{id}/dispose                  explain or accept
```

Side B is the **client's draft statements** by default. Analysing a published
report is a separate opt-in feature and is not exposed here.

A reviewer decision on a draft survives re-ingestion: on the next `/ingest/fs`
the stored `manual` (and previously replayed `cache`) rows seed the mapping
cache, matched on `(statement, normalised label)` for the client. A reset is
stored as `method="reset"` and acts as a tombstone, so an older draft cannot
resurrect the decision. Notes, equity and cash-flow rows are persisted for
provenance as `measure="note_total"` and never enter Side B or the face review
queue.

`POST /materiality` is mandatory: reconciliation fails with `409
materiality_unset` rather than inventing a threshold. `GET /materiality` returns
the current value alongside a revenue-based suggestion for the UI to prefill;
the suggestion is `null` until a draft FS has been ingested, because there is
nothing to base it on.

---

## Endpoints

Every route has a `summary`, a tag and a typed `response_model`; the table is a
reading aid, `openapi.json` is the source of truth.

| Tag | Method | Path | OK | Response | Request body |
| --- | --- | --- | --- | --- | --- |
| meta | `GET` | `/api/health` | 200 | `HealthOut` | — |
| meta | `GET` | `/api/meta` | 200 | `MetaOut` | — |
| engagements | `GET` | `/api/engagements` | 200 | `[EngagementSummaryOut]` | — |
| engagements | `POST` | `/api/engagements` | 201 | `EngagementSummaryOut` | `CreateEngagementIn` |
| engagements | `GET` | `/api/engagements/{engagement_id}` | 200 | `EngagementSummaryOut` | — |
| ingest | `POST` | `/api/engagements/{engagement_id}/ingest/tb` | 201 | `TbIngestOut` | multipart `file` *(or `?path=`)* |
| ingest | `POST` | `/api/engagements/{engagement_id}/ingest/fs` | 201 | `FsIngestOut` | multipart `file` *(or `?path=`)*; `?use_llm=` |
| ingest | `POST` | `/api/engagements/{engagement_id}/fs/coverage` | 200 | `FsCoverageOut` | multipart `file` *(or `?path=`)*; `?use_llm=` |
| ingest | `GET` | `/api/engagements/{engagement_id}/documents` | 200 | `[DocumentOut]` | — |
| ingest | `GET` | `/api/engagements/{engagement_id}/tb-lines` | 200 | `PageOut` | — |
| mapping | `POST` | `/api/engagements/{engagement_id}/map` | 200 | `MappingSummaryOut` | `MapIn` |
| mapping | `GET` | `/api/engagements/{engagement_id}/mappings` | 200 | `[PendingHeadOut]` \| `MappingCountsOut` | — |
| mapping | `POST` | `/api/mappings/resolve` | 200 | `ResolutionOut` | `ResolveIn` |
| mapping | `POST` | `/api/mappings/resolve-bulk` | 200 | `BulkResolveOut` | `BulkResolveIn` |
| mapping | `POST` | `/api/mappings/{line_id}/reset` | 200 | `ResolutionOut` | — |
| financial-statements | `GET` | `/api/engagements/{engagement_id}/fs-review` | 200 | `[FsUnmappedOut]` | — |
| financial-statements | `POST` | `/api/fs-lines/{line_id}/resolve` | 200 | `FsResolveOut` | `FsResolveIn` |
| financial-statements | `POST` | `/api/fs-lines/{line_id}/reset` | 200 | `FsResolveOut` | — |
| materiality | `GET` | `/api/engagements/{engagement_id}/materiality` | 200 | `MaterialityOut` | — |
| materiality | `POST` | `/api/engagements/{engagement_id}/materiality` | 200 | `EngagementInfoOut` | `MaterialityIn` |
| reconciliation | `POST` | `/api/engagements/{engagement_id}/recon/run` | 201 | `ReconOut` | `ReconRunIn` |
| reconciliation | `GET` | `/api/engagements/{engagement_id}/recon` | 200 | `ReconLatestOut` | — |
| reconciliation | `GET` | `/api/engagements/{engagement_id}/recon/explain/{unit_code}` | 200 | `ReconExplainOut` | — |
| exceptions | `GET` | `/api/engagements/{engagement_id}/exceptions` | 200 | `[ExceptionOut]` | — |
| exceptions | `POST` | `/api/exceptions/{exception_id}/dispose` | 200 | `ExceptionOut` | `DisposeIn` |
| reference | `GET` | `/api/taxonomy` | 200 | `[TaxonomyItemOut]` | — |
| reference | `GET` | `/api/groups` | 200 | `[GroupOut]` | — |
| reference | `GET` | `/api/erp-sources` | 200 | `ErpSourcesOut` | — |

### `GET /api/meta`

Do not hardcode enums in the client. This route returns the server's vocabulary:
statements, bases, units, encoder kinds, mapping statuses and methods, FS
measures, classifications, severities, exception kinds/statuses, document kinds,
ERP sources, allowed CORS origins, and capability flags
(`features.path_ingest`, `features.llm`).

### `GET /api/engagements/{id}/mappings`

`status` selects the shape:

| `status` | Returns |
| --- | --- |
| `pending_review` (default) | `[PendingHeadOut]` — heads awaiting a decision |
| `resolved` | `[PendingHeadOut]` with `status: "resolved"` — the audit trail |
| `all` | `MappingCountsOut` — `{counts: {auto, pending_review, resolved, unmapped}, total}` |

Any other value is `400 bad_request`.

Resolving a head applies to **every ledger line sharing it** (client code + ERP
system + raw code / normalized name), not just the representative `line_id`.

### `GET /api/engagements/{id}/tb-lines`

```
?limit=100&offset=0&status=auto|pending_review|resolved|unmapped
```

`limit` is clamped to `1..1000`. `total` is the unpaged count for the filter.
`status=unmapped` means *no mapping row at all*, which is different from a row
whose status is `unmapped`.

### `POST /api/engagements/{id}/recon/run`

```json
{
  "materiality": null,
  "pm": 0.75,
  "rounding_decimals": 2,
  "statements": "BS,P&L",
  "side_b_period": null,
  "no_persist": false
}
```

All fields are optional. `materiality` overrides the engagement value for this
run only. `statements` accepts `BS`, `P&L`, a comma-separated combination, or
`all`/omitted. Setting `no_persist` returns the summary without storing a run
(the `GET` endpoints will still show the previous one).

Two independent gates apply:

* **Rounding tolerance** — `unit_factor × 10^(−decimals) / 2`; the only
  difference treated as ignorable.
* **Materiality / performance materiality** — controls severity and escalation
  (`watch` / `material`), never whether a unit is accepted.

`status` is one of `clean`, `minor residual`, `watch items`, `material
differences`. `reconciled` is simply `material == 0` — watch and minor items do
not fail the tie-out, they inform the reviewer.

Reconciliation requires both sides to exist: a missing TB or draft FS is a `422`
with an actionable message. Materiality is checked after that and yields `409
materiality_unset`.

---

## Client generation

```bash
auditiq api schema --out openapi.json
npx openapi-typescript openapi.json -o src/api/schema.d.ts
```

The document is deterministic — building it twice yields byte-identical JSON —
so schema diffs stay meaningful in review. `tests/test_api_contract.py` fails if
a route loses its typed response, summary, tag or error envelope, or if a
list endpoint grows an envelope.

A minimal fetch client:

```ts
const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await res.json();
  if (!res.ok) throw new ApiError(body.error.code, body.error.message, body.error.details);
  return body as T;
}
```

For uploads, send `FormData` and let the browser set the boundary — do **not**
set `Content-Type` yourself.
