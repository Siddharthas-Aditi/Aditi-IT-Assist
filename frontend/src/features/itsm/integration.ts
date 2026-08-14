/**
 * Bridge between support (tickets, chat) and the ITSM modules.
 *
 * Tickets and users come from the backend; changes and assets live in this
 * module's store. The join is by **email**, because that is the one identifier
 * both sides genuinely share — asset owners are seeded against the same
 * corporate addresses the auth system issues.
 */

import { PEOPLE } from './data/reference';
import { snapshot } from './data/store';
import type { Asset } from './data/types';

/** Resolve a directory person id from a login email. */
export function personIdForEmail(email: string | null | undefined): string | null {
  if (!email) return null;
  const needle = email.trim().toLowerCase();
  return PEOPLE.find((p) => p.email.toLowerCase() === needle)?.id ?? null;
}

/**
 * Resolve by display name, for the surfaces that only carry a name.
 *
 * Falls back to matching the first name against the email local part, because
 * directory display names ("Naresh") and asset-owner records ("Naresh Iyer")
 * don't always agree while the mailbox does.
 */
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
 * Assets a person holds. Retired and disposed records are excluded: a
 * specialist troubleshooting a live issue only cares about kit still in
 * service.
 */
export function assetsForPerson(identity: {
  email?: string | null;
  name?: string | null;
}): Asset[] {
  const personId = personIdForEmail(identity.email) ?? personIdForName(identity.name);
  if (!personId) return [];
  return snapshot()
    .assets.filter((a) => a.assignedTo === personId)
    .filter((a) => a.assetState !== 'Retired' && a.assetState !== 'Disposed')
    .sort((a, b) => a.assetType.localeCompare(b.assetType));
}

/** Query string that pre-fills the change form from a ticket. */
export function changeFromTicketHref(params: {
  ticketId: string;
  ticketNumber: string;
  subject: string;
  description?: string;
  category?: string;
  requesterEmail?: string;
  assetIds?: string[];
}): string {
  const q = new URLSearchParams({
    ticketId: params.ticketId,
    ticketNumber: params.ticketNumber,
    subject: params.subject,
  });
  if (params.description) q.set('description', params.description);
  if (params.category) q.set('category', params.category);
  const requesterId = personIdForEmail(params.requesterEmail);
  if (requesterId) q.set('requesterId', requesterId);
  if (params.assetIds?.length) q.set('assetIds', params.assetIds.join(','));
  return `/itsm/changes/new?${q.toString()}`;
}

/** Changes raised from a given ticket. */
export function changesForTicket(ticketId: string) {
  return snapshot().changes.filter((c) => c.sourceTicketId === ticketId);
}
