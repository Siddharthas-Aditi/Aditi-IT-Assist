/**
 * Bridge between support (tickets, chat) and the ITSM modules.
 *
 * The ITSM data is now backend-backed. This module provides synchronous
 * helpers for the support panel; real queries should use the API hooks
 * from ./api.ts directly.
 */

import { PEOPLE } from './data/reference';
import type { AssetRecord, ChangeRecord } from './api-types';

/** Resolve a directory person id from a login email. */
export function personIdForEmail(email: string | null | undefined): string | null {
  if (!email) return null;
  const needle = email.trim().toLowerCase();
  return PEOPLE.find((p) => p.email.toLowerCase() === needle)?.id ?? null;
}

export function personIdForName(name: string | null | undefined): string | null {
  if (!name) return null;
  const needle = name.trim().toLowerCase();
  if (!needle) return null;
  const exact = PEOPLE.find((p) => p.name.toLowerCase() === needle);
  if (exact) return exact.id;
  const first = needle.split(/\s+/)[0];
  const byLocalPart = PEOPLE.find((p) => p.email.split('@')[0].toLowerCase() === first);
  return byLocalPart?.id ?? null;
}

/**
 * Filter assets from a pre-loaded list to those assigned to a person.
 * Components that need this should fetch assets from the API first.
 */
export function assetsForPerson(
  assets: AssetRecord[],
  identity: { email?: string | null; name?: string | null },
): AssetRecord[] {
  const personId = personIdForEmail(identity.email) ?? personIdForName(identity.name);
  if (!personId) return [];
  return assets
    .filter((a) => a.assigned_to_id === personId)
    .filter((a) => a.status !== 'retired' && a.status !== 'disposed')
    .sort((a, b) => a.asset_type.localeCompare(b.asset_type));
}

/** Query string that pre-fills the change form from a ticket. */
export function changeFromTicketHref(params: {
  ticketId: string;
  ticketNumber: string;
  subject?: string;
}): string {
  const qs = new URLSearchParams({
    sourceTicketId: params.ticketId,
    sourceTicketNumber: params.ticketNumber,
    ...(params.subject ? { subject: params.subject } : {}),
  });
  return `/operations/changes/new?${qs}`;
}

/**
 * Changes related to a ticket from a pre-loaded list.
 * Components should fetch changes from the API directly.
 */
export function changesForTicket(changes: ChangeRecord[], ticketId: string): ChangeRecord[] {
  return changes.filter((c) => c.source_ticket_id === ticketId);
}
