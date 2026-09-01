/**
 * Ticket-side panel for the ITSM modules.
 *
 * Dropped into the specialist ticket workspace and the live-chat sidebar so a
 * specialist can see the requester's kit and changes raised from this ticket —
 * without leaving the ticket.
 */

import { useMemo } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, GitPullRequestArrow, Laptop } from "lucide-react";

import { StatusBadge } from "./components/ui";
import { isExpiringSoon } from "./data/rules";
import { useItsmData } from "./data/store";
import {
  assetsForPerson,
  changesForTicket,
  changeFromTicketHref,
} from "./integration";
import { ASSET_STATUS_LABELS, CHANGE_STATUS_LABELS } from "./api-types";

interface TicketItsmPanelProps {
  ticketId: string;
  ticketNumber: string;
  subject: string;
  requesterEmail?: string | null;
  requesterName?: string | null;
  description?: string | null;
  category?: string | null;
  /** Who is performing actions, for the activity trail. */
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
  compact = false,
}: TicketItsmPanelProps) {
  const { assets, changes } = useItsmData();

  const ownedAssets = useMemo(
    () =>
      assetsForPerson(assets, { email: requesterEmail, name: requesterName }),
    [assets, requesterEmail, requesterName],
  );

  const linkedChanges = useMemo(
    () => changesForTicket(changes, ticketId),
    [changes, ticketId],
  );

  return (
    <section className="itsm-root space-y-3 rounded-lg border border-slate-200 bg-white p-3">
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-[13px] font-semibold text-slate-800">
          Assets &amp; Changes
        </h3>
        <Link
          to={changeFromTicketHref({ ticketId, ticketNumber, subject })}
          className="inline-flex items-center gap-1 rounded-md bg-sky-600 px-2 py-1 text-[11.5px] font-medium text-white transition-colors hover:bg-sky-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
        >
          <GitPullRequestArrow size={12} /> Raise change
        </Link>
      </header>

      {/* Requester's kit — visible before anyone has to ask "what are you on?" */}
      <div>
        <p className="mb-1 text-[10.5px] uppercase tracking-wide text-slate-500">
          {requesterName ? `${requesterName}'s assets` : "Requester assets"}
        </p>
        {ownedAssets.length === 0 ? (
          <p className="text-[12px] text-slate-500">
            No assets recorded for this employee.
          </p>
        ) : (
          <ul className="space-y-1">
            {ownedAssets.map((a) => (
              <li
                key={a.id}
                className="flex items-center gap-2 rounded border border-slate-200 bg-slate-50 px-2 py-1.5"
              >
                <Laptop
                  size={12}
                  className="shrink-0 text-slate-400"
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <Link
                    to={`/itsm/assets/${a.id}`}
                    className="text-[12px] font-medium text-sky-700 hover:underline"
                  >
                    {a.asset_tag}
                  </Link>
                  {!compact && (
                    <p className="truncate text-[11px] text-slate-500">
                      {a.model || a.asset_type}
                      {a.serial_number ? ` · ${a.serial_number}` : ""}
                    </p>
                  )}
                </div>
                {isExpiringSoon(a.warranty_expiry) && (
                  <span
                    title="Warranty expiring within 90 days"
                    className="shrink-0 text-amber-600"
                  >
                    <AlertTriangle size={12} />
                  </span>
                )}
                <StatusBadge
                  status={ASSET_STATUS_LABELS[a.status] ?? a.status}
                />
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
              <li
                key={c.id}
                className="flex items-center justify-between gap-2"
              >
                <Link
                  to={`/itsm/changes/${c.id}`}
                  className="min-w-0 flex-1 truncate text-[12px] text-sky-700 hover:underline"
                >
                  {c.change_number} — {c.title}
                </Link>
                <StatusBadge
                  status={CHANGE_STATUS_LABELS[c.status] ?? c.status}
                />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
