/**
 * Base API client for AuditIQ.
 *
 * All requests go through `api()` or `upload()`. Both handle the backend's
 * typed error envelope ({error: {code, message, details}}) and throw an
 * `ApiError` that components can catch and display.
 */
import type { ErrorCode } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765";

export class ApiError extends Error {
  code: ErrorCode;
  details: Record<string, unknown>;

  constructor(
    code: ErrorCode,
    message: string,
    details: Record<string, unknown> = {}
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.details = details;
  }
}

/**
 * JSON API call. Automatically sets Content-Type and parses the error
 * envelope on non-2xx responses.
 */
export async function api<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (init?.headers) {
    Object.assign(headers, init.headers);
  }

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  const body = await res.json();

  if (!res.ok) {
    const err = body?.error;
    throw new ApiError(
      err?.code ?? "internal_error",
      err?.message ?? `Request failed with status ${res.status}`,
      err?.details ?? {}
    );
  }

  return body as T;
}

/**
 * Multipart file upload. Do NOT set Content-Type — let the browser set
 * the multipart boundary automatically.
 */
export async function upload<T>(
  path: string,
  file: File,
  params?: Record<string, string>
): Promise<T> {
  const form = new FormData();
  form.append("file", file);

  const url = new URL(`${BASE}${path}`);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      url.searchParams.set(k, v);
    }
  }

  const res = await fetch(url.toString(), {
    method: "POST",
    body: form,
  });
  const body = await res.json();

  if (!res.ok) {
    const err = body?.error;
    throw new ApiError(
      err?.code ?? "internal_error",
      err?.message ?? `Upload failed with status ${res.status}`,
      err?.details ?? {}
    );
  }

  return body as T;
}
