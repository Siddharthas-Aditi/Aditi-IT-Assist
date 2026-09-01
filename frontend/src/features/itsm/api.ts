/**
 * React Query hooks for the Changes and Assets backend APIs.
 *
 * All reads and writes go through the backend — no browser persistence path.
 * Every mutation invalidates the relevant query keys so list/detail
 * views stay in sync automatically.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "@/lib/api";

import type {
  ApprovalCreatePayload,
  ApprovalDecidePayload,
  AssetAssignPayload,
  AssetCreatePayload,
  AssetListResponse,
  AssetRecord,
  AssetRetirePayload,
  AssetStatus,
  AssetUpdatePayload,
  ChangeApproval,
  ChangeCreatePayload,
  ChangeListResponse,
  ChangeRecord,
  ChangeStatus,
  ChangeTask,
  ChangeTaskCreatePayload,
  ChangeTaskUpdatePayload,
  ChangeTransitionPayload,
  ChangeUpdatePayload,
} from "./api-types";

// ── Query keys ────────────────────────────────────────────────────────

export const changeKeys = {
  all: ["changes"] as const,
  list: (status?: string) => ["changes", "list", status ?? "all"] as const,
  detail: (id: string) => ["changes", "detail", id] as const,
};

export const assetKeys = {
  all: ["assets"] as const,
  list: (status?: string) => ["assets", "list", status ?? "all"] as const,
  detail: (id: string) => ["assets", "detail", id] as const,
};

// ── Change queries ────────────────────────────────────────────────────

export function useChanges(filters?: {
  status?: ChangeStatus;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: changeKeys.list(filters?.status),
    queryFn: () =>
      apiRequest<ChangeListResponse>("/changes", {
        query: {
          status: filters?.status,
          limit: filters?.limit ?? 100,
          offset: filters?.offset ?? 0,
        },
      }),
  });
}

export function useChange(id: string | null | undefined) {
  return useQuery({
    queryKey: changeKeys.detail(id ?? ""),
    queryFn: () => apiRequest<ChangeRecord>(`/changes/${id}`),
    enabled: !!id,
  });
}

// ── Change mutations ──────────────────────────────────────────────────

export function useCreateChange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ChangeCreatePayload) =>
      apiRequest<ChangeRecord>("/changes", { method: "POST", body: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: changeKeys.all }),
  });
}

export function useUpdateChange(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ChangeUpdatePayload) =>
      apiRequest<ChangeRecord>(`/changes/${id}`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: changeKeys.all });
      qc.invalidateQueries({ queryKey: changeKeys.detail(id) });
    },
  });
}

export function useDeleteChange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/changes/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: changeKeys.all }),
  });
}

export function useTransitionChange(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ChangeTransitionPayload) =>
      apiRequest<ChangeRecord>(`/changes/${id}/transition`, {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: changeKeys.all });
      qc.invalidateQueries({ queryKey: changeKeys.detail(id) });
    },
  });
}

export function useAddChangeApproval(changeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApprovalCreatePayload) =>
      apiRequest<ChangeApproval>(`/changes/${changeId}/approvals`, {
        method: "POST",
        body: payload,
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: changeKeys.detail(changeId) }),
  });
}

export function useDecideApproval(changeId: string, approvalId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApprovalDecidePayload) =>
      apiRequest<ChangeApproval>(
        `/changes/${changeId}/approvals/${approvalId}/decide`,
        { method: "POST", body: payload },
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: changeKeys.detail(changeId) }),
  });
}

export function useAddChangeTask(changeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ChangeTaskCreatePayload) =>
      apiRequest<ChangeTask>(`/changes/${changeId}/tasks`, {
        method: "POST",
        body: payload,
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: changeKeys.detail(changeId) }),
  });
}

export function useUpdateChangeTask(changeId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ChangeTaskUpdatePayload) =>
      apiRequest<ChangeTask>(`/changes/${changeId}/tasks/${taskId}`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: changeKeys.detail(changeId) }),
  });
}

// ── Asset queries ─────────────────────────────────────────────────────

export function useAssets(filters?: {
  status?: AssetStatus;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: assetKeys.list(filters?.status),
    queryFn: () =>
      apiRequest<AssetListResponse>("/assets", {
        query: {
          status: filters?.status,
          limit: filters?.limit ?? 100,
          offset: filters?.offset ?? 0,
        },
      }),
  });
}

export function useAsset(id: string | null | undefined) {
  return useQuery({
    queryKey: assetKeys.detail(id ?? ""),
    queryFn: () => apiRequest<AssetRecord>(`/assets/${id}`),
    enabled: !!id,
  });
}

// ── Asset mutations ───────────────────────────────────────────────────

export function useCreateAsset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AssetCreatePayload) =>
      apiRequest<AssetRecord>("/assets", { method: "POST", body: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: assetKeys.all }),
  });
}

export function useUpdateAsset(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AssetUpdatePayload) =>
      apiRequest<AssetRecord>(`/assets/${id}`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: assetKeys.all });
      qc.invalidateQueries({ queryKey: assetKeys.detail(id) });
    },
  });
}

export function useDeleteAsset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/assets/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: assetKeys.all }),
  });
}

export function useAssignAsset(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AssetAssignPayload) =>
      apiRequest<AssetRecord>(`/assets/${id}/assign`, {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: assetKeys.all });
      qc.invalidateQueries({ queryKey: assetKeys.detail(id) });
    },
  });
}

export function useRetireAsset(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AssetRetirePayload) =>
      apiRequest<AssetRecord>(`/assets/${id}/retire`, {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: assetKeys.all });
      qc.invalidateQueries({ queryKey: assetKeys.detail(id) });
    },
  });
}

export function useTransferAsset(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ new_assigned_to_id }: { new_assigned_to_id: string }) =>
      apiRequest<AssetRecord>(`/assets/${id}/transfer`, {
        method: "POST",
        query: { new_assigned_to_id },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: assetKeys.all });
      qc.invalidateQueries({ queryKey: assetKeys.detail(id) });
    },
  });
}

/** A read-only composition of the two API-backed ITSM collections. */
export function useItsmData() {
  const changes = useChanges();
  const assets = useAssets();
  return {
    changes: changes.data?.items ?? [],
    assets: assets.data?.items ?? [],
    isLoading: changes.isLoading || assets.isLoading,
    isError: changes.isError || assets.isError,
  };
}

