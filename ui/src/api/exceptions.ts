/**
 * TanStack Query hooks for exceptions.
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { engagementKey } from "./engagements";
import type { ExceptionOut, DisposeIn } from "./types";

export function exceptionsKey(engagementId: number) {
  return ["exceptions", engagementId] as const;
}

export function useExceptions(engagementId: number) {
  return useQuery({
    queryKey: exceptionsKey(engagementId),
    queryFn: () =>
      api<ExceptionOut[]>(`/api/engagements/${engagementId}/exceptions`),
  });
}

export function useDisposeException(engagementId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      exceptionId,
      data,
    }: {
      exceptionId: number;
      data: DisposeIn;
    }) =>
      api<ExceptionOut>(`/api/exceptions/${exceptionId}/dispose`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: engagementKey(engagementId) });
      qc.invalidateQueries({ queryKey: exceptionsKey(engagementId) });
    },
  });
}
