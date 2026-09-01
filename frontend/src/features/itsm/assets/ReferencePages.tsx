/** Reference data views: asset types, locations, and vendors. */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Pencil, Plus, Trash2 } from "lucide-react";

import { PageHeader } from "../components/chrome";
import { useToast } from "../components/toast-context";
import { Button, Field, Panel, StatusBadge, TextInput } from "../components/ui";
import { ASSET_TYPES, COUNTRIES, VENDORS } from "../data/reference";
import { formatTotals } from "../data/money";
import {
  createLocation,
  deleteLocation,
  updateLocation,
  useItsmState,
} from "../data/store";
import { toAssetDisplay } from "../display-adapters";

/** Shared table shell so all three reference pages read identically. */
function RefTable({
  headers,
  children,
}: {
  headers: string[];
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-slate-200">
            {headers.map((h) => (
              <th
                key={h}
                scope="col"
                className="whitespace-nowrap px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function AssetTypesPage() {
  const { assets: rawAssets } = useItsmState();
  const assets = rawAssets.map(toAssetDisplay);

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    assets.forEach((a) =>
      map.set(a.assetType, (map.get(a.assetType) ?? 0) + 1),
    );
    return map;
  }, [assets]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Asset Types"
        crumbs={[
          { label: "Assets", to: "/itsm/assets" },
          { label: "Asset Types" },
        ]}
        description="Categories used to classify every record in the inventory."
      />
      <Panel>
        <RefTable headers={["Type", "Category", "Description", "Assets"]}>
          {ASSET_TYPES.map((t) => (
            <tr key={t.id} className="border-b border-slate-200 last:border-0">
              <td className="px-3 py-2 text-[13px] font-medium text-slate-900">
                {t.name}
              </td>
              <td className="px-3 py-2 text-[12.5px] text-slate-500">
                {t.category}
              </td>
              <td className="px-3 py-2 text-[12.5px] text-slate-500">
                {t.description}
              </td>
              <td className="px-3 py-2">
                <Link
                  to={`/itsm/assets?type=${encodeURIComponent(t.name)}`}
                  className="text-[12.5px] text-sky-700 hover:underline"
                >
                  {counts.get(t.name) ?? 0}
                </Link>
              </td>
            </tr>
          ))}
        </RefTable>
      </Panel>
    </div>
  );
}

const BLANK_LOCATION = {
  name: "",
  country: "India",
  city: "",
  timezone: "Asia/Kolkata",
};

export function LocationsPage() {
  const { assets: rawAssets2, locations } = useItsmState();
  const assets = rawAssets2.map(toAssetDisplay);
  const toast = useToast();
  const [editing, setEditing] = useState<
    (typeof BLANK_LOCATION & { id?: string }) | null
  >(null);

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    assets.forEach((a) =>
      map.set(a.location ?? "", (map.get(a.location ?? "") ?? 0) + 1),
    );
    return map;
  }, [assets]);

  function save() {
    if (!editing) return;
    const name = editing.name.trim();
    if (!name) {
      toast.error("Location name is required.");
      return;
    }
    const clash = locations.some(
      (l) =>
        l.id !== editing.id &&
        l.name.trim().toLowerCase() === name.toLowerCase(),
    );
    if (clash) {
      toast.error(`“${name}” already exists.`);
      return;
    }

    if (editing.id) {
      updateLocation(editing.id, { ...editing, name });
      toast.success(`${name} updated. Assets at this site were moved with it.`);
    } else {
      createLocation({ ...editing, name });
      toast.success(`${name} added.`);
    }
    setEditing(null);
  }

  function remove(id: string, name: string) {
    const inUse = counts.get(name) ?? 0;
    if (inUse > 0) {
      toast.error(
        `${name} still has ${inUse} asset${inUse > 1 ? "s" : ""}. Move them before deleting it.`,
      );
      return;
    }
    deleteLocation(id);
    toast.info(`${name} removed.`);
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Locations"
        crumbs={[
          { label: "Assets", to: "/itsm/assets" },
          { label: "Locations" },
        ]}
        description="Sites where assets are deployed or stored. Add as many as you need."
        actions={
          <Button
            variant="primary"
            onClick={() => setEditing({ ...BLANK_LOCATION })}
          >
            <Plus size={14} /> Add location
          </Button>
        }
      />

      {editing && (
        <Panel title={editing.id ? "Edit location" : "New location"}>
          <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Location name" required htmlFor="loc-name">
              <TextInput
                id="loc-name"
                value={editing.name}
                placeholder="India - Chennai"
                onChange={(e) =>
                  setEditing({ ...editing, name: e.target.value })
                }
              />
            </Field>
            <Field label="Country" htmlFor="loc-country">
              <TextInput
                id="loc-country"
                list="itsm-countries"
                value={editing.country}
                onChange={(e) =>
                  setEditing({ ...editing, country: e.target.value })
                }
              />
              {/* A datalist offers USA/India without blocking anything else. */}
              <datalist id="itsm-countries">
                {COUNTRIES.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </Field>
            <Field label="City" htmlFor="loc-city">
              <TextInput
                id="loc-city"
                value={editing.city}
                onChange={(e) =>
                  setEditing({ ...editing, city: e.target.value })
                }
              />
            </Field>
            <Field label="Timezone" htmlFor="loc-tz">
              <TextInput
                id="loc-tz"
                value={editing.timezone}
                onChange={(e) =>
                  setEditing({ ...editing, timezone: e.target.value })
                }
              />
            </Field>
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={save}>
              Save location
            </Button>
          </div>
        </Panel>
      )}

      <Panel>
        <RefTable
          headers={["Location", "City", "Country", "Timezone", "Assets", ""]}
        >
          {locations.map((l) => {
            const inUse = counts.get(l.name) ?? 0;
            return (
              <tr
                key={l.id}
                className="border-b border-slate-200 last:border-0"
              >
                <td className="px-3 py-2 text-[13px] font-medium text-slate-900">
                  {l.name}
                </td>
                <td className="px-3 py-2 text-[12.5px] text-slate-500">
                  {l.city}
                </td>
                <td className="px-3 py-2 text-[12.5px] text-slate-500">
                  {l.country}
                </td>
                <td className="px-3 py-2 text-[12.5px] text-slate-500">
                  {l.timezone}
                </td>
                <td className="px-3 py-2 text-[12.5px] text-slate-800">
                  {inUse}
                </td>
                <td className="px-3 py-2">
                  <div className="flex justify-end gap-1">
                    <Button onClick={() => setEditing({ ...l })}>
                      <Pencil size={12} /> Edit
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => remove(l.id, l.name)}
                      title={
                        inUse > 0
                          ? `${inUse} asset(s) still at this location`
                          : "Delete this location"
                      }
                      aria-label={`Delete ${l.name}`}
                    >
                      <Trash2 size={12} />
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </RefTable>
      </Panel>
    </div>
  );
}

export function VendorsPage() {
  const { assets: rawAssets } = useItsmState();
  const assets = rawAssets.map(toAssetDisplay);

  const stats = useMemo(() => {
    const map = new Map<
      string,
      { count: number; rows: { cost: number; currency: "INR" | "USD" }[] }
    >();
    assets.forEach((a) => {
      const cur = map.get(a.vendor ?? "") ?? { count: 0, rows: [] };
      cur.count += 1;
      cur.rows.push({
        cost: a.cost ?? 0,
        currency: (a.currency as "INR" | "USD") ?? "INR",
      });
      map.set(a.vendor ?? "", cur);
    });
    return map;
  }, [assets]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Vendors"
        crumbs={[{ label: "Assets", to: "/itsm/assets" }, { label: "Vendors" }]}
        description="Suppliers and support contacts for the estate."
      />
      <Panel>
        <RefTable
          headers={[
            "Vendor",
            "Contact",
            "Email",
            "Phone",
            "Assets",
            "Total spend",
          ]}
        >
          {VENDORS.map((v) => {
            const s = stats.get(v.name);
            return (
              <tr
                key={v.id}
                className="border-b border-slate-200 last:border-0"
              >
                <td className="px-3 py-2">
                  <span className="text-[13px] font-medium text-slate-900">
                    {v.name}
                  </span>
                  <a
                    href={v.supportUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-2 text-[11.5px] text-sky-700 hover:underline"
                  >
                    Support
                  </a>
                </td>
                <td className="px-3 py-2 text-[12.5px] text-slate-500">
                  {v.contactName}
                </td>
                <td className="px-3 py-2 text-[12.5px] text-slate-500">
                  {v.email}
                </td>
                <td className="px-3 py-2 text-[12.5px] text-slate-500">
                  {v.phone}
                </td>
                <td className="px-3 py-2 text-[12.5px] text-slate-800">
                  {s?.count ?? 0}
                </td>
                <td className="px-3 py-2 text-[12.5px] text-slate-800">
                  {formatTotals(s?.rows ?? [])}
                </td>
              </tr>
            );
          })}
        </RefTable>
      </Panel>

      <Panel title="Assets without a known vendor">
        {assets.filter((a) => !VENDORS.some((v) => v.name === a.vendor))
          .length === 0 ? (
          <p className="text-[12.5px] text-slate-500">
            Every asset maps to a registered vendor.
          </p>
        ) : (
          <ul className="space-y-1">
            {assets
              .filter((a) => !VENDORS.some((v) => v.name === a.vendor))
              .map((a) => (
                <li
                  key={a.id}
                  className="flex items-center justify-between text-[12.5px]"
                >
                  <Link
                    to={`/itsm/assets/${a.id}`}
                    className="text-sky-700 hover:underline"
                  >
                    {a.assetTag}
                  </Link>
                  <StatusBadge status={a.assetState} />
                </li>
              ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
