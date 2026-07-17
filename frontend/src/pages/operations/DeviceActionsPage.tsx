/**
 * Device Actions — request a catalog-bound Intune action on a managed device.
 *
 * IT staff pick an approved action from the catalog (`/device-execution/catalog`),
 * name the target device + employee, and submit. The backend routes it to
 * autonomous execution, the human-approval queue, or denial — the typed outcome
 * (decision, risk tier, policy signals) is shown inline. Queued actions also
 * appear in the Approval Queue for an it_lead to action.
 *
 * The agent can never author a payload here: the only lever is a catalog id.
 * Styling mirrors `ApprovalsPage`. React Query owns the catalog fetch.
 */

import { useMemo, useState } from 'react';
import { Cpu } from 'lucide-react';

import { useDeviceCatalog, useRequestDeviceAction } from '@/features/device-execution/api';
import type {
  CatalogEntry,
  DeviceActionOutcome,
  RiskTier,
} from '@/features/device-execution/types';
import { TOOL_FOR_KIND } from '@/features/device-execution/types';
import { ApiError } from '@/lib/api';

export function DeviceActionsPage() {
  const { data: catalog, isLoading, isError } = useDeviceCatalog();
  const request = useRequestDeviceAction();

  const [selectedId, setSelectedId] = useState('');
  const [deviceId, setDeviceId] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [justification, setJustification] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<DeviceActionOutcome | null>(null);

  const entries: CatalogEntry[] = useMemo(
    () =>
      catalog
        ? [...catalog.apps, ...catalog.remediations, ...catalog.device_actions]
        : [],
    [catalog],
  );
  const selected = entries.find((e) => e.id === selectedId) ?? null;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setOutcome(null);
    if (!selected) return setError('Select an action from the catalog.');
    if (!deviceId.trim()) return setError('A target device id is required.');
    if (!employeeId.trim()) return setError('A target employee id is required.');

    try {
      const result = await request.mutateAsync({
        tool_name: TOOL_FOR_KIND[selected.kind],
        action_ref: selected.id,
        device_id: deviceId.trim(),
        employee_id: employeeId.trim(),
        idempotency_key: `${selected.id}-${deviceId.trim()}-${Date.now()}`,
        justification: justification.trim(),
        reason: justification.trim() || `Requested ${selected.display_name}`,
      });
      setOutcome(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError('Device execution is disabled or you lack permission.');
      } else {
        setError(err instanceof Error ? err.message : 'Failed to request action');
      }
    }
  };

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-gray-900">
          <Cpu size={22} className="text-indigo-600" /> Device Actions
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Run an approved, catalog-bound action on a managed device. Low-risk actions
          run autonomously; anything higher is routed to approval.
        </p>
      </div>

      {catalog && (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border bg-white p-4 text-xs text-gray-600">
          <Chip
            tone={catalog.autonomous_enabled ? 'green' : 'gray'}
            text={`Autonomy ${catalog.autonomous_enabled ? 'ON' : 'OFF (all → approval)'}`}
          />
          <Chip
            tone={catalog.autonomous_medium_allowed ? 'yellow' : 'gray'}
            text={`Medium-risk autonomy ${catalog.autonomous_medium_allowed ? 'ON' : 'OFF'}`}
          />
          <span className="text-gray-400">catalog v{catalog.catalog_version}</span>
          <span className="text-gray-400">policy v{catalog.policy_version}</span>
        </div>
      )}

      <div className="overflow-hidden rounded-lg border bg-white">
        <div className="border-b bg-gray-50 p-4 text-sm font-medium text-gray-700">
          Request an action
        </div>

        {isLoading ? (
          <div className="p-8 text-center text-sm text-gray-400">Loading catalog…</div>
        ) : isError ? (
          <div className="p-8 text-center text-sm text-red-600">
            Failed to load the action catalog. Device execution may be disabled.
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4 p-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600">
                Action <span className="text-red-500">*</span>
              </label>
              <select
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              >
                <option value="">Select an approved action…</option>
                <CatalogOptions label="Install app" entries={catalog?.apps ?? []} />
                <CatalogOptions label="Remediation" entries={catalog?.remediations ?? []} />
                <CatalogOptions label="Device action" entries={catalog?.device_actions ?? []} />
              </select>
              {selected && (
                <p className="mt-1 flex items-center gap-2 text-xs text-gray-400">
                  <RiskBadge tier={selected.risk_tier} /> {selected.description}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Field label="Target device id" required value={deviceId} onChange={setDeviceId}
                placeholder="Intune managed device id" />
              <Field label="Target employee id" required value={employeeId} onChange={setEmployeeId}
                placeholder="Employee whose consent applies" />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600">
                Justification
              </label>
              <textarea
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
                rows={2}
                placeholder="Why this action is needed (scanned for safety, never executed)"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>

            {error && <div className="text-sm text-red-600">{error}</div>}

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={request.isPending}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {request.isPending ? 'Requesting…' : 'Request action'}
              </button>
            </div>
          </form>
        )}
      </div>

      {outcome && <OutcomeCard outcome={outcome} />}
    </div>
  );
}

