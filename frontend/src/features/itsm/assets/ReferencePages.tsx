/** Reference data views: asset types, locations, and vendors. */

import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { PageHeader } from '../components/chrome';
import { Panel, StatusBadge } from '../components/ui';
import { ASSET_TYPES, LOCATIONS, VENDORS } from '../data/reference';
import { useItsmState } from '../data/store';

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
  const { assets } = useItsmState();

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    assets.forEach((a) => map.set(a.assetType, (map.get(a.assetType) ?? 0) + 1));
    return map;
  }, [assets]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Asset Types"
        crumbs={[{ label: 'Assets', to: '/itsm/assets' }, { label: 'Asset Types' }]}
        description="Categories used to classify every record in the inventory."
      />
      <Panel>
        <RefTable headers={['Type', 'Category', 'Description', 'Assets']}>
          {ASSET_TYPES.map((t) => (
            <tr key={t.id} className="border-b border-slate-200 last:border-0">
              <td className="px-3 py-2 text-[13px] font-medium text-slate-900">{t.name}</td>
              <td className="px-3 py-2 text-[12.5px] text-slate-500">{t.category}</td>
              <td className="px-3 py-2 text-[12.5px] text-slate-500">{t.description}</td>
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

export function LocationsPage() {
  const { assets } = useItsmState();

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    assets.forEach((a) => map.set(a.location, (map.get(a.location) ?? 0) + 1));
    return map;
  }, [assets]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Locations"
        crumbs={[{ label: 'Assets', to: '/itsm/assets' }, { label: 'Locations' }]}
        description="Sites where assets are deployed or stored."
      />
      <Panel>
        <RefTable headers={['Location', 'City', 'Country', 'Timezone', 'Assets']}>
          {LOCATIONS.map((l) => (
            <tr key={l.id} className="border-b border-slate-200 last:border-0">
              <td className="px-3 py-2 text-[13px] font-medium text-slate-900">{l.name}</td>
              <td className="px-3 py-2 text-[12.5px] text-slate-500">{l.city}</td>
              <td className="px-3 py-2 text-[12.5px] text-slate-500">{l.country}</td>
              <td className="px-3 py-2 text-[12.5px] text-slate-500">{l.timezone}</td>
              <td className="px-3 py-2 text-[12.5px] text-slate-800">
                {counts.get(l.name) ?? 0}
              </td>
            </tr>
          ))}
        </RefTable>
      </Panel>
    </div>
  );
}

export function VendorsPage() {
  const { assets } = useItsmState();

  const stats = useMemo(() => {
    const map = new Map<string, { count: number; spend: number }>();
    assets.forEach((a) => {
      const cur = map.get(a.vendor) ?? { count: 0, spend: 0 };
      map.set(a.vendor, { count: cur.count + 1, spend: cur.spend + a.cost });
    });
    return map;
  }, [assets]);

  const inr = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  });

  return (
    <div className="space-y-4">
      <PageHeader
        title="Vendors"
        crumbs={[{ label: 'Assets', to: '/itsm/assets' }, { label: 'Vendors' }]}
        description="Suppliers and support contacts for the estate."
      />
      <Panel>
        <RefTable headers={['Vendor', 'Contact', 'Email', 'Phone', 'Assets', 'Total spend']}>
          {VENDORS.map((v) => {
            const s = stats.get(v.name);
            return (
              <tr key={v.id} className="border-b border-slate-200 last:border-0">
                <td className="px-3 py-2">
                  <span className="text-[13px] font-medium text-slate-900">{v.name}</span>
                  <a
                    href={v.supportUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-2 text-[11.5px] text-sky-700 hover:underline"
                  >
                    Support
                  </a>
                </td>
                <td className="px-3 py-2 text-[12.5px] text-slate-500">{v.contactName}</td>
                <td className="px-3 py-2 text-[12.5px] text-slate-500">{v.email}</td>
                <td className="px-3 py-2 text-[12.5px] text-slate-500">{v.phone}</td>
                <td className="px-3 py-2 text-[12.5px] text-slate-800">{s?.count ?? 0}</td>
                <td className="px-3 py-2 text-[12.5px] text-slate-800">
                  {inr.format(s?.spend ?? 0)}
                </td>
              </tr>
            );
          })}
        </RefTable>
      </Panel>

      <Panel title="Assets without a known vendor">
        {assets.filter((a) => !VENDORS.some((v) => v.name === a.vendor)).length === 0 ? (
          <p className="text-[12.5px] text-slate-500">
            Every asset maps to a registered vendor.
          </p>
        ) : (
          <ul className="space-y-1">
            {assets
              .filter((a) => !VENDORS.some((v) => v.name === a.vendor))
              .map((a) => (
                <li key={a.id} className="flex items-center justify-between text-[12.5px]">
                  <Link to={`/itsm/assets/${a.id}`} className="text-sky-700 hover:underline">
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
