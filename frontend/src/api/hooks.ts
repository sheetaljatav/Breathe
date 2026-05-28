/**
 * Centralized TanStack Query hooks. One file so the cache-key strategy stays
 * coherent — every key starts with the entity name + the org_id, so an org
 * switch invalidates everything tenant-scoped via predicate.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";

import { useUiStore } from "@/store/ui";
import { api, ensureCsrf } from "./client";
import type {
  ActivityRecordDetailDTO,
  ActivityRecordDTO,
  AirportDTO,
  CanonicalUnitDTO,
  EmissionFactorDTO,
  IngestionBatchDetailDTO,
  IngestionBatchDTO,
  OrganizationDTO,
  OverviewDTO,
  PaginatedDTO,
  PlantCodeDTO,
  ReviewState,
  SourceType,
  UserDTO,
} from "./types";

const k = {
  me:       () => ["me"] as QueryKey,
  orgs:     () => ["orgs"] as QueryKey,
  current:  (org: number | null) => ["org:current", org] as QueryKey,
  overview: (org: number | null) => ["overview", org] as QueryKey,
  batches:  (org: number | null, source?: SourceType) => ["batches", org, source ?? "all"] as QueryKey,
  batch:    (org: number | null, id: number) => ["batch", org, id] as QueryKey,
  queue:    (org: number | null, filters: Record<string, string | undefined>) =>
              ["queue", org, filters] as QueryKey,
  activity: (org: number | null, id: number) => ["activity", org, id] as QueryKey,
  factors:  () => ["factors"] as QueryKey,
  lookups:  (org: number | null) => ["lookups", org] as QueryKey,
  units:    () => ["units"] as QueryKey,
};

// ---------- auth + bootstrap ---------------------------------------------

export function useMe() {
  return useQuery({
    queryKey: k.me(),
    queryFn: () => api<UserDTO>("/api/auth/me", { noOrg: true }),
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { email: string; password: string }) => {
      await ensureCsrf();
      return api<UserDTO>("/api/auth/login", { method: "POST", body, noOrg: true });
    },
    onSuccess: (user) => {
      qc.setQueryData(k.me(), user);
      // If we don't have an org pinned yet, take the user's first membership.
      const ui = useUiStore.getState();
      if (!ui.orgId && user.memberships[0]) ui.setOrgId(user.memberships[0].organization.id);
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("/api/auth/logout", { method: "POST", noOrg: true }),
    onSuccess: () => {
      useUiStore.getState().setOrgId(null);
      // Set me to null immediately so App.tsx renders login routes without a
      // loading flash, then silently drop all other cached data.
      qc.setQueryData(k.me(), null);
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    },
  });
}

export function useOrgs() {
  return useQuery({
    queryKey: k.orgs(),
    queryFn: () => api<OrganizationDTO[]>("/api/orgs/"),
    staleTime: 5 * 60_000,
  });
}

// ---------- overview ------------------------------------------------------

export function useOverview() {
  const orgId = useUiStore((s) => s.orgId);
  return useQuery({
    queryKey: k.overview(orgId),
    queryFn: () => api<OverviewDTO>("/api/overview"),
    enabled: !!orgId,
  });
}

// ---------- ingestion -----------------------------------------------------

export function useBatches(source?: SourceType) {
  const orgId = useUiStore((s) => s.orgId);
  return useQuery({
    queryKey: k.batches(orgId, source),
    queryFn: () => api<PaginatedDTO<IngestionBatchDTO>>(
      `/api/batches/${source ? `?source=${source}` : ""}`
    ),
    enabled: !!orgId,
    refetchInterval: (q) => {
      // Poll while any batch in the page is still parsing.
      const data = q.state.data as PaginatedDTO<IngestionBatchDTO> | undefined;
      const live = data?.results.some(
        (b) => b.status === "queued" || b.status === "parsing"
      );
      return live ? 2_000 : false;
    },
  });
}

export function useBatch(id: number | null) {
  const orgId = useUiStore((s) => s.orgId);
  return useQuery({
    queryKey: k.batch(orgId, id ?? 0),
    queryFn: () => api<IngestionBatchDetailDTO>(`/api/batches/${id}/`),
    enabled: !!orgId && !!id,
    refetchInterval: (q) => {
      const data = q.state.data as IngestionBatchDetailDTO | undefined;
      return data && (data.status === "queued" || data.status === "parsing") ? 2_000 : false;
    },
  });
}

export function useUploadFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (args: { source_type: SourceType; file: File }) => {
      const fd = new FormData();
      fd.append("source_type", args.source_type);
      fd.append("file", args.file);
      return api<IngestionBatchDTO>("/api/ingest/upload", { method: "POST", body: fd });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["batches"] }),
  });
}

export function usePasteJson() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { payload: unknown; file_name?: string }) =>
      api<IngestionBatchDTO>("/api/ingest/paste", {
        method: "POST",
        body: { source_type: "travel", ...args },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["batches"] }),
  });
}

// ---------- review queue --------------------------------------------------

export function useQueue(filters: { state?: ReviewState; category?: string; batch?: string; q?: string }) {
  const orgId = useUiStore((s) => s.orgId);
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, String(value));
  }
  return useQuery({
    queryKey: k.queue(orgId, filters as Record<string, string>),
    queryFn: () => api<PaginatedDTO<ActivityRecordDTO>>(
      `/api/activities/${params.toString() ? "?" + params.toString() : ""}`
    ),
    enabled: !!orgId,
  });
}

export function useActivity(id: number | null) {
  const orgId = useUiStore((s) => s.orgId);
  return useQuery({
    queryKey: k.activity(orgId, id ?? 0),
    queryFn: () => api<ActivityRecordDetailDTO>(`/api/activities/${id}/`),
    enabled: !!orgId && !!id,
  });
}

export function usePatchActivity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: number; version: number; body: Record<string, unknown> }) =>
      api<ActivityRecordDTO>(`/api/activities/${args.id}/`, {
        method: "PATCH",
        body: args.body,
        ifMatch: args.version,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["activity"] });
      qc.invalidateQueries({ queryKey: ["queue"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export function useTransitionActivity(verb: "approve" | "flag" | "reject" | "lock" | "unlock") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: number; reason?: string }) =>
      api<ActivityRecordDTO>(`/api/activities/${args.id}/${verb}`, {
        method: "POST",
        body: args.reason ? { reason: args.reason } : {},
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["activity"] });
      qc.invalidateQueries({ queryKey: ["queue"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

// ---------- settings ------------------------------------------------------

export function useFactors() {
  return useQuery({
    queryKey: k.factors(),
    queryFn: () => api<PaginatedDTO<EmissionFactorDTO>>("/api/settings/factors"),
    staleTime: 5 * 60_000,
  });
}

export function useLookups() {
  const orgId = useUiStore((s) => s.orgId);
  return useQuery({
    queryKey: k.lookups(orgId),
    queryFn: () => api<{ plant_codes: PlantCodeDTO[]; airports: AirportDTO[] }>("/api/settings/lookups"),
    enabled: !!orgId,
    staleTime: 5 * 60_000,
  });
}

export function useUnits() {
  return useQuery({
    queryKey: k.units(),
    queryFn: () => api<PaginatedDTO<CanonicalUnitDTO>>("/api/settings/units"),
    staleTime: 5 * 60_000,
  });
}
