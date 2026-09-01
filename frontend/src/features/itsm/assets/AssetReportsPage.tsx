/**
 * Asset reports.
 *
 * Every chart here is a single measure (a count) across nominal categories, so
 * each uses ONE hue rather than a per-bar ramp — bar length already encodes the
 * value, and colouring by rank would double-encode it. Identity comes from the
 * axis label. Each chart ships a table-view twin so no value is reachable only
 * by hovering, and the filter row scopes every card at once.
 */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageHeader } from "../components/chrome";
import { Button, Panel, StatusBadge } from "../components/ui";
import { ASSET_TYPES, personName } from "../data/reference";
import { formatTotals } from "../data/money";
import { daysUntil, isExpiringSoon } from "../data/rules";
import { useItsmState } from "../api";
import { toAssetDisplay } from "../display-adapters";
import type { AssetDisplay as Asset } from "../display-adapters";

/** One hue for every bar: the category is carried by the axis, not by colour. */
const MARK = "#0284c7"; // sky-600 — the console's accent, readable on white
const GRID = "#e2e8f0"; // slate-200 hairline, one shade off the surface
const AXIS_INK = "#64748b"; // slate-500

interface Datum {
  label: string;
  value: number;
}

function tally(rows: Asset[], pick: (a: Asset) => string): Datum[] {
  const map = new Map<string, number>();
  rows.forEach((a) => {
    const key = pick(a) || "Unspecified";
    map.set(key, (map.get(key) ?? 0) + 1);
  });
  return [...map.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value);
}

function StatTile({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: number | string;
  tone?: "warn" | "default";
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-[11.5px] uppercase tracking-wide text-slate-500">
        {label}
      </p>
      {/* Proportional figures — tabular-nums would make a display number look loose. */}
      <p
        className={`mt-1 text-[26px] font-semibold leading-none ${
          tone === "warn" ? "text-amber-700" : "text-slate-900"
        }`}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-[11.5px] text-slate-500">{hint}</p>}
    </div>
  );
}

