/**
 * TanStack Query hooks for reference/meta data.
 * Meta is fetched once and cached for the session (staleTime: Infinity).
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "./client";
import type {
  MetaOut,
  HealthOut,
  TaxonomyItemOut,
  GroupOut,
  ErpSourcesOut,
} from "./types";

export function useMeta() {
  return useQuery({
    queryKey: ["meta"] as const,
    queryFn: () => api<MetaOut>("/api/meta"),
    staleTime: Infinity,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"] as const,
    queryFn: () => api<HealthOut>("/api/health"),
    refetchInterval: 30_000,
  });
}

export function useTaxonomy() {
  return useQuery({
    queryKey: ["taxonomy"] as const,
    queryFn: () => api<TaxonomyItemOut[]>("/api/taxonomy"),
    staleTime: Infinity,
  });
}

export function useGroups() {
  return useQuery({
    queryKey: ["groups"] as const,
    queryFn: () => api<GroupOut[]>("/api/groups"),
    staleTime: Infinity,
  });
}

export function useErpSources() {
  return useQuery({
    queryKey: ["erp-sources"] as const,
    queryFn: () => api<ErpSourcesOut>("/api/erp-sources"),
    staleTime: Infinity,
  });
}
