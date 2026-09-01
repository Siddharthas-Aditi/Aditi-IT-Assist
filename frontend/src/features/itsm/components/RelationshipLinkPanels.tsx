import { Link } from "react-router-dom";

import type { LinkedAsset, LinkedChange, LinkedTicket } from "../api-types";
import { EmptyState, Panel, StatusBadge } from "../components/ui";

interface Loadable<T> {
  data?: { items: T[] };
  isError: boolean;
  isLoading: boolean;
}

function LoadingLinks({ label }: { label: string }) {
  return <p className="text-[13px] text-slate-500">Loading {label.toLowerCase()}…</p>;
}

function UnavailableLinks({ detail }: { detail: string }) {
  return (
    <EmptyState
      title="Relationship data is unavailable"
      description={detail}
    />
  );
}

export function ChangeAssetLinksPanel({ query }: { query: Loadable<LinkedAsset> }) {
  const assets = query.data?.items ?? [];
  return (
    <Panel title="Associated assets">
      {query.isLoading ? (
        <LoadingLinks label="associated assets" />
      ) : query.isError ? (
        <UnavailableLinks detail="The linked-asset service could not be reached. This does not mean the change has no associated assets." />
      ) : assets.length === 0 ? (
        <EmptyState title="No associated assets" description="No assets are linked to this change." />
      ) : (
        <ul className="divide-y divide-slate-200">
          {assets.map((asset) => (
            <li key={asset.id} className="flex items-center justify-between gap-3 py-2">
              <Link to={`/itsm/assets/${asset.id}`} className="text-[13px] text-sky-700 hover:underline">
                {asset.asset_tag} — {asset.name}
              </Link>
              <StatusBadge status={asset.status} />
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function AssetAssociationPanels({
  changeQuery,
  ticketQuery,
}: {
  changeQuery: Loadable<LinkedChange>;
  ticketQuery: Loadable<LinkedTicket>;
}) {
  const changes = changeQuery.data?.items ?? [];
  const tickets = ticketQuery.data?.items ?? [];
  return (
    <>
      <Panel title="Linked support tickets">
        {ticketQuery.isLoading ? (
          <LoadingLinks label="linked support tickets" />
        ) : ticketQuery.isError ? (
          <UnavailableLinks detail="Ticket links are restricted to IT staff because a ticket title can disclose another employee’s support issue. This does not mean no tickets are linked." />
        ) : tickets.length === 0 ? (
          <EmptyState title="No linked support tickets" description="No support tickets are linked to this asset." />
        ) : (
          <ul className="divide-y divide-slate-200">
            {tickets.map((ticket) => (
              <li key={ticket.id} className="flex items-center justify-between gap-3 py-2">
                <Link to={`/operations/tickets/${ticket.id}`} className="text-[13px] text-sky-700 hover:underline">
                  {ticket.ticket_number} — {ticket.title}
                </Link>
                <StatusBadge status={ticket.status} />
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <Panel title="Associated changes">
        {changeQuery.isLoading ? (
          <LoadingLinks label="associated changes" />
        ) : changeQuery.isError ? (
          <UnavailableLinks detail="The linked-change service could not be reached. This does not mean the asset has no associated changes." />
        ) : changes.length === 0 ? (
          <EmptyState title="No associated changes" description="No changes are linked to this asset." />
        ) : (
          <ul className="divide-y divide-slate-200">
            {changes.map((change) => (
              <li key={change.id} className="flex items-center justify-between gap-3 py-2">
                <Link to={`/itsm/changes/${change.id}`} className="text-[13px] text-sky-700 hover:underline">
                  {change.change_number} — {change.title}
                </Link>
                <StatusBadge status={change.status} />
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}