function ChartCard({ title, data }: { title: string; data: Datum[] }) {
  const [asTable, setAsTable] = useState(false);
  // Give every row a consistent band plus room for the axis, so the card never
  // grows an inner scrollbar that clips the axis labels.
  const height = Math.max(160, data.length * 28 + 40);

  return (
    <Panel
      title={title}
      actions={
        <Button variant="ghost" onClick={() => setAsTable((t) => !t)}>
          {asTable ? "Show chart" : "Show table"}
        </Button>
      }
    >
      {data.length === 0 ? (
        <p className="py-6 text-center text-[12.5px] text-slate-500">
          No data for this slice.
        </p>
      ) : asTable ? (
        <table className="w-full text-left">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr className="border-b border-slate-200">
              <th
                scope="col"
                className="px-2 py-1.5 text-[11px] uppercase tracking-wide text-slate-500"
              >
                Category
              </th>
              <th
                scope="col"
                className="px-2 py-1.5 text-right text-[11px] uppercase tracking-wide text-slate-500"
              >
                Assets
              </th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr
                key={d.label}
                className="border-b border-slate-200 last:border-0"
              >
                <td className="px-2 py-1.5 text-[12.5px] text-slate-800">
                  {d.label}
                </td>
                <td className="px-2 py-1.5 text-right text-[12.5px] tabular-nums text-slate-800">
                  {d.value}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ left: 8, right: 24, top: 4, bottom: 4 }}
            >
              <CartesianGrid horizontal={false} stroke={GRID} />
              <XAxis
                type="number"
                allowDecimals={false}
                stroke={GRID}
                tick={{ fill: AXIS_INK, fontSize: 11 }}
              />
              <YAxis
                type="category"
                dataKey="label"
                width={150}
                stroke={GRID}
                tick={{ fill: AXIS_INK, fontSize: 11 }}
              />
              <Tooltip
                cursor={{ fill: "rgba(2,132,199,0.06)" }}
                contentStyle={{
                  background: "#ffffff",
                  border: "1px solid #cbd5e1",
                  borderRadius: 6,
                  fontSize: 12,
                  color: "#0f172a",
                }}
              />
              {/* Thin mark, rounded data-end anchored to the baseline. */}
              <Bar
                name="Assets"
                dataKey="value"
                fill={MARK}
                radius={[0, 4, 4, 0]}
                barSize={14}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}

function ExpiryList({
  title,
  rows,
  dateOf,
}: {
  title: string;
  rows: Asset[];
  dateOf: (a: Asset) => string | null;
}) {
  return (
    <Panel title={title}>
      {rows.length === 0 ? (
        <p className="py-4 text-center text-[12.5px] text-slate-500">
          Nothing in the next 90 days.
        </p>
      ) : (
        <ul className="divide-y divide-slate-200">
          {rows.slice(0, 10).map((a) => {
            const days = daysUntil(dateOf(a));
            return (
              <li
                key={a.id}
                className="flex items-center justify-between gap-3 py-1.5"
              >
                <div className="min-w-0">
                  <Link
                    to={`/itsm/assets/${a.id}`}
                    className="text-[12.5px] font-medium text-sky-700 hover:underline"
                  >
                    {a.assetTag}
                  </Link>
                  <p className="truncate text-[11.5px] text-slate-500">
                    {a.name}
                  </p>
                </div>
                <span className="shrink-0 text-[11.5px] text-amber-700">
                  {days !== null && days < 0 ? "Expired" : `${days} days`}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

export function AssetReportsPage() {
  const { assets: rawAssets } = useItsmState();
  const assets = rawAssets.map(toAssetDisplay);
  const [location, setLocation] = useState("");
  const [assetType, setAssetType] = useState("");

  const rows = useMemo(
    () =>
      assets.filter(
        (a) =>
          (!location || a.location === location) &&
          (!assetType || a.assetType === assetType),
      ),
    [assets, location, assetType],
  );

  const byState = useMemo(
    () =>
      Object.entries({
        in_stock: "In Stock",
        assigned: "Assigned",
        in_use: "In Use",
        under_repair: "Under Repair",
        reserved: "Reserved",
        lost: "Lost",
        retired: "Retired",
        disposed: "Disposed",
      })
        .map(([key, label]) => ({
          label,
          value: rows.filter((a) => a.status === key).length,
        }))
        .filter((d) => d.value > 0),
    [rows],
  );

  const byType = useMemo(() => tally(rows, (a) => a.assetType ?? ""), [rows]);
  const byLocation = useMemo(
    () => tally(rows, (a) => a.location ?? ""),
    [rows],
  );
  const byDepartment = useMemo(
    () => tally(rows, (a) => a.department ?? ""),
    [rows],
  );
  const byVendor = useMemo(() => tally(rows, (a) => a.vendor ?? ""), [rows]);

  const warrantySoon = rows
    .filter((a) => isExpiringSoon(a.warrantyExpiry))
    .sort((a, b) =>
      (a.warrantyExpiry ?? "").localeCompare(b.warrantyExpiry ?? ""),
    );
  const eolSoon = rows
    .filter((a) => isExpiringSoon(a.endOfLife))
    .sort((a, b) => (a.endOfLife ?? "").localeCompare(b.endOfLife ?? ""));
  const unassigned = rows.filter((a) => !a.assignedTo);

  return (
    <div className="space-y-4 pb-10">
      <PageHeader
        title="Asset Reports"
        crumbs={[{ label: "Assets", to: "/itsm/assets" }, { label: "Reports" }]}
        description="Inventory posture across state, type, location, department, and vendor."
      />

      {/* One filter row scoping every card below. */}
      <div className="flex flex-wrap gap-3 rounded-lg border border-slate-200 bg-white p-3">
        <label className="flex flex-col gap-0.5">
          <span className="text-[10.5px] uppercase tracking-wide text-slate-500">
            Location
          </span>
          <select
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            className="min-w-[180px] rounded-md border border-slate-300 bg-white px-2 py-1 text-[12px] text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          >
            <option value="">All locations</option>
            {/* Locations not yet in backend */}
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="text-[10.5px] uppercase tracking-wide text-slate-500">
            Asset type
          </span>
          <select
            value={assetType}
            onChange={(e) => setAssetType(e.target.value)}
            className="min-w-[160px] rounded-md border border-slate-300 bg-white px-2 py-1 text-[12px] text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          >
            <option value="">All types</option>
            {ASSET_TYPES.map((t) => (
              <option key={t.id} value={t.name}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatTile
          label="Total assets"
          value={rows.length}
          hint="Matching the current filters"
        />
        <StatTile
          label="Total value"
          value={formatTotals(
            rows.map((r) => ({
              cost: r.cost ?? 0,
              currency: (r.currency as "INR" | "USD") ?? "INR",
            })),
          )}
          hint="Grouped by currency — never converted"
        />
        <StatTile
          label="Unassigned"
          value={unassigned.length}
          hint="No owner recorded"
        />
        <StatTile
          label="Warranty ≤ 90 days"
          value={warrantySoon.length}
          tone="warn"
          hint="Includes already expired"
        />
        <StatTile
          label="End of life ≤ 90 days"
          value={eolSoon.length}
          tone="warn"
          hint="Plan replacement"
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <ChartCard title="Assets by state" data={byState} />
        <ChartCard title="Assets by type" data={byType} />
        <ChartCard title="Assets by location" data={byLocation} />
        <ChartCard title="Assets by department" data={byDepartment} />
        <ChartCard title="Assets by vendor" data={byVendor} />

        <Panel title="Unassigned assets">
          {unassigned.length === 0 ? (
            <p className="py-4 text-center text-[12.5px] text-slate-500">
              Every asset has an owner.
            </p>
          ) : (
            <ul className="divide-y divide-slate-200">
              {unassigned.slice(0, 10).map((a) => (
                <li
                  key={a.id}
                  className="flex items-center justify-between gap-3 py-1.5"
                >
                  <div className="min-w-0">
                    <Link
                      to={`/itsm/assets/${a.id}`}
                      className="text-[12.5px] font-medium text-sky-700 hover:underline"
                    >
                      {a.assetTag}
                    </Link>
                    <p className="truncate text-[11.5px] text-slate-500">
                      {a.name} · managed by {personName(a.managedBy)}
                    </p>
                  </div>
                  <StatusBadge status={a.assetState} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <ExpiryList
          title="Nearing warranty expiry"
          rows={warrantySoon}
          dateOf={(a) => a.warrantyExpiry}
        />
        <ExpiryList
          title="Nearing end of life"
          rows={eolSoon}
          dateOf={(a) => a.endOfLife}
        />
      </div>
    </div>
  );
}
