/**
 * TanStack Query hooks for FSLI mapping, review queue and resolution.
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { engagementKey } from "./engagements";
import type {
  MapIn,
  MappingSummaryOut,
  PendingHeadOut,
  MappingCountsOut,
  ResolveIn,
  ResolutionOut,
  BulkResolveIn,
  BulkResolveOut,
  FsUnmappedOut,
  FsResolveIn,
  FsResolveOut,
} from "./types";

export function mappingsKey(engagementId: number, status?: string) {
  return ["mappings", engagementId, status] as const;
}

export function fsReviewKey(engagementId: number) {
  return ["fs-review", engagementId] as const;
}

export function useRunMapping(engagementId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: MapIn) =>
      api<MappingSummaryOut>(`/api/engagements/${engagementId}/map`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: engagementKey(engagementId) });
      qc.invalidateQueries({
        queryKey: ["mappings", engagementId],
      });
    },
  });
}

export function usePendingMappings(engagementId: number) {
  return useQuery({
    queryKey: mappingsKey(engagementId, "pending_review"),
    queryFn: () =>
      api<PendingHeadOut[]>(
        `/api/engagements/${engagementId}/mappings?status=pending_review`
      ),
  });
}

export function useResolvedMappings(engagementId: number) {
  return useQuery({
    queryKey: mappingsKey(engagementId, "resolved"),
    queryFn: () =>
      api<PendingHeadOut[]>(
        `/api/engagements/${engagementId}/mappings?status=resolved`
      ),
  });
}

export function useMappingCounts(engagementId: number) {
  return useQuery({
    queryKey: mappingsKey(engagementId, "all"),
    queryFn: () =>
      api<MappingCountsOut>(
        `/api/engagements/${engagementId}/mappings?status=all`
      ),
  });
}

export function useResolveMapping(engagementId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ResolveIn) =>
      api<ResolutionOut>("/api/mappings/resolve", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: engagementKey(engagementId) });
      qc.invalidateQueries({
        queryKey: ["mappings", engagementId],
      });
    },
  });
}

export function useBulkResolve(engagementId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: BulkResolveIn) =>
      api<BulkResolveOut>("/api/mappings/resolve-bulk", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: engagementKey(engagementId) });
      qc.invalidateQueries({
        queryKey: ["mappings", engagementId],
      });
    },
  });
}

export function useResetMapping(engagementId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (lineId: number) =>
      api<ResolutionOut>(`/api/mappings/${lineId}/reset`, {
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: engagementKey(engagementId) });
      qc.invalidateQueries({
        queryKey: ["mappings", engagementId],
      });
    },
  });
}

// -- FS Review ---

export function useFsReview(engagementId: number) {
  return useQuery({
    queryKey: fsReviewKey(engagementId),
    queryFn: () =>
      api<FsUnmappedOut[]>(`/api/engagements/${engagementId}/fs-review`),
  });
}

export function useResolveFsLine(engagementId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      lineId,
      data,
    }: {
      lineId: number;
      data: FsResolveIn;
    }) =>
      api<FsResolveOut>(`/api/fs-lines/${lineId}/resolve`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: engagementKey(engagementId) });
      qc.invalidateQueries({ queryKey: fsReviewKey(engagementId) });
    },
  });
}

export function useResetFsLine(engagementId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (lineId: number) =>
      api<FsResolveOut>(`/api/fs-lines/${lineId}/reset`, {
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: engagementKey(engagementId) });
      qc.invalidateQueries({ queryKey: fsReviewKey(engagementId) });
    },
  });
}
