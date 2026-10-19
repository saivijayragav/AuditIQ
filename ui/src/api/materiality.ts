/**
 * TanStack Query hooks for materiality.
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { engagementKey } from "./engagements";
import type { MaterialityIn, MaterialityOut, EngagementInfoOut } from "./types";

export function materialityKey(engagementId: number) {
  return ["materiality", engagementId] as const;
}

export function useMateriality(engagementId: number) {
  return useQuery({
    queryKey: materialityKey(engagementId),
    queryFn: () =>
      api<MaterialityOut>(`/api/engagements/${engagementId}/materiality`),
  });
}

export function useSetMateriality(engagementId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: MaterialityIn) =>
      api<EngagementInfoOut>(
        `/api/engagements/${engagementId}/materiality`,
        {
          method: "POST",
          body: JSON.stringify(data),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: engagementKey(engagementId) });
      qc.invalidateQueries({ queryKey: materialityKey(engagementId) });
    },
  });
}
