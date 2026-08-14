/** Changes list — filters, sorting, bulk selection, CSV export. */

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, Plus } from 'lucide-react';

import { DataTable, type Column } from '../components/DataTable';
import { exportCsv } from '../components/csv';
import { FilterBar, type FilterSpec, type FilterValues } from '../components/FilterBar';
import { PageHeader } from '../components/chrome';
import { useSavedViews } from '../components/useSavedViews';
import { useToast } from '../components/toast-context';
import { Button, ChangeTypeBadge, LevelIndicator, StatusBadge } from '../components/ui';
import {
  CATEGORIES,
  DEPARTMENTS,
  GROUPS,
  PEOPLE,
  personName,
} from '../data/reference';
import { logChangeActivity, useItsmState } from '../data/store';
import {
  CHANGE_STATUSES,
  CHANGE_TYPES,
  IMPACTS,
  PRIORITIES,
  RISKS,
  type Change,
} from '../data/types';

const FILTERS: FilterSpec[] = [
  { key: 'status', label: 'Status', options: CHANGE_STATUSES },
  { key: 'changeType', label: 'Change Type', options: CHANGE_TYPES },
  { key: 'priority', label: 'Priority', options: PRIORITIES },
  { key: 'risk', label: 'Risk', options: RISKS },
  { key: 'impact', label: 'Impact', options: IMPACTS },
  { key: 'department', label: 'Department', options: DEPARTMENTS },
  { key: 'category', label: 'Category', options: CATEGORIES },
  { key: 'group', label: 'Group', options: GROUPS },
  { key: 'agent', label: 'Agent', options: PEOPLE.map((p) => p.name) },
  { key: 'plannedStartFrom', label: 'Planned Start ≥', options: [], type: 'date' },
  { key: 'plannedEndTo', label: 'Planned End ≤', options: [], type: 'date' },
];

function fmt(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export function ChangeListPage() {
  const { changes } = useItsmState();
  const navigate = useNavigate();
  const toast = useToast();
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState<FilterValues>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const savedViews = useSavedViews('aditi.itsm.views.changes');

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return changes.filter((c) => {
      if (
        needle &&
        !c.subject.toLowerCase().includes(needle) &&
        !c.changeId.toLowerCase().includes(needle) &&
        !personName(c.requesterId).toLowerCase().includes(needle)
      ) {
        return false;
      }
      if (filters.status && c.status !== filters.status) return false;
      if (filters.changeType && c.changeType !== filters.changeType) return false;
      if (filters.priority && c.priority !== filters.priority) return false;
      if (filters.risk && c.risk !== filters.risk) return false;
      if (filters.impact && c.impact !== filters.impact) return false;
      if (filters.department && c.department !== filters.department) return false;
      if (filters.category && c.category !== filters.category) return false;
      if (filters.group && c.group !== filters.group) return false;
      if (filters.agent && personName(c.agentId) !== filters.agent) return false;
      if (filters.plannedStartFrom && c.plannedStart < filters.plannedStartFrom) return false;
      if (filters.plannedEndTo && c.plannedEnd.slice(0, 10) > filters.plannedEndTo) return false;
      return true;
    });
  }, [changes, search, filters]);

  const columns: Column<Change>[] = [
    {
      key: 'changeId',
      header: 'Change ID',
      value: (c) => c.changeId,
      render: (c) => <span className="font-medium text-sky-700">{c.changeId}</span>,
    },
    {
      key: 'subject',
      header: 'Subject',
      value: (c) => c.subject,
      render: (c) => (
        <span className="block max-w-[320px] truncate text-slate-900" title={c.subject}>
          {c.subject}
        </span>
      ),
    },
    {
      key: 'changeType',
      header: 'Type',
      value: (c) => c.changeType,
      render: (c) => <ChangeTypeBadge type={c.changeType} />,
    },
    {
      key: 'status',
      header: 'Status',
      value: (c) => c.status,
      render: (c) => <StatusBadge status={c.status} />,
    },
    {
      key: 'priority',
      header: 'Priority',
      value: (c) => c.priority,
      render: (c) => <LevelIndicator level={c.priority} />,
    },
    {
      key: 'risk',
      header: 'Risk',
      value: (c) => c.risk,
      render: (c) => <LevelIndicator level={c.risk} />,
    },
    {
      key: 'impact',
      header: 'Impact',
      value: (c) => c.impact,
      render: (c) => <LevelIndicator level={c.impact} />,
    },
    { key: 'requester', header: 'Requester', value: (c) => personName(c.requesterId) },
    { key: 'group', header: 'Assigned Group', value: (c) => c.group },
    { key: 'agent', header: 'Agent', value: (c) => personName(c.agentId) },
    { key: 'plannedStart', header: 'Planned Start', value: (c) => c.plannedStart, render: (c) => fmt(c.plannedStart) },
    { key: 'plannedEnd', header: 'Planned End', value: (c) => c.plannedEnd, render: (c) => fmt(c.plannedEnd) },
    { key: 'createdAt', header: 'Created', value: (c) => c.createdAt, render: (c) => fmtDate(c.createdAt) },
  ];

  function bulkCancel() {
    let cancelled = 0;
    selected.forEach((id) => {
      const change = changes.find((c) => c.id === id);
      if (!change || change.status === 'Completed' || change.status === 'Cancelled') return;
      logChangeActivity(id, 'Sagar J', 'Cancelled via bulk action', { status: 'Cancelled' });
      cancelled += 1;
    });
    setSelected(new Set());
    if (cancelled) toast.success(`Cancelled ${cancelled} change${cancelled > 1 ? 's' : ''}.`);
    else toast.error('None of the selected changes can be cancelled.');
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Changes"
        description={`${changes.length} change records across the estate.`}
        actions={
          <>
            <Button
              onClick={() => exportCsv('changes.csv', rows, columns)}
              disabled={rows.length === 0}
            >
              <Download size={14} /> Export CSV
            </Button>
            <Button variant="primary" onClick={() => navigate('/itsm/changes/new')}>
              <Plus size={14} /> Create Change
            </Button>
          </>
        }
      />

      <FilterBar
        searchPlaceholder="Search by change ID, subject, or requester…"
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
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-[12.5px] text-sky-800">
          <span>{selected.size} selected</span>
          <Button variant="danger" onClick={bulkCancel}>
            Cancel selected
          </Button>
          <Button variant="ghost" onClick={() => setSelected(new Set())}>
            Clear selection
          </Button>
        </div>
      )}

      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(c) => c.id}
        onRowClick={(c) => navigate(`/itsm/changes/${c.id}`)}
        selectable
        selected={selected}
        onSelectedChange={setSelected}
        initialSortKey="plannedStart"
        emptyTitle="No changes match these filters"
        emptyDescription="Adjust the search or filters, or raise a new change."
        emptyAction={
          <Button variant="primary" onClick={() => navigate('/itsm/changes/new')}>
            <Plus size={14} /> Create Change
          </Button>
        }
      />
    </div>
  );
}
