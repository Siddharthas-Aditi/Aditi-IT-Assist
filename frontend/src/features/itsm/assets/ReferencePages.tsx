/** Read-only reference summaries derived from backend Asset records. */

import { useMemo } from "react";

import { useAssets } from "../api";
import { PageHeader } from "../components/chrome";
import { EmptyState, Panel } from "../components/ui";

function ReferenceRows({ title, field }: { title: string; field: "asset_type" | "location" | "vendor" }) {
  const { data, isLoading } = useAssets();
  const rows = useMemo(() => {
    const counts = new Map<string, number>();
    for (const asset of data?.items ?? []) {
      const value = asset[field]?.trim();
      if (value) counts.set(value, (counts.get(value) ?? 0) + 1);
    }
    return [...counts.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [data?.items, field]);

  return (
    <div className="space-y-4 pb-10">
      <PageHeader
        title={title}
        crumbs={[{ label: "Assets", to: "/itsm/assets" }, { label: title }]}
        description="Values currently present in backend asset records."
      />
      <Panel title={title}>
        {isLoading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : rows.length === 0 ? (
          <EmptyState
            title={`No ${title.toLowerCase()} recorded`}
            description="Reference-data management is unavailable until a server-backed contract exists."
          />
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
              <tr><th className="px-3 py-2">Value</th><th className="px-3 py-2">Assets</th></tr>
            </thead>
            <tbody>
              {rows.map(([value, count]) => (
                <tr key={value} className="border-b border-slate-100">
                  <td className="px-3 py-2 text-slate-800">{value}</td>
                  <td className="px-3 py-2 text-slate-600">{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

export function AssetTypesPage() {
  return <ReferenceRows title="Asset Types" field="asset_type" />;
}

export function LocationsPage() {
  return <ReferenceRows title="Locations" field="location" />;
}

export function VendorsPage() {
  return <ReferenceRows title="Vendors" field="vendor" />;
}
