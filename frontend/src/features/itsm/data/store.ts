/**
 * In-memory ITSM store with sessionStorage persistence.
 *
 * Deliberately framework-light: a snapshot + listener set consumed through
 * `useSyncExternalStore`. Every mutation replaces the snapshot, so the swap to
 * a real API later means changing these functions, not the pages.
 *
 * Persistence is sessionStorage (not localStorage) because the spec calls for
 * state to survive navigation and reloads within a browser session only.
 */

import { useSyncExternalStore } from 'react';

import { seedAssets } from './mock-assets';
import { seedChanges } from './mock-changes';
import { seedTemplates } from './mock-templates';
import type { Asset, Change, ChangeTemplate, TicketAssetLink } from './types';

const STORAGE_KEY = 'aditi.itsm.state.v1';

export interface ItsmState {
  assets: Asset[];
  changes: Change[];
  templates: ChangeTemplate[];
  ticketAssetLinks: TicketAssetLink[];
}

function buildSeed(): ItsmState {
  const assets = seedAssets();
  const assetIdByTag = Object.fromEntries(assets.map((a) => [a.assetTag, a.id]));
  return {
    assets,
    changes: seedChanges(assetIdByTag),
    templates: seedTemplates(),
    ticketAssetLinks: [],
  };
}

function load(): ItsmState {
  if (typeof window === 'undefined') return buildSeed();
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return buildSeed();
    const parsed = JSON.parse(raw) as Partial<ItsmState>;
    if (!parsed.assets?.length || !parsed.changes?.length) return buildSeed();
    return {
      assets: parsed.assets,
      changes: parsed.changes,
      templates: parsed.templates ?? seedTemplates(),
      ticketAssetLinks: parsed.ticketAssetLinks ?? [],
    };
  } catch {
    // Corrupt or unreadable session state must never block the module.
    return buildSeed();
  }
}

let state: ItsmState = load();
const listeners = new Set<() => void>();

function persist(): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Quota or private-mode failures are non-fatal — the in-memory copy stands.
  }
}

function setState(next: ItsmState): void {
  state = next;
  persist();
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): ItsmState {
  return state;
}

/** Subscribe a component to the whole store. */
export function useItsmState(): ItsmState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

export function resetItsmStore(): void {
  setState(buildSeed());
}

// ── Ids ────────────────────────────────────────────────────────────────

