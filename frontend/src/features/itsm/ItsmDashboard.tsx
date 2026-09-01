/** Landing dashboard summarising the Change and Asset modules. */

import { Link } from 'react-router-dom';
import { AlertTriangle, ArrowRight, Loader2 } from 'lucide-react';

import { PageHeader } from './components/chrome';
import { ChangeTypeBadge, Panel, StatusBadge } from './components/ui';
import { useItsmData } from './api';
import { CHANGE_STATUS_LABELS, ASSET_STATUS_LABELS } from './api-types';

const EXPIRY_DAYS = 90;

function isExpiringSoon(date: string | null): boolean {
  if (!date) return false;
  const d = new Date(date).getTime();
  if (isNaN(d)) return false;
  const diff = (d - Date.now()) / 86_400_000;
  return diff >= 0 && diff <= EXPIRY_DAYS;
}

function Tile({ label, value, to, tone, loading }: {
  label: string; value: number; to: string; tone?: 'warn'; loading?: boolean;
}) {
  return (
    <Link to={to} className="rounded-lg border border-slate-200 bg-white p-4 transition-colors hover:border-sky-300 focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500">
      <p className="text-[11.5px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-[26px] font-semibold leading-none ${tone === 'warn' ? 'text-amber-700' : 'text-slate-900'}`}>
        {loading ? <Loader2 size={22} className="animate-spin text-slate-400" /> : value}
      </p>
    </Link>
  );
}

export function ItsmDashboard() {
  const { changes, assets, isLoading } = useItsmData();

  const pendingApproval = changes.filter((c) => c.status === 'pending_approval');
  const inProgress = changes.filter((c) => c.status === 'in_progress');
  const scheduled = changes
    .filter((c) => c.status === 'scheduled')
    .sort((a, b) => (a.planned_start ?? '').localeCompare(b.planned_start ?? ''));
  const expiring = assets.filter((a) => isExpiringSoon(a.warranty_expiry) || isExpiringSoon(a.end_of_life));
  const unassigned = assets.filter((a) => !a.assigned_to_id);

  return (
    <div className="space-y-4 pb-10">
      <PageHeader title="Dashboard" description="Change and asset posture for Aditi Consulting IT operations." />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Tile label="Open changes" value={changes.length} to="/itsm/changes" loading={isLoading} />
        <Tile label="Pending approval" value={pendingApproval.length} to="/itsm/changes?status=pending_approval" loading={isLoading} />
        <Tile label="In progress" value={inProgress.length} to="/itsm/changes/board" loading={isLoading} />
        <Tile label="Total assets" value={assets.length} to="/itsm/assets" loading={isLoading} />
        <Tile label="Expiring ≤ 90 days" value={expiring.length} to="/itsm/assets/reports" tone="warn" loading={isLoading} />
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Next scheduled changes" actions={<Link to="/itsm/changes/calendar" className="inline-flex items-center gap-1 text-[12px] text-sky-700 hover:underline">Calendar <ArrowRight size={12} /></Link>}>
          {scheduled.length === 0 ? (
            <p className="py-4 text-center text-[12.5px] text-slate-500">{isLoading ? 'Loading…' : 'Nothing scheduled right now.'}</p>
          ) : (
            <ul className="divide-y divide-slate-200">
              {scheduled.slice(0, 6).map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <Link to={`/itsm/changes/${c.id}`} className="text-[12.5px] font-medium text-sky-700 hover:underline">{c.change_number}</Link>
                    <p className="truncate text-[12px] text-slate-700">{c.title}</p>
                    <p className="text-[11px] text-slate-500">{c.planned_start ? new Date(c.planned_start).toLocaleString() : '—'}</p>
                  </div>
                  <ChangeTypeBadge type={c.change_type} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Awaiting approval" actions={<Link to="/itsm/changes" className="inline-flex items-center gap-1 text-[12px] text-sky-700 hover:underline">All changes <ArrowRight size={12} /></Link>}>
          {pendingApproval.length === 0 ? (
            <p className="py-4 text-center text-[12.5px] text-slate-500">{isLoading ? 'Loading…' : 'No approvals outstanding.'}</p>
          ) : (
            <ul className="divide-y divide-slate-200">
              {pendingApproval.slice(0, 6).map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <Link to={`/itsm/changes/${c.id}`} className="text-[12.5px] font-medium text-sky-700 hover:underline">{c.change_number}</Link>
                    <p className="truncate text-[12px] text-slate-700">{c.title}</p>
                  </div>
                  <StatusBadge status={CHANGE_STATUS_LABELS[c.status] ?? c.status} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Assets needing attention" actions={<Link to="/itsm/assets/reports" className="inline-flex items-center gap-1 text-[12px] text-sky-700 hover:underline">Reports <ArrowRight size={12} /></Link>}>
          {expiring.length === 0 ? (
            <p className="py-4 text-center text-[12.5px] text-slate-500">{isLoading ? 'Loading…' : 'No warranty or end-of-life risk in the next 90 days.'}</p>
          ) : (
            <ul className="divide-y divide-slate-200">
              {expiring.slice(0, 6).map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <Link to={`/itsm/assets/${a.id}`} className="text-[12.5px] font-medium text-sky-700 hover:underline">{a.asset_tag}</Link>
                    <p className="truncate text-[12px] text-slate-500">{a.name}</p>
                  </div>
                  <span className="inline-flex shrink-0 items-center gap-1 text-[11.5px] text-amber-700"><AlertTriangle size={11} /> Review</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Unassigned assets">
          {unassigned.length === 0 ? (
            <p className="py-4 text-center text-[12.5px] text-slate-500">{isLoading ? 'Loading…' : 'Every asset has an owner.'}</p>
          ) : (
            <ul className="divide-y divide-slate-200">
              {unassigned.slice(0, 6).map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <Link to={`/itsm/assets/${a.id}`} className="text-[12.5px] font-medium text-sky-700 hover:underline">{a.asset_tag}</Link>
                    <p className="truncate text-[12px] text-slate-500">{a.name}</p>
                  </div>
                  <StatusBadge status={ASSET_STATUS_LABELS[a.status] ?? a.status} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
