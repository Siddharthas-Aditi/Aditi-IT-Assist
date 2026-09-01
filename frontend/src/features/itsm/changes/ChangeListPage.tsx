/** Changes list — filters, sorting, bulk selection, CSV export. */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Download, Plus } from "lucide-react";

import { DataTable, type Column } from "../components/DataTable";
import { exportCsv } from "../components/csv";
import {
  FilterBar,
  type FilterSpec,
  type FilterValues,
} from "../components/FilterBar";
import { PageHeader } from "../components/chrome";
import { useSavedViews } from "../components/useSavedViews";
import { useToast } from "../components/toast-context";
import {
  Button,
  ChangeTypeBadge,
  LevelIndicator,
  StatusBadge,
} from "../components/ui";
import { CATEGORIES, DEPARTMENTS, PEOPLE, personName } from "../data/reference";
import { logChangeActivity } from "../data/store";
import { useChanges } from "../api";
import {
  CHANGE_STATUS_LABELS,
  type ChangeRecord,
  type ChangeStatus,
  type ChangeType,
} from "../api-types";

const STATUS_LABEL_TO_KEY: Record<string, ChangeStatus> = Object.fromEntries(
  Object.entries(CHANGE_STATUS_LABELS).map(([k, v]) => [v, k as ChangeStatus]),
);
const CHANGE_TYPE_OPTIONS = ["Standard", "Normal", "Emergency"];
const CHANGE_TYPE_TO_KEY: Record<string, ChangeType> = {
  Standard: "standard",
  Normal: "normal",
  Emergency: "emergency",
};
const PRIORITIES = ["Low", "Medium", "High", "Urgent"];
const IMPACTS = ["Low", "Medium", "High"];
const RISKS = ["Low", "Medium", "High"];

const FILTERS: FilterSpec[] = [
  {
    key: "status",
    label: "Status",
    options: Object.values(CHANGE_STATUS_LABELS),
  },
  { key: "change_type", label: "Change Type", options: CHANGE_TYPE_OPTIONS },
  { key: "priority", label: "Priority", options: PRIORITIES },
  { key: "risk", label: "Risk", options: RISKS },
  { key: "impact", label: "Impact", options: IMPACTS },
  { key: "department", label: "Department", options: DEPARTMENTS },
  { key: "category", label: "Category", options: CATEGORIES },
  { key: "agent", label: "Agent", options: PEOPLE.map((p) => p.name) },
  {
    key: "plannedStartFrom",
    label: "Planned Start ≥",
    options: [],
    type: "date",
  },
  { key: "plannedEndTo", label: "Planned End ≤", options: [], type: "date" },
];

