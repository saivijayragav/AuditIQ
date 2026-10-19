/**
 * TanStack Query hooks for reconciliation.
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { engagementKey } from "./engagements";
import type {
  ReconRunIn,
  ReconOut,
  ReconLatestOut,
  ReconExplainOut,
} from "./types";

export function reconKey(engagementId: number) {
  return ["recon", engagementId] as const;
}

export function useRunRecon(engagementId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ReconRunIn) =>
      api<ReconOut>(`/api/engagements/${engagementId}/recon/run`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: engagementKey(engagementId) });
      qc.invalidateQueries({ queryKey: reconKey(engagementId) });
      qc.invalidateQueries({ queryKey: ["exceptions", engagementId] });
    },
  });
}

export function useReconLatest(engagementId: number) {
  return useQuery({
    queryKey: reconKey(engagementId),
    queryFn: () =>
      api<ReconLatestOut>(`/api/engagements/${engagementId}/recon`),
    retry: false,
  });
}

export function useReconExplain(engagementId: number, unitCode: string) {
  return useQuery({
    queryKey: [...reconKey(engagementId), "explain", unitCode] as const,
    queryFn: () =>
      api<ReconExplainOut>(
        `/api/engagements/${engagementId}/recon/explain/${unitCode}`
      ),
    enabled: !!unitCode,
  });
}
