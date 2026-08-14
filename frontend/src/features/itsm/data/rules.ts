/**
 * Workflow rules for changes and assets — pure functions, no I/O.
 *
 * Both boards and both detail pages enforce transitions through here, so a
 * drag-and-drop and a button click can never disagree about what is legal.
 */

import type { Asset, AssetState, Change, ChangeStatus } from './types';

// ── Change workflow ────────────────────────────────────────────────────

/** Legal next statuses, keyed by current status. */
const CHANGE_TRANSITIONS: Record<ChangeStatus, ChangeStatus[]> = {
  Draft: ['Open', 'Planning', 'Cancelled'],
  Open: ['Planning', 'Pending Approval', 'Cancelled'],
  Planning: ['Pending Approval', 'Scheduled', 'Cancelled'],
  'Pending Approval': ['Scheduled', 'Rejected', 'Planning', 'Cancelled'],
  Scheduled: ['In Progress', 'Cancelled', 'Planning'],
  'In Progress': ['Completed', 'Cancelled'],
  Completed: [],
  Rejected: ['Planning'],
  Cancelled: [],
};

export function allowedChangeTransitions(from: ChangeStatus): ChangeStatus[] {
  return CHANGE_TRANSITIONS[from] ?? [];
}

export interface RuleResult {
  ok: boolean;
  reason?: string;
}

/**
 * Gate a change status transition.
 *
 * Beyond the state graph this enforces the two business rules that matter:
 * a Standard change may reach Scheduled without approval, anything else must
 * clear its approval stages first; and completing requires closure notes.
 */
export function canMoveChange(change: Change, to: ChangeStatus): RuleResult {
  if (change.status === to) return { ok: true };

  if (!allowedChangeTransitions(change.status).includes(to)) {
    return { ok: false, reason: `A change cannot move from ${change.status} to ${to}.` };
  }

  if (to === 'Scheduled' && change.changeType !== 'Standard') {
    const outstanding = change.approvals.filter((a) => a.decision !== 'Approved');
    if (outstanding.length > 0) {
      return {
        ok: false,
        reason: `All approval stages must be approved before scheduling a ${change.changeType} change.`,
      };
    }
  }

  if (to === 'In Progress' && !change.plannedStart) {
    return { ok: false, reason: 'Set a planned start before starting implementation.' };
  }

  if (to === 'Completed' && !change.closureNotes.trim()) {
    return { ok: false, reason: 'Closure notes are required before completing a change.' };
  }

  return { ok: true };
}

/** Where a newly submitted change lands, by type. */
export function initialStatusFor(changeType: Change['changeType']): ChangeStatus {
  // Standard changes are pre-authorised, so they enter planning ready to be
  // scheduled. Normal and Emergency both need an approval decision first.
  return changeType === 'Standard' ? 'Planning' : 'Pending Approval';
}

// ── Asset lifecycle ────────────────────────────────────────────────────

const TERMINAL_ASSET_STATES: AssetState[] = ['Retired', 'Disposed'];
const ASSIGNMENT_STATES: AssetState[] = ['Assigned', 'In Use'];

export function requiresAssignee(state: AssetState): boolean {
  return ASSIGNMENT_STATES.includes(state);
}

export function requiresRetirementReason(state: AssetState): boolean {
  return TERMINAL_ASSET_STATES.includes(state);
}

/**
 * Gate an asset lifecycle transition.
 *
 * `patch` carries the values the caller is about to apply, so a board drop can
 * be rejected before it opens a dialog and a form submit can be validated with
 * exactly the same rule.
 */
export function canMoveAsset(
  asset: Asset,
  to: AssetState,
  patch: Partial<Asset> = {},
): RuleResult {
  if (asset.assetState === to) return { ok: true };

  const merged = { ...asset, ...patch };

  if (TERMINAL_ASSET_STATES.includes(asset.assetState) && ASSIGNMENT_STATES.includes(to)) {
    return {
      ok: false,
      reason: `A ${asset.assetState.toLowerCase()} asset cannot be assigned. Return it to stock first.`,
    };
  }

  if (requiresAssignee(to)) {
    if (!merged.assignedTo) {
      return { ok: false, reason: `"Assigned To" is required to move an asset to ${to}.` };
    }
    if (!merged.assignedDate) {
      return { ok: false, reason: `"Assigned Date" is required to move an asset to ${to}.` };
    }
  }

  if (requiresRetirementReason(to)) {
    if (!merged.retirementReason?.trim()) {
      return { ok: false, reason: `A reason is required to mark an asset ${to}.` };
    }
    if (!merged.retirementDate) {
      return { ok: false, reason: `A date is required to mark an asset ${to}.` };
    }
  }

  return { ok: true };
}

// ── Expiry helpers ─────────────────────────────────────────────────────

export const EXPIRY_WINDOW_DAYS = 90;

export function daysUntil(date: string | null): number | null {
  if (!date) return null;
  const target = new Date(date).getTime();
  if (Number.isNaN(target)) return null;
  return Math.ceil((target - Date.now()) / 86400000);
}

/** True when a date falls inside the 90-day highlight window (or has passed). */
export function isExpiringSoon(date: string | null): boolean {
  const days = daysUntil(date);
  return days !== null && days <= EXPIRY_WINDOW_DAYS;
}

export function isExpired(date: string | null): boolean {
  const days = daysUntil(date);
  return days !== null && days < 0;
}