function fmt(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function ChangeListPage() {
  const changesQuery = useChanges();
  const changesData = changesQuery.data?.items;
  const changes = useMemo(() => changesData ?? [], [changesData]);
  const navigate = useNavigate();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<FilterValues>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const savedViews = useSavedViews("aditi.itsm.views.changes");

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return changes.filter((c) => {
      if (
        needle &&
        !c.title.toLowerCase().includes(needle) &&
        !c.change_number.toLowerCase().includes(needle) &&
        !personName(c.requested_by_id).toLowerCase().includes(needle)
      ) {
        return false;
      }
      if (filters.status) {
        const key = STATUS_LABEL_TO_KEY[filters.status as string];
        if (key && c.status !== key) return false;
      }
      if (filters.change_type) {
        const key = CHANGE_TYPE_TO_KEY[filters.change_type as string];
        if (key && c.change_type !== key) return false;
      }
      if (filters.priority && c.priority !== filters.priority) return false;
      if (filters.risk && c.risk !== filters.risk) return false;
      if (filters.impact && c.impact !== filters.impact) return false;
      if (filters.department && c.department !== filters.department)
        return false;
      if (filters.category && c.category !== filters.category) return false;
      if (filters.agent && personName(c.assigned_to_id) !== filters.agent)
        return false;
      if (
        filters.plannedStartFrom &&
        (c.planned_start ?? "") < (filters.plannedStartFrom as string)
      ) {
        return false;
      }
      if (
        filters.plannedEndTo &&
        (c.planned_end ?? "").slice(0, 10) > (filters.plannedEndTo as string)
      ) {
        return false;
      }
      return true;
    });
  }, [changes, search, filters]);

  const columns: Column<ChangeRecord>[] = [
    {
      key: "changeId",
      header: "Change ID",
      value: (c) => c.change_number,
      render: (c) => (
        <span className="font-medium text-sky-700">{c.change_number}</span>
      ),
    },
    {
      key: "title",
      header: "Subject",
      value: (c) => c.title,
      render: (c) => (
        <span
          className="block max-w-[320px] truncate text-slate-900"
          title={c.title}
        >
          {c.title}
        </span>
      ),
    },
    {
      key: "change_type",
      header: "Type",
      value: (c) => c.change_type,
      render: (c) => <ChangeTypeBadge type={c.change_type} />,
    },
    {
      key: "status",
      header: "Status",
      value: (c) => CHANGE_STATUS_LABELS[c.status] ?? c.status,
      render: (c) => (
        <StatusBadge status={CHANGE_STATUS_LABELS[c.status] ?? c.status} />
      ),
    },
    {
      key: "priority",
      header: "Priority",
      value: (c) => c.priority,
      render: (c) => <LevelIndicator level={c.priority} />,
    },
    {
      key: "risk",
      header: "Risk",
      value: (c) => c.risk,
      render: (c) => <LevelIndicator level={c.risk} />,
    },
    {
      key: "impact",
      header: "Impact",
      value: (c) => c.impact,
      render: (c) => <LevelIndicator level={c.impact} />,
    },
    {
      key: "requested_by_id",
      header: "Requester",
      value: (c) => c.requested_by_id ?? "",
    },
    {
      key: "assigned_to_id",
      header: "Agent",
      value: (c) => c.assigned_to_id ?? "",
    },
    {
      key: "planned_start",
      header: "Planned Start",
      value: (c) => c.planned_start ?? "",
      render: (c) => fmt(c.planned_start),
    },
    {
      key: "planned_end",
      header: "Planned End",
      value: (c) => c.planned_end ?? "",
      render: (c) => fmt(c.planned_end),
    },
    {
      key: "created_at",
      header: "Created",
      value: (c) => c.created_at,
      render: (c) => fmtDate(c.created_at),
    },
  ];

  function bulkCancel() {
    let cancelled = 0;
    selected.forEach((id) => {
      const change = changes.find((c) => c.id === id);
      if (
        !change ||
        change.status === "implemented" ||
        change.status === "closed" ||
        change.status === "cancelled"
      )
        return;
      void logChangeActivity(id, "Sagar J", "Cancelled via bulk action", {
        status: "cancelled",
      });
      cancelled += 1;
    });
    setSelected(new Set());
    if (cancelled)
      toast.success(
        `Cancelled ${cancelled} change${cancelled > 1 ? "s" : ""}.`,
      );
    else toast.error("None of the selected changes can be cancelled.");
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Changes"
        description={`${changesQuery.data?.total ?? changes.length} change records across the estate.`}
        actions={
          <>
            <Button
              onClick={() => exportCsv("changes.csv", rows, columns)}
              disabled={rows.length === 0}
            >
              <Download size={14} /> Export CSV
            </Button>
            <Button
              variant="primary"
              onClick={() => navigate("/itsm/changes/new")}
            >
              <Plus size={14} /> Create Change
            </Button>
          </>
        }
      />

      <FilterBar
        searchPlaceholder="Search by change ID, title, or requester…"
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
          <Button variant="danger" onClick={() => void bulkCancel()}>
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
        initialSortKey="planned_start"
        emptyTitle="No changes match these filters"
        emptyDescription="Adjust the search or filters, or raise a new change."
        emptyAction={
          <Button
            variant="primary"
            onClick={() => navigate("/itsm/changes/new")}
          >
            <Plus size={14} /> Create Change
          </Button>
        }
      />
    </div>
  );
}
