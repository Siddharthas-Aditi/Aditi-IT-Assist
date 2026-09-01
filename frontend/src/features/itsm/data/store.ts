/**
 * ITSM store — thin API wrapper. sessionStorage removed; all state is in the
 * backend (migration 020: /changes, /assets).
 */

import { apiRequest } from "@/lib/api";
import { useAssets, useChanges } from "../api";
import type { AssetRecord, ChangeRecord } from "../api-types";
import { SEED_LOCATIONS } from "./reference";
import type { LocationRef } from "./types";

export type {
  AssetRecord as ApiAsset,
  ChangeRecord as ApiChange,
} from "../api-types";

export { useAssets, useChanges } from "../api";

export function useItsmData() {
  const changes = useChanges();
  const assets = useAssets();
  return {
    changes: changes.data?.items ?? [],
    assets: assets.data?.items ?? [],
    isLoading: changes.isLoading || assets.isLoading,
    isError: changes.isError || assets.isError,
    // Location ref data not yet in backend — provide seed data for compat
    locations: SEED_LOCATIONS as LocationRef[],
    templates: [] as never[],
    ticketAssetLinks: [] as never[],
  };
}

/** @deprecated Use useItsmData() or named hooks from ../api.ts */
export const useItsmState = useItsmData;

export async function createChange(
  payload: Omit<
    ChangeRecord,
    | "id"
    | "change_number"
    | "created_at"
    | "updated_at"
    | "approvals"
    | "tasks"
    | "events"
  >,
): Promise<ChangeRecord> {
  return apiRequest<ChangeRecord>("/changes", {
    method: "POST",
    body: payload,
  });
}

export async function updateChange(
  id: string,
  patch: Partial<ChangeRecord>,
): Promise<ChangeRecord> {
  return apiRequest<ChangeRecord>(`/changes/${id}`, {
    method: "PATCH",
    body: patch,
  });
}

export async function deleteChange(id: string): Promise<void> {
  return apiRequest<void>(`/changes/${id}`, { method: "DELETE" });
}

export async function logChangeActivity(
  id: string,
  _actor: string,
  _action: string,
  patch: Partial<ChangeRecord> & Record<string, unknown> = {},
  detail?: string,
): Promise<ChangeRecord> {
  if (patch.status) {
    return apiRequest<ChangeRecord>(`/changes/${id}/transition`, {
      method: "POST",
      body: { to_status: patch.status, comment: detail ?? "" },
    });
  }
  return apiRequest<ChangeRecord>(`/changes/${id}`, {
    method: "PATCH",
    body: patch,
  });
}

export async function createAsset(
  payload: Omit<AssetRecord, "id" | "created_at" | "updated_at" | "events">,
): Promise<AssetRecord> {
  return apiRequest<AssetRecord>("/assets", { method: "POST", body: payload });
}

export async function updateAsset(
  id: string,
  patch: Partial<AssetRecord>,
): Promise<AssetRecord> {
  return apiRequest<AssetRecord>(`/assets/${id}`, {
    method: "PATCH",
    body: patch,
  });
}

export async function deleteAsset(id: string): Promise<void> {
  return apiRequest<void>(`/assets/${id}`, { method: "DELETE" });
}

export async function logAssetActivity(
  id: string,
  _actor: string,
  _action: string,
  patch: Partial<AssetRecord> & Record<string, unknown> = {},
  _detail?: string,
): Promise<AssetRecord> {
  if (
    patch.status === "assigned" &&
    (patch as { assigned_to_id?: string }).assigned_to_id
  ) {
    return apiRequest<AssetRecord>(`/assets/${id}/assign`, {
      method: "POST",
      body: {
        assigned_to_id: (patch as { assigned_to_id?: string }).assigned_to_id,
        assigned_date: (patch as { assigned_date?: string }).assigned_date,
      },
    });
  }
  if (patch.status === "retired" || patch.status === "disposed") {
    return apiRequest<AssetRecord>(`/assets/${id}/retire`, {
      method: "POST",
      body: {
        status: patch.status,
        retirement_reason:
          (patch as { retirement_reason?: string }).retirement_reason ?? "",
        retirement_date:
          (patch as { retirement_date?: string }).retirement_date ??
          new Date().toISOString().split("T")[0],
      },
    });
  }
  return apiRequest<AssetRecord>(`/assets/${id}`, {
    method: "PATCH",
    body: patch,
  });
}

export async function createAssetsBulk(
  drafts: Omit<AssetRecord, "id" | "created_at" | "updated_at" | "events">[],
): Promise<AssetRecord[]> {
  return Promise.all(drafts.map((d) => createAsset(d)));
}

export function snapshot() {
  throw new Error(
    "snapshot() removed — use useChanges() / useAssets() from ../api.ts.",
  );
}

export function createLocation(_: unknown) {
  return _;
}
export function updateLocation(_id: string, _patch: unknown) {
  return;
}
export function deleteLocation(_id: string) {
  return;
}
export function createTemplate(_: unknown) {
  return _;
}
export function updateTemplate(_id: string, _patch: unknown) {
  return;
}
export function cloneTemplate(_id: string) {
  return null;
}
export function touchTemplate(_id: string) {
  return;
}
export function linkTicketAsset(_: unknown) {
  return _;
}
export function unlinkTicketAsset(_id: string) {
  return;
}
export function newId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
export function nowIso(): string {
  return new Date().toISOString();
}
export function isAssetTagTaken(_tag: string, _exceptId?: string): boolean {
  return false;
}
export function findSerialDuplicate(_serial: string, _exceptId?: string) {
  return undefined;
}
export function getAsset(_id: string) {
  return undefined;
}
export function getChange(_id: string) {
  return undefined;
}
export function resetItsmStore() {
  return;
}
