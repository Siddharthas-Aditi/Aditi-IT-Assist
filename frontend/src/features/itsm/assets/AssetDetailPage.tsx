/** Asset detail — tabbed record with a quick-update property panel. */

import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, Network } from "lucide-react";

import { PageHeader, Tabs } from "../components/chrome";
import { ConditionPhotos } from "../components/ConditionPhotos";
import { useToast } from "../components/toast-context";
import {
  Button,
  DetailRow,
  EmptyState,
  ErrorState,
  Field,
  LevelIndicator,
  Panel,
  Select,
  StatusBadge,
  TextInput,
} from "../components/ui";
import { DEPARTMENTS, GROUPS, personName } from "../data/reference";
import { formatMoney } from "../data/money";
import { canMoveAsset, daysUntil, isExpiringSoon } from "../data/rules";
import { logAssetActivity, useItsmState } from "../data/store";
import { ASSET_STATES, IMPACTS, USAGE_TYPES } from "../data/types";
import type { AssetDisplay as Asset, AssetDisplay } from "../display-adapters";
import type { AssetRelationship } from "../data/types";
import { toAssetDisplay } from "../display-adapters";
import { RelationshipMap } from "./RelationshipMap";

const TABS = [
  "Overview",
  "Relationships",
  "Condition",
  "Components",
  "Associations",
  "Purchase Orders",
  "Contracts",
  "Expenses",
  "Assignment",
  "Activity",
] as const;

const ACTOR = "Sagar J";

