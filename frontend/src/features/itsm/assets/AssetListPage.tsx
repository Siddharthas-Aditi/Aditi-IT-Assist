/** Asset inventory list — filters, bulk update, CSV export, expiry highlights. */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Download, Plus, Upload } from "lucide-react";

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
import { Button, Select, StatusBadge } from "../components/ui";
import {
  DEPARTMENTS,
  GROUPS,
  PEOPLE,
  personName,
  VENDORS,
} from "../data/reference";
import { formatMoney } from "../data/money";
import { daysUntil, isExpiringSoon } from "../data/rules";
import { logAssetActivity } from "../data/store";
import { useAssets } from "../api";
import {
  ASSET_STATUS_LABELS,
  ASSET_TERMINAL,
  type AssetRecord,
  type AssetStatus,
} from "../api-types";

const ASSET_STATUS_OPTIONS = Object.values(ASSET_STATUS_LABELS);
const STATUS_LABEL_TO_KEY: Record<string, AssetStatus> = Object.fromEntries(
  Object.entries(ASSET_STATUS_LABELS).map(([k, v]) => [v, k as AssetStatus]),
);

const ASSET_TYPES = [
  "Computer",
  "Laptop",
  "Mobile",
  "Tablet",
  "Monitor",
  "Printer",
  "Server",
  "Network",
  "Peripheral",
  "Software",
  "Other",
];

const FILTERS: FilterSpec[] = [
  { key: "asset_type", label: "Asset Type", options: ASSET_TYPES },
  { key: "status", label: "Asset Status", options: ASSET_STATUS_OPTIONS },
  { key: "department", label: "Department", options: DEPARTMENTS },
  { key: "managed_by_group", label: "Managed By Group", options: GROUPS },
  {
    key: "assigned_to",
    label: "Assigned To",
    options: PEOPLE.map((p) => p.name),
  },
  { key: "vendor", label: "Vendor", options: VENDORS.map((v) => v.name) },
  {
    key: "warrantyBefore",
    label: "Warranty Expiry ≤",
    options: [],
    type: "date",
  },
  { key: "eolBefore", label: "End of Life ≤", options: [], type: "date" },
];

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/** Warranty / EOL inside the 90-day window get an amber warning affordance. */
function ExpiryCell({ date }: { date: string | null }) {
  if (!date) return <span className="text-slate-500">—</span>;
  const days = daysUntil(date);
  const soon = isExpiringSoon(date);
  return (
    <span
      className={
        soon ? "inline-flex items-center gap-1 text-amber-700" : undefined
      }
    >
      {soon && <AlertTriangle size={11} aria-hidden="true" />}
      {fmtDate(date)}
      {soon && (
        <span className="text-[11px] text-amber-600">
          ({days !== null && days < 0 ? "expired" : `${days}d`})
        </span>
      )}
    </span>
  );
}

