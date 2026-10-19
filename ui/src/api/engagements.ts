/**
 * TanStack Query hooks for engagement CRUD.
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { EngagementSummaryOut, CreateEngagementIn } from "./types";

export const ENGAGEMENTS_KEY = ["engagements"] as const;

export function engagementKey(id: number) {
  return ["engagement", id] as const;
}

export function useEngagements() {
  return useQuery({
    queryKey: ENGAGEMENTS_KEY,
    queryFn: () => api<EngagementSummaryOut[]>("/api/engagements"),
  });
}

export function useEngagement(id: number) {
  return useQuery({
    queryKey: engagementKey(id),
    queryFn: () => api<EngagementSummaryOut>(`/api/engagements/${id}`),
  });
}

export function useCreateEngagement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateEngagementIn) =>
      api<EngagementSummaryOut>("/api/engagements", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ENGAGEMENTS_KEY });
    },
  });
}