let counter = 0;
export function newId(prefix: string): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter}`;
}

function nextChangeId(): string {
  const max = state.changes.reduce((acc, c) => {
    const n = Number.parseInt(c.changeId.replace(/\D/g, ''), 10);
    return Number.isFinite(n) && n > acc ? n : acc;
  }, 1000);
  return `CHG-${max + 1}`;
}

export function nowIso(): string {
  return new Date().toISOString();
}

// ── Changes ────────────────────────────────────────────────────────────

export function createChange(draft: Omit<Change, 'id' | 'changeId' | 'createdAt' | 'updatedAt'>): Change {
  const change: Change = {
    ...draft,
    id: newId('change'),
    changeId: nextChangeId(),
    createdAt: nowIso(),
    updatedAt: nowIso(),
  };
  setState({ ...state, changes: [change, ...state.changes] });
  return change;
}

export function updateChange(id: string, patch: Partial<Change>): Change | null {
  let updated: Change | null = null;
  const changes = state.changes.map((c) => {
    if (c.id !== id) return c;
    updated = { ...c, ...patch, updatedAt: nowIso() };
    return updated;
  });
  if (updated) setState({ ...state, changes });
  return updated;
}

/** Append an activity entry alongside an optional field patch. */
export function logChangeActivity(
  id: string,
  actor: string,
  action: string,
  patch: Partial<Change> = {},
  detail?: string,
): Change | null {
  const current = state.changes.find((c) => c.id === id);
  if (!current) return null;
  return updateChange(id, {
    ...patch,
    activity: [
      ...current.activity,
      { id: newId('act'), at: nowIso(), actor, action, detail },
    ],
  });
}

export function deleteChange(id: string): void {
  setState({ ...state, changes: state.changes.filter((c) => c.id !== id) });
}

export function getChange(id: string): Change | undefined {
  return state.changes.find((c) => c.id === id || c.changeId === id);
}

// ── Templates ──────────────────────────────────────────────────────────

export function createTemplate(draft: Omit<ChangeTemplate, 'id' | 'createdAt'>): ChangeTemplate {
  const tpl: ChangeTemplate = { ...draft, id: newId('tpl'), createdAt: nowIso() };
  setState({ ...state, templates: [tpl, ...state.templates] });
  return tpl;
}

export function updateTemplate(id: string, patch: Partial<ChangeTemplate>): void {
  setState({
    ...state,
    templates: state.templates.map((t) => (t.id === id ? { ...t, ...patch } : t)),
  });
}

export function cloneTemplate(id: string): ChangeTemplate | null {
  const source = state.templates.find((t) => t.id === id);
  if (!source) return null;
  return createTemplate({ ...source, name: `${source.name} (copy)`, lastUsedAt: null });
}

export function touchTemplate(id: string): void {
  updateTemplate(id, { lastUsedAt: nowIso() });
}

// ── Assets ─────────────────────────────────────────────────────────────

export function createAsset(draft: Omit<Asset, 'id' | 'createdAt' | 'updatedAt'>): Asset {
  const asset: Asset = {
    ...draft,
    id: newId('asset'),
    createdAt: nowIso(),
    updatedAt: nowIso(),
  };
  setState({ ...state, assets: [asset, ...state.assets] });
  return asset;
}

export function updateAsset(id: string, patch: Partial<Asset>): Asset | null {
  let updated: Asset | null = null;
  const assets = state.assets.map((a) => {
    if (a.id !== id) return a;
    updated = { ...a, ...patch, updatedAt: nowIso() };
    return updated;
  });
  if (updated) setState({ ...state, assets });
  return updated;
}

export function logAssetActivity(
  id: string,
  actor: string,
  action: string,
  patch: Partial<Asset> = {},
  detail?: string,
): Asset | null {
  const current = state.assets.find((a) => a.id === id);
  if (!current) return null;
  return updateAsset(id, {
    ...patch,
    activity: [
      ...current.activity,
      { id: newId('act'), at: nowIso(), actor, action, detail },
    ],
  });
}

export function deleteAsset(id: string): void {
  setState({ ...state, assets: state.assets.filter((a) => a.id !== id) });
}

export function getAsset(id: string): Asset | undefined {
  return state.assets.find((a) => a.id === id || a.assetTag === id);
}

/** Uniqueness guard for asset tags — `exceptId` skips the record being edited. */
export function isAssetTagTaken(tag: string, exceptId?: string): boolean {
  const needle = tag.trim().toLowerCase();
  if (!needle) return false;
  return state.assets.some(
    (a) => a.id !== exceptId && a.assetTag.trim().toLowerCase() === needle,
  );
}

/** Serial numbers only warn — duplicates happen legitimately during RMA swaps. */
export function findSerialDuplicate(serial: string, exceptId?: string): Asset | undefined {
  const needle = serial.trim().toLowerCase();
  if (!needle) return undefined;
  return state.assets.find(
    (a) => a.id !== exceptId && a.serialNumber.trim().toLowerCase() === needle,
  );
}

// ── Ticket ↔ asset links ───────────────────────────────────────────────

export function linkTicketAsset(
  ticketId: string,
  ticketNumber: string,
  assetId: string,
  linkedBy: string,
): TicketAssetLink | null {
  const exists = state.ticketAssetLinks.some(
    (l) => l.ticketId === ticketId && l.assetId === assetId,
  );
  if (exists) return null;

  const link: TicketAssetLink = {
    id: newId('tal'),
    ticketId,
    ticketNumber,
    assetId,
    linkedBy,
    createdAt: nowIso(),
  };
  setState({ ...state, ticketAssetLinks: [...state.ticketAssetLinks, link] });

  // Mirror the link onto the asset's own timeline so the CMDB record shows it.
  logAssetActivity(assetId, linkedBy, `Linked to ticket ${ticketNumber}`);
  return link;
}

export function unlinkTicketAsset(linkId: string): void {
  const link = state.ticketAssetLinks.find((l) => l.id === linkId);
  setState({
    ...state,
    ticketAssetLinks: state.ticketAssetLinks.filter((l) => l.id !== linkId),
  });
  if (link) {
    logAssetActivity(link.assetId, link.linkedBy, `Unlinked from ticket ${link.ticketNumber}`);
  }
}

export function assetsForTicket(ticketId: string): Asset[] {
  const ids = new Set(
    state.ticketAssetLinks.filter((l) => l.ticketId === ticketId).map((l) => l.assetId),
  );
  return state.assets.filter((a) => ids.has(a.id));
}

/** Read the current snapshot outside React (validation, exports). */
export function snapshot(): ItsmState {
  return state;
}
