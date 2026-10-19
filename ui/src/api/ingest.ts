/**
 * TanStack Query hooks for trial-balance and financial-statement ingestion.
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, upload } from "./client";
import { engagementKey } from "./engagements";
import type {
  TbIngestOut,
  FsIngestOut,
  FsCoverageOut,
  DocumentOut,
  PageOut,
} from "./types";

export function documentsKey(engagementId: number) {
  return ["documents", engagementId] as const;
}

export function tbLinesKey(
  engagementId: number,
  opts?: { limit?: number; offset?: number; status?: string }
) {
  return ["tb-lines", engagementId, opts] as const;
}

export function useDocuments(engagementId: number) {
  return useQuery({
    queryKey: documentsKey(engagementId),
    queryFn: () =>
      api<DocumentOut[]>(`/api/engagements/${engagementId}/documents`),
  });
}

export function useTbLines(
  engagementId: number,
  opts: { limit?: number; offset?: number; status?: string } = {}
) {
  const { limit = 100, offset = 0, status } = opts;
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (status) params.set("status", status);

  return useQuery({
    queryKey: tbLinesKey(engagementId, opts),
    queryFn: () =>
      api<PageOut>(
        `/api/engagements/${engagementId}/tb-lines?${params.toString()}`
      ),
  });
}

export function useIngestTb(engagementId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      file,
      unit,
      source,
    }: {
      file: File;
      unit?: string;
      source?: string;
    }) => {
      const params: Record<string, string> = {};
      if (unit) params.unit = unit;
      if (source) params.source = source;
      return upload<TbIngestOut>(
        `/api/engagements/${engagementId}/ingest/tb`,
        file,
        params
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: engagementKey(engagementId) });
      qc.invalidateQueries({ queryKey: documentsKey(engagementId) });
      qc.invalidateQueries({ queryKey: tbLinesKey(engagementId) });
    },
  });
}

export function useIngestFs(engagementId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, unit }: { file: File; unit?: string }) => {
      const params: Record<string, string> = {};
      if (unit) params.unit = unit;
      return upload<FsIngestOut>(
        `/api/engagements/${engagementId}/ingest/fs`,
        file,
        params
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: engagementKey(engagementId) });
      qc.invalidateQueries({ queryKey: documentsKey(engagementId) });
    },
  });
}

export function useFsCoverage(engagementId: number) {
  return useMutation({
    mutationFn: ({ file }: { file: File }) =>
      upload<FsCoverageOut>(
        `/api/engagements/${engagementId}/fs/coverage`,
        file
      ),
  });
}
