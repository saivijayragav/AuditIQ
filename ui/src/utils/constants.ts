/**
 * Application-wide constants: route paths, query keys.
 */

export const ROUTES = {
  dashboard: "/",
  newEngagement: "/engagements/new",
  engagement: (id: number | string) => `/engagements/${id}`,
  ingestTb: (id: number | string) => `/engagements/${id}/ingest-tb`,
  tbLines: (id: number | string) => `/engagements/${id}/tb-lines`,
  mapping: (id: number | string) => `/engagements/${id}/mapping`,
  ingestFs: (id: number | string) => `/engagements/${id}/ingest-fs`,
  fsReview: (id: number | string) => `/engagements/${id}/fs-review`,
  materiality: (id: number | string) => `/engagements/${id}/materiality`,
  recon: (id: number | string) => `/engagements/${id}/recon`,
  exceptions: (id: number | string) => `/engagements/${id}/exceptions`,
} as const;

/** Workflow steps in order. Used by the stepper component. */
export const WORKFLOW_STEPS = [
  { key: "ingest-tb", label: "Ingest TB", path: ROUTES.ingestTb },
  { key: "mapping", label: "Map FSLIs", path: ROUTES.mapping },
  { key: "ingest-fs", label: "Ingest FS", path: ROUTES.ingestFs },
  { key: "fs-review", label: "FS Review", path: ROUTES.fsReview },
  { key: "materiality", label: "Materiality", path: ROUTES.materiality },
  { key: "recon", label: "Reconcile", path: ROUTES.recon },
  { key: "exceptions", label: "Exceptions", path: ROUTES.exceptions },
] as const;