function CatalogOptions({ label, entries }: { label: string; entries: CatalogEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <optgroup label={label}>
      {entries.map((e) => (
        <option key={e.id} value={e.id}>
          {e.display_name} ({e.risk_tier})
        </option>
      ))}
    </optgroup>
  );
}

function OutcomeCard({ outcome }: { outcome: DeviceActionOutcome }) {
  const tone: Record<string, string> = {
    executed: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    pending_approval: 'border-amber-200 bg-amber-50 text-amber-800',
    denied: 'border-red-200 bg-red-50 text-red-800',
    rejected: 'border-red-200 bg-red-50 text-red-800',
    error: 'border-red-200 bg-red-50 text-red-800',
  };
  const heading: Record<string, string> = {
    executed: 'Executed autonomously',
    pending_approval: 'Queued for approval',
    denied: 'Denied by policy',
    rejected: 'Rejected',
    error: 'Error',
  };
  return (
    <div className={`mt-6 rounded-lg border p-4 text-sm ${tone[outcome.status] ?? ''}`}>
      <div className="font-medium">{heading[outcome.status] ?? outcome.status}</div>
      <div className="mt-1 text-xs">
        {outcome.action_ref} on {outcome.device_id}
        {outcome.risk_tier && ` · risk: ${outcome.risk_tier}`}
        {' · '}decision: {outcome.decision}
      </div>
      {outcome.reason && <div className="mt-1 text-xs italic">{outcome.reason}</div>}
      {outcome.approval_id && (
        <div className="mt-1 text-xs">
          Approval id <span className="font-mono">{outcome.approval_id}</span> — see the
          Approval Queue.
        </div>
      )}
      {outcome.policy_signals.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {outcome.policy_signals.map((s) => (
            <span key={s} className="rounded-full bg-white/60 px-2 py-0.5 text-[10px]">
              {s}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-gray-600">
        {label}
        {required && <span className="text-red-500"> *</span>}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
      />
    </div>
  );
}

function RiskBadge({ tier }: { tier: RiskTier }) {
  const tone: Record<RiskTier, string> = {
    low: 'bg-emerald-100 text-emerald-700',
    medium: 'bg-amber-100 text-amber-700',
    high: 'bg-red-100 text-red-700',
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${tone[tier]}`}>
      {tier} risk
    </span>
  );
}

function Chip({ tone, text }: { tone: 'green' | 'yellow' | 'gray'; text: string }) {
  const cls = {
    green: 'bg-emerald-100 text-emerald-700',
    yellow: 'bg-amber-100 text-amber-700',
    gray: 'bg-gray-100 text-gray-600',
  }[tone];
  return <span className={`rounded-full px-2 py-1 font-medium ${cls}`}>{text}</span>;
}
