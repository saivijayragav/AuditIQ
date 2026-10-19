/**
 * Formatting utilities for Indian currency, percentages and numbers.
 */

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const INR_PRECISE = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const NUM = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const PCT = new Intl.NumberFormat("en-IN", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** Format as ₹X,XX,XXX (no decimals). */
export function rupees(value: number | null | undefined): string {
  if (value == null) return "—";
  return INR.format(value);
}

export const inr = rupees;

/** Format as ₹X,XX,XXX.XX (2 decimals). */
export function rupeesPrecise(value: number | null | undefined): string {
  if (value == null) return "—";
  return INR_PRECISE.format(value);
}

/** Format as Indian-locale number (no currency symbol). */
export function num(value: number | null | undefined): string {
  if (value == null) return "—";
  return NUM.format(value);
}

/** Format as percentage (0.75 → "75.0%"). */
export function pct(value: number | null | undefined): string {
  if (value == null) return "—";
  return PCT.format(value);
}

/**
 * Format in compact Indian denomination:
 * ≥1Cr → "X.XX Cr", ≥1L → "X.XX L", else ₹X,XXX
 */
export function compact(value: number | null | undefined): string {
  if (value == null) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_00_00_000) return `${sign}₹${(abs / 1_00_00_000).toFixed(2)} Cr`;
  if (abs >= 1_00_000) return `${sign}₹${(abs / 1_00_000).toFixed(2)} L`;
  return INR.format(value);
}

/** Capitalize first letter. */
export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Human-readable classification/status label. */
export function label(s: string): string {
  return s
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
