/** Asset inventory list — filters, bulk update, CSV export, expiry highlights. */

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Download, Plus } from 'lucide-react';

import { DataTable, type Column } from '../components/DataTable';
import { exportCsv } from '../components/csv';
import { FilterBar, type FilterSpec, type FilterValues } from '../components/FilterBar';
import { PageHeader } from '../components/chrome';
import { useSavedViews } from '../components/useSavedViews';
import { useToast } from '../components/toast-context';
import { Button, Select, StatusBadge } from '../components/ui';
import {
  ASSET_TYPES,
  DEPARTMENTS,
  GROUPS,
  LOCATIONS,
  PEOPLE,
  personName,
  VENDORS,
} from '../data/reference';
import { canMoveAsset, daysUntil, isExpiringSoon } from '../data/rules';
import { logAssetActivity, useItsmState } from '../data/store';
import { ASSET_STATES, USAGE_TYPES, type Asset, type AssetState } from '../data/types';

const FILTERS: FilterSpec[] = [
  { key: 'assetType', label: 'Asset Type', options: ASSET_TYPES.map((t) => t.name) },
  { key: 'assetState', label: 'Asset State', options: ASSET_STATES },
  { key: 'usageType', label: 'Usage Type', options: USAGE_TYPES },
  { key: 'department', label: 'Department', options: DEPARTMENTS },
  { key: 'managedByGroup', label: 'Managed By Group', options: GROUPS },
  { key: 'managedBy', label: 'Managed By', options: PEOPLE.map((p) => p.name) },
  { key: 'assignedTo', label: 'Assigned To', options: PEOPLE.map((p) => p.name) },
  { key: 'location', label: 'Location', options: LOCATIONS.map((l) => l.name) },
  { key: 'vendor', label: 'Vendor', options: VENDORS.map((v) => v.name) },
  { key: 'warrantyBefore', label: 'Warranty Expiry ≤', options: [], type: 'date' },
  { key: 'eolBefore', label: 'End of Life ≤', options: [], type: 'date' },
];

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

const INR = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

/** Warranty / EOL inside the 90-day window get an amber warning affordance. */
function ExpiryCell({ date }: { date: string | null }) {
  if (!date) return <span className="text-slate-500">—</span>;
  const days = daysUntil(date);
  const soon = isExpiringSoon(date);
  return (
    <span className={soon ? 'inline-flex items-center gap-1 text-amber-700' : undefined}>
      {soon && <AlertTriangle size={11} aria-hidden="true" />}
      {fmtDate(date)}
      {soon && (
        <span className="text-[11px] text-amber-600">
          ({days !== null && days < 0 ? 'expired' : `${days}d`})
        </span>
      )}
    </span>
  );
}