/** @deprecated Prefer the resource-specific query hooks above. */
export const useItsmState = useItsmData;

// Direct API helpers are retained only for existing event handlers that cannot
// call React hooks. They have no client-side state or browser persistence.
export async function createChange(payload: ChangeCreatePayload): Promise<ChangeRecord> {
  return apiRequest<ChangeRecord>("/changes", { method: "POST", body: payload });
}

export async function updateChange(
  id: string,
  payload: ChangeUpdatePayload,
): Promise<ChangeRecord> {
  return apiRequest<ChangeRecord>(`/changes/${id}`, { method: "PATCH", body: payload });
}

export async function deleteChangeRecord(id: string): Promise<void> {
  await apiRequest<void>(`/changes/${id}`, { method: "DELETE" });
}

export async function transitionChange(
  id: string,
  payload: ChangeTransitionPayload,
): Promise<ChangeRecord> {
  return apiRequest<ChangeRecord>(`/changes/${id}/transition`, {
    method: "POST",
    body: payload,
  });
}

export async function createAsset(payload: AssetCreatePayload): Promise<AssetRecord> {
  return apiRequest<AssetRecord>("/assets", { method: "POST", body: payload });
}

export async function updateAsset(
  id: string,
  payload: AssetUpdatePayload,
): Promise<AssetRecord> {
  return apiRequest<AssetRecord>(`/assets/${id}`, { method: "PATCH", body: payload });
}

export async function deleteAssetRecord(id: string): Promise<void> {
  await apiRequest<void>(`/assets/${id}`, { method: "DELETE" });
}

export async function createAssetsBulk(payloads: AssetCreatePayload[]): Promise<AssetRecord[]> {
  return Promise.all(payloads.map(createAsset));
}

export async function logChangeActivity(
  id: string,
  _actor: string,
  _action: string,
  patch: object = {},
  detail?: string,
): Promise<ChangeRecord> {
  const status = (patch as { status?: unknown }).status;
  if (typeof status === "string") {
    return transitionChange(id, { to_status: status as ChangeStatus, comment: detail });
  }
  return apiRequest<ChangeRecord>(`/changes/${id}`, { method: "PATCH", body: patch });
}

export async function logAssetActivity(
  id: string,
  _actor: string,
  _action: string,
  patch: object = {},
): Promise<AssetRecord> {
  const data = patch as Record<string, unknown>;
  if (data.status === "assigned" && typeof data.assigned_to_id === "string") {
    return apiRequest<AssetRecord>(`/assets/${id}/assign`, {
      method: "POST",
      body: {
        assigned_to_id: data.assigned_to_id,
        assigned_date: typeof data.assigned_date === "string" ? data.assigned_date : undefined,
      },
    });
  }
  if (data.status === "retired" || data.status === "disposed") {
    return apiRequest<AssetRecord>(`/assets/${id}/retire`, {
      method: "POST",
      body: {
        status: data.status,
        retirement_reason:
          typeof data.retirement_reason === "string" ? data.retirement_reason : "",
        retirement_date:
          typeof data.retirement_date === "string"
            ? data.retirement_date
            : new Date().toISOString().slice(0, 10),
      },
    });
  }
  return apiRequest<AssetRecord>(`/assets/${id}`, { method: "PATCH", body: patch });
}