function fmt(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function ExpiryValue({ date }: { date: string | null }) {
  if (!date) return <>—</>;
  const days = daysUntil(date);
  if (!isExpiringSoon(date)) return <>{fmt(date)}</>;
  return (
    <span className="inline-flex items-center gap-1 text-amber-700">
      <AlertTriangle size={11} aria-hidden="true" />
      {fmt(date)}
      <span className="text-[11px] text-amber-600">
        ({days !== null && days < 0 ? "expired" : `${days} days`})
      </span>
    </span>
  );
}

export function AssetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const { assets, changes } = useItsmState();
  const locations: string[] = [];
  void locations;
  const [tab, setTab] = useState<string>("Overview");

  const assetRaw = useMemo(
    () => assets.find((a) => a.id === id || a.asset_tag === id),
    [assets, id],
  );
  const asset = useMemo(
    () => (assetRaw ? toAssetDisplay(assetRaw) : undefined),
    [assetRaw],
  );

  // Quick-panel edits are staged until the user presses Update.
  const [quick, setQuick] = useState<Partial<AssetDisplay>>({});

  if (!asset) return <ErrorState message={`No asset found for "${id}".`} />;

  const merged = { ...asset, ...quick };
  const children = assets
    .map(toAssetDisplay)
    .filter((a) => a.parentAssetId === asset.id);
  const parent = assets
    .map(toAssetDisplay)
    .find((a) => a.id === asset.parentAssetId);
  const relatedChanges = changes.filter((c) => c.id === ""); // asset-change links need separate query
  const ticketLinks: never[] = [];
  void ticketLinks;

  function applyQuick() {
    if (!asset) return;
    if (Object.keys(quick).length === 0) {
      toast.info("Nothing to update.");
      return;
    }
    if (quick.assetState && quick.assetState !== asset.assetState) {
      const verdict = canMoveAsset(
        asset as unknown as Parameters<typeof canMoveAsset>[0],
        quick.assetState! as unknown as Parameters<typeof canMoveAsset>[1],
        quick as unknown as Parameters<typeof canMoveAsset>[2],
      );
      if (!verdict.ok) {
        toast.error(verdict.reason ?? "That lifecycle change is not allowed.");
        return;
      }
    }
    logAssetActivity(asset.id, ACTOR, "Properties updated", quick);
    setQuick({});
    toast.success("Asset updated.");
  }

  function addRelationship(rel: AssetRelationship) {
    if (!asset) return;
    logAssetActivity(
      asset.id,
      ACTOR,
      `Associated ${rel.targetType}: ${rel.targetLabel}`,
      {
        relationships: [...(asset.relationships as AssetRelationship[]), rel],
      },
    );
    toast.success("Association added.");
  }

  function removeRelationship(relId: string) {
    if (!asset) return;
    logAssetActivity(asset.id, ACTOR, "Association removed", {
      relationships: (asset.relationships as AssetRelationship[]).filter(
        (r) => r.id !== relId,
      ),
    });
    toast.info("Association removed.");
  }

  return (
    <div className="space-y-4 pb-10">
      <PageHeader
        title={`${asset.assetTag} — ${asset.name}`}
        crumbs={[
          { label: "Assets", to: "/itsm/assets" },
          { label: asset.assetTag },
        ]}
        description={`${asset.assetType} · ${asset.product || asset.model} · ${asset.location}`}
        actions={
          <>
            <StatusBadge status={asset.assetState} />
            <Button onClick={() => setTab("Relationships")}>
              <Network size={14} /> View Relationship Map
            </Button>
            <Button onClick={() => setTab("Associations")}>Associate</Button>
            <Button onClick={() => navigate(`/itsm/assets/${asset.id}/edit`)}>
              Edit
            </Button>
          </>
        }
      />

      <div className="flex flex-col gap-4 xl:flex-row">
        <Tabs
          tabs={TABS}
          active={tab}
          onChange={setTab}
          orientation="vertical"
        />

        <div className="min-w-0 flex-1 space-y-4">
          {tab === "Overview" && (
            <>
              <Panel title="General">
                <dl className="grid gap-x-6 sm:grid-cols-2">
                  <DetailRow label="Asset Name">{asset.name}</DetailRow>
                  <DetailRow label="Asset Type">{asset.assetType}</DetailRow>
                  <DetailRow label="Asset Tag">{asset.assetTag}</DetailRow>
                  <DetailRow label="Impact">
                    <LevelIndicator level={asset.impact} />
                  </DetailRow>
                  <DetailRow label="Description">{asset.description}</DetailRow>
                  <DetailRow label="End of Life">
                    <ExpiryValue date={asset.endOfLife} />
                  </DetailRow>
                  <DetailRow label="Discovery Enabled">
                    {asset.discoveryEnabled ? "Yes" : "No"}
                  </DetailRow>
                  <DetailRow label="Created by Source">
                    {asset.createdBySource}
                  </DetailRow>
                  <DetailRow label="Source">{asset.source}</DetailRow>
                </dl>
              </Panel>

              <Panel title="Hardware">
                <dl className="grid gap-x-6 sm:grid-cols-2">
                  <DetailRow label="Type">{asset.hardwareType}</DetailRow>
                  <DetailRow label="Physical Subtype">
                    {asset.physicalSubtype}
                  </DetailRow>
                  <DetailRow label="Virtual Subtype">
                    {asset.virtualSubtype}
                  </DetailRow>
                  <DetailRow label="Product">{asset.product}</DetailRow>
                  <DetailRow label="Model">{asset.model}</DetailRow>
                  <DetailRow label="Vendor">{asset.vendor}</DetailRow>
                  <DetailRow label="Asset State">
                    <StatusBadge status={asset.assetState} />
                  </DetailRow>
                  <DetailRow label="Employee ID">{asset.employeeId}</DetailRow>
                  <DetailRow label="Serial Number">
                    {asset.serialNumber}
                  </DetailRow>
                  <DetailRow label="Classification">
                    {asset.classification}
                  </DetailRow>
                </dl>
              </Panel>

              <Panel title="Access Point / Network">
                <dl className="grid gap-x-6 sm:grid-cols-2">
                  <DetailRow label="Firmware">{asset.firmware}</DetailRow>
                  <DetailRow label="Firmware Version">
                    {asset.firmwareVersion}
                  </DetailRow>
                  <DetailRow label="IP Address">{asset.ipAddress}</DetailRow>
                  <DetailRow label="Ports">{asset.ports}</DetailRow>
                  <DetailRow label="MAC Address">{asset.macAddress}</DetailRow>
                  <DetailRow label="Subnet Mask">{asset.subnetMask}</DetailRow>
                </dl>
              </Panel>

              <Panel title="Ownership and Assignment">
                <dl className="grid gap-x-6 sm:grid-cols-2">
                  <DetailRow label="Workspace">{asset.workspace}</DetailRow>
                  <DetailRow label="Location">{asset.location}</DetailRow>
                  <DetailRow label="Department">{asset.department}</DetailRow>
                  <DetailRow label="Usage Type">{asset.usageType}</DetailRow>
                  <DetailRow label="Managed By Group">
                    {asset.managedByGroup}
                  </DetailRow>
                  <DetailRow label="Managed By">
                    {personName(asset.managedBy)}
                  </DetailRow>
                  <DetailRow label="Assigned To">
                    {personName(asset.assignedTo)}
                  </DetailRow>
                  <DetailRow label="Assigned Date">
                    {fmt(asset.assignedDate)}
                  </DetailRow>
                </dl>
              </Panel>

              <Panel title="Lifecycle">
                <dl className="grid gap-x-6 sm:grid-cols-2">
                  <DetailRow label="Asset State">
                    <StatusBadge status={asset.assetState} />
                  </DetailRow>
                  <DetailRow label="Acquisition Date">
                    {fmt(asset.acquisitionDate)}
                  </DetailRow>
                  <DetailRow label="Warranty">{asset.warranty}</DetailRow>
                  <DetailRow label="Warranty Expiry">
                    <ExpiryValue date={asset.warrantyExpiry} />
                  </DetailRow>
                  <DetailRow label="End of Life">
                    <ExpiryValue date={asset.endOfLife} />
                  </DetailRow>
                  <DetailRow label="Retirement Reason">
                    {asset.retirementReason}
                  </DetailRow>
                  <DetailRow label="Retirement Date">
                    {fmt(asset.retirementDate)}
                  </DetailRow>
                </dl>
              </Panel>

              <Panel title="Financial Details">
                <dl className="grid gap-x-6 sm:grid-cols-2">
                  <DetailRow label="Cost">
                    {formatMoney(
                      asset.cost ?? 0,
                      (asset.currency as "INR" | "USD" | undefined) ??
                        undefined,
                    )}
                  </DetailRow>
                  <DetailRow label="Invoice Number">
                    {asset.invoiceNumber}
                  </DetailRow>
                  <DetailRow label="PO Number">{asset.poNumber}</DetailRow>
                  <DetailRow label="Contract">{asset.contract}</DetailRow>
                </dl>
              </Panel>
            </>
          )}

          {tab === "Relationships" && (
            <RelationshipMap
              asset={
                asset as unknown as Parameters<
                  typeof RelationshipMap
                >[0]["asset"]
              }
              onAdd={addRelationship}
              onRemove={removeRelationship}
            />
          )}

          {tab === "Condition" && (
            <Panel
              title={`Asset condition images (${asset.conditionPhotos?.length ?? 0})`}
            >
              <ConditionPhotos
                photos={asset.conditionPhotos ?? []}
                actorName={ACTOR}
                onError={(m) => toast.error(m)}
                onChange={(next) => {
                  logAssetActivity(
                    asset.id,
                    ACTOR,
                    "Condition photos updated",
                    {
                      conditionPhotos: next,
                    },
                  );
                  toast.success("Condition photos updated.");
                }}
              />
            </Panel>
          )}

          {tab === "Components" && (
            <Panel title={`Child assets (${children.length})`}>
              {parent && (
                <p className="mb-3 text-[12.5px] text-slate-500">
                  Parent asset:{" "}
                  <Link
                    to={`/itsm/assets/${parent.id}`}
                    className="text-sky-700 hover:underline"
                  >
                    {parent.assetTag}
                  </Link>
                </p>
              )}
              {children.length === 0 ? (
                <EmptyState
                  title="No components"
                  description="No assets list this record as their parent."
                />
              ) : (
                <ul className="divide-y divide-slate-200">
                  {children.map((c) => (
                    <li
                      key={c.id}
                      className="flex items-center justify-between py-2"
                    >
                      <Link
                        to={`/itsm/assets/${c.id}`}
                        className="text-[13px] text-sky-700 hover:underline"
                      >
                        {c.assetTag} — {c.name}
                      </Link>
                      <StatusBadge status={c.assetState} />
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}

          {tab === "Associations" && (
            <>
              <Panel title={`Linked support tickets (0)`}>
                <EmptyState
                  title="No linked tickets"
                  description="Specialists can link this asset from a ticket in the IT Operations workspace."
                />
              </Panel>

              <Panel title={`Associated changes (${relatedChanges.length})`}>
                {relatedChanges.length === 0 ? (
                  <EmptyState
                    title="No associated changes"
                    description="This asset is not referenced by any change record."
                  />
                ) : (
                  <ul className="divide-y divide-slate-200">
                    {relatedChanges.map((c) => (
                      <li
                        key={c.id}
                        className="flex items-center justify-between gap-3 py-2"
                      >
                        <div className="min-w-0">
                          <Link
                            to={`/itsm/changes/${c.id}`}
                            className="text-[13px] font-medium text-sky-700 hover:underline"
                          >
                            {c.change_number}
                          </Link>
                          <p className="truncate text-[12px] text-slate-500">
                            {c.title}
                          </p>
                        </div>
                        <StatusBadge status={c.status} />
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </>
          )}

          {tab === "Purchase Orders" && (
            <Panel title="Purchase orders">
              <dl className="grid gap-x-6 sm:grid-cols-2">
                <DetailRow label="PO Number">{asset.poNumber}</DetailRow>
                <DetailRow label="Invoice Number">
                  {asset.invoiceNumber}
                </DetailRow>
                <DetailRow label="Vendor">{asset.vendor}</DetailRow>
                <DetailRow label="Acquisition Date">
                  {fmt(asset.acquisitionDate)}
                </DetailRow>
              </dl>
            </Panel>
          )}

          {tab === "Contracts" && (
            <Panel title="Contracts">
              <dl className="grid gap-x-6 sm:grid-cols-2">
                <DetailRow label="Contract">{asset.contract}</DetailRow>
                <DetailRow label="Warranty">{asset.warranty}</DetailRow>
                <DetailRow label="Warranty Expiry">
                  <ExpiryValue date={asset.warrantyExpiry} />
                </DetailRow>
                <DetailRow label="Vendor">{asset.vendor}</DetailRow>
              </dl>
            </Panel>
          )}

          {tab === "Expenses" && (
            <Panel title="Expenses">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-slate-200">
                    {["Item", "Reference", "Amount"].map((h) => (
                      <th
                        key={h}
                        scope="col"
                        className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="text-[12.5px] text-slate-800">
                  <tr className="border-b border-slate-200">
                    <td className="px-2 py-1.5">Acquisition</td>
                    <td className="px-2 py-1.5 text-slate-500">
                      {asset.invoiceNumber || "—"}
                    </td>
                    <td className="px-2 py-1.5">
                      {formatMoney(
                        asset.cost ?? 0,
                        asset.currency as "INR" | "USD" | undefined,
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td className="px-2 py-1.5 font-medium">Total</td>
                    <td className="px-2 py-1.5" />
                    <td className="px-2 py-1.5 font-medium">
                      {formatMoney(
                        asset.cost ?? 0,
                        asset.currency as "INR" | "USD" | undefined,
                      )}
                    </td>
                  </tr>
                </tbody>
              </table>
            </Panel>
          )}

          {tab === "Assignment" && (
            <Panel title="Assignment history">
              <dl className="grid gap-x-6 sm:grid-cols-2">
                <DetailRow label="Assigned To">
                  {personName(asset.assignedTo)}
                </DetailRow>
                <DetailRow label="Assigned Date">
                  {fmt(asset.assignedDate)}
                </DetailRow>
                <DetailRow label="Usage Type">{asset.usageType}</DetailRow>
                <DetailRow label="Employee ID">{asset.employeeId}</DetailRow>
                <DetailRow label="Department">{asset.department}</DetailRow>
                <DetailRow label="Location">{asset.location}</DetailRow>
              </dl>
            </Panel>
          )}

          {tab === "Activity" && (
            <Panel title="Activity">
              <ol className="relative space-y-3 border-l border-slate-200 pl-4">
                {[...asset.activity].reverse().map((e) => (
                  <li key={e.id} className="relative">
                    <span
                      className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-sky-500"
                      aria-hidden="true"
                    />
                    <p className="text-[13px] text-slate-800">{e.action}</p>
                    <p className="text-[11.5px] text-slate-500">
                      {e.actor} · {new Date(e.at).toLocaleString()}
                    </p>
                  </li>
                ))}
              </ol>
            </Panel>
          )}
        </div>

        {/* Quick property panel */}
        <aside className="w-full shrink-0 space-y-3 xl:w-72">
          <Panel title="Properties">
            <dl className="mb-3 space-y-0.5 border-b border-slate-200 pb-3">
              <DetailRow label="Workspace">{asset.workspace}</DetailRow>
              <DetailRow label="Product">{asset.product}</DetailRow>
              <DetailRow label="Asset State">
                <StatusBadge status={asset.assetState} />
              </DetailRow>
              <DetailRow label="Cost">
                {formatMoney(
                  asset.cost ?? 0,
                  (asset.currency as "INR" | "USD" | undefined) ?? undefined,
                )}
              </DetailRow>
              <DetailRow label="Date of Expiry">
                <ExpiryValue date={asset.warrantyExpiry} />
              </DetailRow>
              <DetailRow label="Serial Number">{asset.serialNumber}</DetailRow>
            </dl>

            <div className="space-y-2.5">
              <Field label="Impact" htmlFor="q-impact">
                <Select
                  id="q-impact"
                  options={IMPACTS}
                  value={merged.impact}
                  onChange={(e) =>
                    setQuick((q) => ({
                      ...q,
                      impact: e.target.value as Asset["impact"],
                    }))
                  }
                />
              </Field>
              <Field label="Asset State" htmlFor="q-state">
                <Select
                  id="q-state"
                  options={ASSET_STATES}
                  value={merged.assetState}
                  onChange={(e) =>
                    setQuick((q) => ({
                      ...q,
                      status: e.target.value as Asset["assetState"],
                    }))
                  }
                />
              </Field>
              <Field label="Usage Type" htmlFor="q-usage">
                <Select
                  id="q-usage"
                  options={USAGE_TYPES}
                  value={merged.usageType}
                  onChange={(e) =>
                    setQuick((q) => ({
                      ...q,
                      usage_type: e.target.value as Asset["usageType"],
                    }))
                  }
                />
              </Field>
              <Field label="Location" htmlFor="q-loc">
                <Select
                  id="q-loc"
                  options={["(Select location)"]}
                  value={merged.location ?? ""}
                  onChange={(e) =>
                    setQuick((q) => ({ ...q, location: e.target.value }))
                  }
                />
              </Field>
              <Field label="Department" htmlFor="q-dept">
                <Select
                  id="q-dept"
                  options={DEPARTMENTS}
                  value={merged.department ?? ""}
                  onChange={(e) =>
                    setQuick((q) => ({ ...q, department: e.target.value }))
                  }
                />
              </Field>
              <Field label="Used By" htmlFor="q-used">
                <TextInput
                  id="q-used"
                  value={personName(merged.assignedTo)}
                  readOnly
                  className="opacity-70"
                />
              </Field>
              <Field label="Managed By Group" htmlFor="q-mbg">
                <Select
                  id="q-mbg"
                  options={GROUPS}
                  value={merged.managedByGroup ?? ""}
                  onChange={(e) =>
                    setQuick((q) => ({
                      ...q,
                      managed_by_group: e.target.value,
                    }))
                  }
                />
              </Field>
              <Field label="Managed By" htmlFor="q-mb">
                <TextInput
                  id="q-mb"
                  value={personName(merged.managedBy)}
                  readOnly
                  className="opacity-70"
                />
              </Field>
              <Field label="Assigned On" htmlFor="q-aon">
                <TextInput
                  id="q-aon"
                  type="date"
                  value={merged.assignedDate ?? ""}
                  onChange={(e) =>
                    setQuick((q) => ({
                      ...q,
                      assigned_date: e.target.value || null,
                    }))
                  }
                />
              </Field>
              <Field label="End of Life" htmlFor="q-eol">
                <TextInput
                  id="q-eol"
                  type="date"
                  value={merged.endOfLife ?? ""}
                  onChange={(e) =>
                    setQuick((q) => ({
                      ...q,
                      end_of_life: e.target.value || null,
                    }))
                  }
                />
              </Field>

              <Button variant="primary" onClick={applyQuick} className="w-full">
                Update
              </Button>
            </div>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
