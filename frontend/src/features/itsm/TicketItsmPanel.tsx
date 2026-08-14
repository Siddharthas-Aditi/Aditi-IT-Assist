/**
 * Ticket-side panel for the ITSM modules.
 *
 * Dropped into the specialist ticket workspace and the live-chat sidebar so a
 * specialist can see the requester's kit, attach the relevant asset to the
 * ticket, and escalate into a change — without leaving the ticket.
 */

import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, GitPullRequestArrow, Laptop, Plus, X } from 'lucide-react';

import { StatusBadge } from './components/ui';
import { isExpiringSoon } from './data/rules';
import { linkTicketAsset, unlinkTicketAsset, useItsmState } from './data/store';
import { assetsForPerson, changeFromTicketHref } from './integration';

interface TicketItsmPanelProps {
  ticketId: string;
  ticketNumber: string;
  subject: string;
  requesterEmail?: string | null;
  requesterName?: string | null;
  description?: string | null;
  category?: string | null;
  /** Who is performing the link, for the asset activity trail. */
  actorName: string;
  /** Chat sidebars are narrower than the ticket workspace. */
  compact?: boolean;
}

export function TicketItsmPanel({
  ticketId,
  ticketNumber,
  subject,
  requesterEmail,
  requesterName,
  description,
  category,
  actorName,
  compact = false,
}: TicketItsmPanelProps) {
  const { assets, changes, ticketAssetLinks } = useItsmState();
  const [showPicker, setShowPicker] = useState(false);
  const [query, setQuery] = useState('');

  const ownedAssets = useMemo(
    () => assetsForPerson({ email: requesterEmail, name: requesterName }),
    [requesterEmail, requesterName],
  );

  const linked = useMemo(() => {
    const ids = new Set(
      ticketAssetLinks.filter((l) => l.ticketId === ticketId).map((l) => l.assetId),
    );
    return assets.filter((a) => ids.has(a.id));
  }, [assets, ticketAssetLinks, ticketId]);

  const linkedChanges = useMemo(
    () => changes.filter((c) => c.sourceTicketId === ticketId),
    [changes, ticketId],
  );

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];
    const linkedIds = new Set(linked.map((a) => a.id));
    return assets
      .filter((a) => !linkedIds.has(a.id))
      .filter(
        (a) =>
          a.assetTag.toLowerCase().includes(needle) ||
          a.name.toLowerCase().includes(needle) ||
          a.serialNumber.toLowerCase().includes(needle),
      )
      .slice(0, 6);
  }, [query, assets, linked]);

  function link(assetId: string) {
    linkTicketAsset(ticketId, ticketNumber, assetId, actorName);
    setQuery('');
    setShowPicker(false);
  }

  const linkIdFor = (assetId: string) =>
    ticketAssetLinks.find((l) => l.ticketId === ticketId && l.assetId === assetId)?.id;

  return (
    <section className="itsm-root space-y-3 rounded-lg border border-slate-200 bg-white p-3">
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-[13px] font-semibold text-slate-800">Assets &amp; Changes</h3>
        <Link
          to={changeFromTicketHref({
            ticketId,
            ticketNumber,
            subject,
            description: description ?? undefined,
            category: category ?? undefined,
            requesterEmail: requesterEmail ?? undefined,
            assetIds: linked.map((a) => a.id),
          })}
          className="inline-flex items-center gap-1 rounded-md bg-sky-600 px-2 py-1 text-[11.5px] font-medium text-white transition-colors hover:bg-sky-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
        >
          <GitPullRequestArrow size={12} /> Raise change
        </Link>
      </header>

      {/* Requester's kit — visible before anyone has to ask "what are you on?" */}
      <div>
        <p className="mb-1 text-[10.5px] uppercase tracking-wide text-slate-500">
          {requesterName ? `${requesterName}'s assets` : 'Requester assets'}
        </p>
        {ownedAssets.length === 0 ? (
          <p className="text-[12px] text-slate-500">
            No assets recorded for this employee.
          </p>
        ) : (
          <ul className="space-y-1">
            {ownedAssets.map((a) => {
              const isLinked = linked.some((l) => l.id === a.id);
              return (
                <li
                  key={a.id}
                  className="flex items-center gap-2 rounded border border-slate-200 bg-slate-50 px-2 py-1.5"
                >
                  <Laptop size={12} className="shrink-0 text-slate-400" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/itsm/assets/${a.id}`}
                      className="text-[12px] font-medium text-sky-700 hover:underline"
                    >
                      {a.assetTag}
                    </Link>
                    {!compact && (
                      <p className="truncate text-[11px] text-slate-500">
                        {a.model || a.assetType}
                        {a.serialNumber ? ` · ${a.serialNumber}` : ''}
                      </p>
                    )}
                  </div>
                  {isExpiringSoon(a.warrantyExpiry) && (
                    <span
                      title="Warranty expiring within 90 days"
                      className="shrink-0 text-amber-600"
                    >
                      <AlertTriangle size={12} />
                    </span>
                  )}
                  {isLinked ? (
                    <span className="shrink-0 text-[10.5px] text-emerald-700">Linked</span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => link(a.id)}
                      className="shrink-0 rounded px-1.5 py-0.5 text-[10.5px] text-slate-600 hover:bg-slate-200 hover:text-slate-900 focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
                    >
                      Link
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Assets attached to this ticket (may include kit the requester doesn't own). */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <p className="text-[10.5px] uppercase tracking-wide text-slate-500">
            Linked to this ticket ({linked.length})
          </p>
          <button
            type="button"
            onClick={() => setShowPicker((s) => !s)}
            aria-expanded={showPicker}
            className="inline-flex items-center gap-1 rounded px-1 text-[11px] text-sky-700 hover:underline focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
          >
            <Plus size={11} /> Add
          </button>
        </div>

        {showPicker && (
          <div className="mb-1.5">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search any asset by tag, name, or serial…"
              aria-label="Search assets to link to this ticket"
              className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-[12px] text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
            {matches.length > 0 && (
              <ul className="mt-1 overflow-hidden rounded-md border border-slate-200">
                {matches.map((a) => (
                  <li key={a.id}>
                    <button
                      type="button"
                      onClick={() => link(a.id)}
                      className="block w-full px-2 py-1 text-left text-[11.5px] text-slate-700 hover:bg-slate-50"
                    >
                      <span className="font-medium text-sky-700">{a.assetTag}</span> — {a.name}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {linked.length === 0 ? (
          <p className="text-[12px] text-slate-500">Nothing linked yet.</p>
        ) : (
          <ul className="space-y-1">
            {linked.map((a) => (
              <li
                key={a.id}
                className="flex items-center gap-2 rounded border border-slate-200 px-2 py-1.5"
              >
                <div className="min-w-0 flex-1">
                  <Link
                    to={`/itsm/assets/${a.id}`}
                    className="text-[12px] font-medium text-sky-700 hover:underline"
                  >
                    {a.assetTag}
                  </Link>
                  {!compact && (
                    <p className="truncate text-[11px] text-slate-500">{a.name}</p>
                  )}
                </div>
                <StatusBadge status={a.assetState} />
                <button
                  type="button"
                  onClick={() => {
                    const id = linkIdFor(a.id);
                    if (id) unlinkTicketAsset(id);
                  }}
                  aria-label={`Unlink ${a.assetTag} from this ticket`}
                  className="shrink-0 rounded p-0.5 text-slate-400 hover:text-red-600 focus:outline-none focus-visible:ring-1 focus-visible:ring-red-500"
                >
                  <X size={12} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {linkedChanges.length > 0 && (
        <div>
          <p className="mb-1 text-[10.5px] uppercase tracking-wide text-slate-500">
            Changes raised from this ticket
          </p>
          <ul className="space-y-1">
            {linkedChanges.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-2">
                <Link
                  to={`/itsm/changes/${c.id}`}
                  className="min-w-0 flex-1 truncate text-[12px] text-sky-700 hover:underline"
                >
                  {c.changeId} — {c.subject}
                </Link>
                <StatusBadge status={c.status} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