export function AssetListPage() {
  const assetsQuery = useAssets();
  const assetsData = assetsQuery.data?.items;
  const assets = useMemo(() => assetsData ?? [], [assetsData]);
  const navigate = useNavigate();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<FilterValues>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkStatus, setBulkStatus] = useState("");
  const savedViews = useSavedViews("aditi.itsm.views.assets");

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return assets.filter((a) => {
      if (needle) {
        const haystack = [
          a.name,
          a.asset_tag,
          a.serial_number,
          a.model,
          a.vendor,
          a.location,
          a.ip_address,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      if (filters.asset_type && a.asset_type !== filters.asset_type)
        return false;
      if (filters.status) {
        const key = STATUS_LABEL_TO_KEY[filters.status as string];
        if (key && a.status !== key) return false;
      }
      if (filters.department && a.department !== filters.department)
        return false;
      if (
        filters.managed_by_group &&
        a.managed_by_group !== filters.managed_by_group
      )
        return false;
      if (
        filters.assigned_to &&
        personName(a.assigned_to_id) !== filters.assigned_to
      )
        return false;
      if (filters.vendor && a.vendor !== filters.vendor) return false;
      if (
        filters.warrantyBefore &&
        (a.warranty_expiry ?? "9999") > (filters.warrantyBefore as string)
      ) {
        return false;
      }
      if (
        filters.eolBefore &&
        (a.end_of_life ?? "9999") > (filters.eolBefore as string)
      )
        return false;
      return true;
    });
  }, [assets, search, filters]);

  const columns: Column<AssetRecord>[] = [
    {
      key: "asset_tag",
      header: "Asset Tag",
      value: (a) => a.asset_tag,
      render: (a) => (
        <span className="font-medium text-sky-700">{a.asset_tag}</span>
      ),
    },
    {
      key: "name",
      header: "Asset Name",
      value: (a) => a.name,
      render: (a) => (
        <span
          className="block max-w-[260px] truncate text-slate-900"
          title={a.name}
        >
          {a.name}
        </span>
      ),
    },
    { key: "asset_type", header: "Type", value: (a) => a.asset_type },
    { key: "model", header: "Model", value: (a) => a.model ?? "" },
    { key: "vendor", header: "Vendor", value: (a) => a.vendor ?? "" },
    {
      key: "serial_number",
      header: "Serial Number",
      value: (a) => a.serial_number ?? "",
    },
    {
      key: "status",
      header: "Status",
      value: (a) => a.status,
      render: (a) => (
        <StatusBadge status={ASSET_STATUS_LABELS[a.status] ?? a.status} />
      ),
    },
    {
      key: "assigned_to",
      header: "Assigned To",
      value: (a) => personName(a.assigned_to_id),
    },
    { key: "location", header: "Location", value: (a) => a.location ?? "" },
    {
      key: "department",
      header: "Department",
      value: (a) => a.department ?? "",
    },
    {
      key: "managed_by_group",
      header: "Managed By Group",
      value: (a) => a.managed_by_group ?? "",
    },
    {
      key: "cost",
      header: "Cost",
      value: (a) => a.cost ?? 0,
      align: "right",
      render: (a) =>
        formatMoney(a.cost ?? 0, (a.currency as "INR" | "USD") ?? "INR"),
    },
    {
      key: "warranty_expiry",
      header: "Warranty Expiry",
      value: (a) => a.warranty_expiry ?? "",
      render: (a) => <ExpiryCell date={a.warranty_expiry} />,
    },
    {
      key: "end_of_life",
      header: "End of Life",
      value: (a) => a.end_of_life ?? "",
      render: (a) => <ExpiryCell date={a.end_of_life} />,
    },
    {
      key: "updated_at",
      header: "Updated",
      value: (a) => a.updated_at,
      render: (a) => fmtDate(a.updated_at),
    },
  ];

  async function applyBulkStatus() {
    if (!bulkStatus) return;
    const target =
      STATUS_LABEL_TO_KEY[bulkStatus] ?? (bulkStatus as AssetStatus);
    let moved = 0;
    const blocked: string[] = [];
    const promises = Array.from(selected).map(async (id) => {
      const asset = assets.find((a) => a.id === id);
      if (!asset) return;
      if (ASSET_TERMINAL.has(asset.status)) {
        blocked.push(asset.asset_tag);
        return;
      }
      await logAssetActivity(
        id,
        "Sagar J",
        `Status changed to ${target} via bulk update`,
        {
          status: target,
        },
      );
      moved += 1;
    });
    await Promise.allSettled(promises);
    if (moved)
      toast.success(
        `Updated ${moved} asset${moved > 1 ? "s" : ""} to ${ASSET_STATUS_LABELS[target] ?? target}.`,
      );
    if (blocked.length) {
      toast.error(
        `${blocked.length} skipped — retired or disposed: ${blocked.slice(0, 3).join(", ")}${blocked.length > 3 ? "…" : ""}`,
      );
    }
    setSelected(new Set());
    setBulkStatus("");
  }

  const expiringCount = assets.filter(
    (a) => isExpiringSoon(a.warranty_expiry) || isExpiringSoon(a.end_of_life),
  ).length;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Assets"
        description={`${assetsQuery.data?.total ?? assets.length} assets tracked · ${expiringCount} nearing warranty or end of life.`}
        actions={
          <>
            <Button onClick={() => navigate("/itsm/assets/import")}>
              <Upload size={14} /> Bulk import
            </Button>
            <Button
              onClick={() => exportCsv("assets.csv", rows, columns)}
              disabled={!rows.length}
            >
              <Download size={14} /> Export CSV
            </Button>
            <Button
              variant="primary"
              onClick={() => navigate("/itsm/assets/new")}
            >
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
            <span className="sr-only">Bulk asset status</span>
            <Select
              options={ASSET_STATUS_OPTIONS}
              placeholder="Set status to…"
              value={bulkStatus}
              onChange={(e) => setBulkStatus(e.target.value)}
              className="w-40"
            />
          </label>
          <Button
            variant="primary"
            onClick={() => void applyBulkStatus()}
            disabled={!bulkStatus}
          >
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
        initialSortKey="asset_tag"
        emptyTitle="No assets match these filters"
        emptyDescription="Adjust the search or filters, or add a new asset to the inventory."
        emptyAction={
          <Button
            variant="primary"
            onClick={() => navigate("/itsm/assets/new")}
          >
            <Plus size={14} /> Create Asset
          </Button>
        }
      />
    </div>
  );
}