export function AssetListPage() {
  const { assets } = useItsmState();
  const navigate = useNavigate();
  const toast = useToast();
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState<FilterValues>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkState, setBulkState] = useState('');
  const savedViews = useSavedViews('aditi.itsm.views.assets');

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return assets.filter((a) => {
      if (needle) {
        const haystack = [
          a.name,
          a.assetTag,
          a.serialNumber,
          a.employeeId,
          a.model,
          a.vendor,
          a.location,
          a.ipAddress,
        ]
          .join(' ')
          .toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      if (filters.assetType && a.assetType !== filters.assetType) return false;
      if (filters.assetState && a.assetState !== filters.assetState) return false;
      if (filters.usageType && a.usageType !== filters.usageType) return false;
      if (filters.department && a.department !== filters.department) return false;
      if (filters.managedByGroup && a.managedByGroup !== filters.managedByGroup) return false;
      if (filters.managedBy && personName(a.managedBy) !== filters.managedBy) return false;
      if (filters.assignedTo && personName(a.assignedTo) !== filters.assignedTo) return false;
      if (filters.location && a.location !== filters.location) return false;
      if (filters.vendor && a.vendor !== filters.vendor) return false;
      if (filters.warrantyBefore && (a.warrantyExpiry ?? '9999') > filters.warrantyBefore) {
        return false;
      }
      if (filters.eolBefore && (a.endOfLife ?? '9999') > filters.eolBefore) return false;
      return true;
    });
  }, [assets, search, filters]);

  const columns: Column<Asset>[] = [
    {
      key: 'assetTag',
      header: 'Asset Tag',
      value: (a) => a.assetTag,
      render: (a) => <span className="font-medium text-sky-700">{a.assetTag}</span>,
    },
    {
      key: 'name',
      header: 'Asset Name',
      value: (a) => a.name,
      render: (a) => (
        <span className="block max-w-[260px] truncate text-slate-900" title={a.name}>
          {a.name}
        </span>
      ),
    },
    { key: 'assetType', header: 'Type', value: (a) => a.assetType },
    { key: 'model', header: 'Model', value: (a) => a.model },
    { key: 'vendor', header: 'Vendor', value: (a) => a.vendor },
    { key: 'serialNumber', header: 'Serial Number', value: (a) => a.serialNumber },
    {
      key: 'assetState',
      header: 'Asset State',
      value: (a) => a.assetState,
      render: (a) => <StatusBadge status={a.assetState} />,
    },
    {
      key: 'assignedTo',
      header: 'Assigned To',
      value: (a) => personName(a.assignedTo),
    },
    { key: 'location', header: 'Location', value: (a) => a.location },
    { key: 'department', header: 'Department', value: (a) => a.department },
    { key: 'managedByGroup', header: 'Managed By Group', value: (a) => a.managedByGroup },
    {
      key: 'cost',
      header: 'Cost',
      value: (a) => a.cost,
      align: 'right',
      render: (a) => INR.format(a.cost),
    },
    {
      key: 'warrantyExpiry',
      header: 'Warranty Expiry',
      value: (a) => a.warrantyExpiry ?? '',
      render: (a) => <ExpiryCell date={a.warrantyExpiry} />,
    },
    {
      key: 'endOfLife',
      header: 'End of Life',
      value: (a) => a.endOfLife ?? '',
      render: (a) => <ExpiryCell date={a.endOfLife} />,
    },
    {
      key: 'updatedAt',
      header: 'Updated',
      value: (a) => a.updatedAt,
      render: (a) => fmtDate(a.updatedAt),
    },
  ];

  function applyBulkState() {
    if (!bulkState) return;
    const target = bulkState as AssetState;
    let moved = 0;
    const blocked: string[] = [];
    selected.forEach((id) => {
      const asset = assets.find((a) => a.id === id);
      if (!asset) return;
      const verdict = canMoveAsset(asset, target);
      if (!verdict.ok) {
        blocked.push(asset.assetTag);
        return;
      }
      logAssetActivity(id, 'Sagar J', `State changed to ${target} via bulk update`, {
        assetState: target,
      });
      moved += 1;
    });
    if (moved) toast.success(`Updated ${moved} asset${moved > 1 ? 's' : ''} to ${target}.`);
    if (blocked.length) {
      toast.error(
        `${blocked.length} skipped — required fields missing: ${blocked.slice(0, 3).join(', ')}${blocked.length > 3 ? '…' : ''}`,
      );
    }
    setSelected(new Set());
    setBulkState('');
  }

  const expiringCount = assets.filter(
    (a) => isExpiringSoon(a.warrantyExpiry) || isExpiringSoon(a.endOfLife),
  ).length;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Assets"
        description={`${assets.length} assets tracked · ${expiringCount} nearing warranty or end of life.`}
        actions={
          <>
            <Button onClick={() => exportCsv('assets.csv', rows, columns)} disabled={!rows.length}>
              <Download size={14} /> Export CSV
            </Button>
            <Button variant="primary" onClick={() => navigate('/itsm/assets/new')}>
              <Plus size={14} /> Create Asset
            </Button>
          </>
        }
      />

      <FilterBar
        searchPlaceholder="Search by name, tag, serial, employee ID, model, vendor, location, or IP…"
        search={search}
        onSearchChange={setSearch}
        specs={FILTERS}
        values={filters}
        onChange={setFilters}
        savedViews={savedViews.views}
        onSaveView={(name) => {
          savedViews.save(name, search, filters);
          toast.success(`Saved view “${name}”.`);
        }}
        onApplyView={(v) => {
          setSearch(v.search);
          setFilters(v.filters);
        }}
        onDeleteView={(name) => savedViews.remove(name)}
      />

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-[12.5px] text-sky-800">
          <span>{selected.size} selected</span>
          <label className="flex items-center gap-1.5">
            <span className="sr-only">Bulk asset state</span>
            <Select
              options={ASSET_STATES}
              placeholder="Set state to…"
              value={bulkState}
              onChange={(e) => setBulkState(e.target.value)}
              className="w-40"
            />
          </label>
          <Button variant="primary" onClick={applyBulkState} disabled={!bulkState}>
            Apply
          </Button>
          <Button variant="ghost" onClick={() => setSelected(new Set())}>
            Clear selection
          </Button>
        </div>
      )}

      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(a) => a.id}
        onRowClick={(a) => navigate(`/itsm/assets/${a.id}`)}
        selectable
        selected={selected}
        onSelectedChange={setSelected}
        initialSortKey="assetTag"
        emptyTitle="No assets match these filters"
        emptyDescription="Adjust the search or filters, or add a new asset to the inventory."
        emptyAction={
          <Button variant="primary" onClick={() => navigate('/itsm/assets/new')}>
            <Plus size={14} /> Create Asset
          </Button>
        }
      />
    </div>
  );
}
