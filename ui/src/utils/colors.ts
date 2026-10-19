/**
 * Severity/classification → CSS color variable mapping.
 * Used consistently across badges, charts, and table cells.
 */

export const CLASSIFICATION_COLORS: Record<string, string> = {
  tied: "var(--success)",
  rounding: "var(--info)",
  minor: "var(--minor)",
  watch: "var(--warning)",
  material: "var(--danger)",
};

export const SEVERITY_COLORS: Record<string, string> = {
  none: "var(--text-secondary)",
  info: "var(--info)",
  watch: "var(--warning)",
  material: "var(--danger)",
  error: "var(--danger)",
  warning: "var(--warning)",
};

export const STATUS_COLORS: Record<string, string> = {
  auto: "var(--success)",
  resolved: "var(--accent)",
  pending_review: "var(--warning)",
  unmapped: "var(--text-secondary)",
  open: "var(--danger)",
  explained: "var(--info)",
  accepted: "var(--success)",
};

export const INTAKE_STATUS_COLORS: Record<string, string> = {
  intake: "var(--text-secondary)",
  "in progress": "var(--warning)",
  reconcilable: "var(--success)",
};

export const RECON_STATUS_COLORS: Record<string, string> = {
  clean: "var(--success)",
  "minor residual": "var(--info)",
  "watch items": "var(--warning)",
  "material differences": "var(--danger)",
};

/**
 * Mapping layers → chart-friendly colors.
 */
export const LAYER_COLORS: Record<string, string> = {
  cache: "hsl(210, 100%, 56%)",
  dict: "hsl(152, 68%, 46%)",
  emb: "hsl(270, 60%, 56%)",
  llm: "hsl(38, 92%, 56%)",
  group: "hsl(180, 60%, 46%)",
  manual: "hsl(0, 0%, 60%)",
};

export function classificationColor(c: string): string {
  return CLASSIFICATION_COLORS[c] ?? "var(--text-secondary)";
}

export function statusColor(s: string): string {
  return STATUS_COLORS[s] ?? "var(--text-secondary)";
}
