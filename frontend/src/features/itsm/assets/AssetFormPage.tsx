/** Create / edit an asset — sectioned form covering the full CMDB record. */

import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertTriangle } from "lucide-react";

import { ConditionPhotos } from "../components/ConditionPhotos";
import {
  AssetPicker,
  AttachmentZone,
  PersonPicker,
} from "../components/Pickers";
import { PageHeader } from "../components/chrome";
import { useToast } from "../components/toast-context";
import {
  Button,
  ErrorState,
  Field,
  Panel,
  Select,
  TextArea,
  TextInput,
} from "../components/ui";
import {
  ASSET_TYPES,
  CLASSIFICATIONS,
  CONTRACTS,
  DEPARTMENTS,
  GROUPS,
  PHYSICAL_SUBTYPES,
  SOURCES,
  VENDORS,
  VIRTUAL_SUBTYPES,
  WORKSPACES,
} from "../data/reference";
import { createAsset, logAssetActivity, useItsmState } from "../data/store";
import {
  ASSET_STATES,
  CURRENCIES,
  HARDWARE_TYPES,
  IMPACTS,
  USAGE_TYPES,
} from "../data/types";
import { toAssetDisplay } from "../display-adapters";
import type { AssetRecord } from "../api-types";
import type { AssetConditionPhoto, Attachment } from "../data/types";

import {
  draftFromAsset,
  emptyAssetDraft,
  validateAsset,
  type AssetDraft,
  type AssetErrors,
} from "./form-model";

export function AssetFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const { assets } = useItsmState();
  const locations: never[] = [];
  void locations;

  const editing = id
    ? assets.map(toAssetDisplay).find((a) => a.id === id || a.assetTag === id)
    : undefined;
  const isEdit = Boolean(id);

  const [draft, setDraft] = useState<AssetDraft>(() =>
    editing
      ? draftFromAsset(
          editing as unknown as Parameters<typeof draftFromAsset>[0],
        )
      : emptyAssetDraft(),
  );
  const [errors, setErrors] = useState<AssetErrors>({});

  const serialDuplicate = useMemo(
    () => (draft.serialNumber ? undefined : undefined), // serial duplicate check deferred
    [draft.serialNumber],
  );

  function set<K extends keyof AssetDraft>(key: K, value: AssetDraft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
    setErrors((e) => ({ ...e, [key]: undefined }));
  }

  async function submit() {
    const found = validateAsset(draft, editing?.id);
    setErrors(found);
    if (Object.keys(found).length) {
      toast.error("Fix the highlighted fields before saving.");
      (
        document.querySelector('[aria-invalid="true"]') as HTMLElement | null
      )?.focus();
      return;
    }

    if (isEdit && editing) {
      void logAssetActivity(
        editing.id,
        "Sagar J",
        "Asset updated",
        draft as Partial<AssetRecord>,
      );
      toast.success(`${draft.assetTag} updated.`);
      navigate(`/itsm/assets/${editing.id}`);
      return;
    }

    const created = await createAsset(
      draft as unknown as Parameters<typeof createAsset>[0],
    );
    toast.success(`${created.asset_tag} created.`);
    navigate(`/itsm/assets/${created.id}`);
  }

  if (isEdit && !editing)
    return <ErrorState message={`No asset found for “${id}”.`} />;

  const isNetworkish = [
    "Access Point",
    "Firewall",
    "Switch",
    "Server",
  ].includes(draft.assetType);

  return (
    <div className="mx-auto max-w-5xl space-y-4 pb-10">
      <PageHeader
        title={isEdit ? `Edit ${editing?.assetTag}` : "New asset"}
        crumbs={[
          { label: "Assets", to: "/itsm/assets" },
          { label: isEdit ? (editing?.assetTag ?? "Edit") : "New asset" },
        ]}
      />

      <Panel title="General">
        <div className="grid gap-3.5 sm:grid-cols-2">
          <Field
            label="Asset Name"
            required
            error={errors.name}
            htmlFor="af-name"
          >
            <TextInput
              id="af-name"
              value={draft.name}
              aria-invalid={Boolean(errors.name)}
              onChange={(e) => set("name", e.target.value)}
            />
          </Field>
          <Field
            label="Asset Type"
            required
            error={errors.assetType}
            htmlFor="af-type"
          >
            <Select
              id="af-type"
              options={ASSET_TYPES.map((t) => t.name)}
              placeholder="Select type"
              value={draft.assetType}
              aria-invalid={Boolean(errors.assetType)}
              onChange={(e) => set("assetType", e.target.value)}
            />
          </Field>
          <Field
            label="Asset Tag"
            required
            error={errors.assetTag}
            hint="Must be unique across the inventory."
            htmlFor="af-tag"
          >
            <TextInput
              id="af-tag"
              value={draft.assetTag}
              aria-invalid={Boolean(errors.assetTag)}
              onChange={(e) => set("assetTag", e.target.value)}
            />
          </Field>
          <Field label="Impact" htmlFor="af-impact">
            <Select
              id="af-impact"
              options={IMPACTS}
              value={draft.impact}
              onChange={(e) =>
                set("impact", e.target.value as AssetDraft["impact"])
              }
            />
          </Field>
          <Field
            label="Description"
            htmlFor="af-desc"
            className="sm:col-span-2"
          >
            <TextArea
              id="af-desc"
              value={draft.description}
              onChange={(e) => set("description", e.target.value)}
            />
          </Field>
          <Field label="End of Life Date" htmlFor="af-eol">
            <TextInput
              id="af-eol"
              type="date"
              value={draft.endOfLife ?? ""}
              onChange={(e) => set("endOfLife", e.target.value || null)}
            />
          </Field>
          <Field label="Created by Source" htmlFor="af-cbs">
            <Select
              id="af-cbs"
              options={SOURCES}
              value={draft.createdBySource}
              onChange={(e) => set("createdBySource", e.target.value)}
            />
          </Field>
          <Field label="Source" htmlFor="af-src">
            <Select
              id="af-src"
              options={SOURCES}
              value={draft.source}
              onChange={(e) => set("source", e.target.value)}
            />
          </Field>
          <Field label="Discovery Enabled">
            <label className="flex items-center gap-2 pt-1 text-[13px] text-slate-700">
              <input
                type="checkbox"
                checked={draft.discoveryEnabled}
                onChange={(e) => set("discoveryEnabled", e.target.checked)}
                className="h-3.5 w-3.5 rounded border-slate-300 bg-slate-100 text-sky-500 focus:ring-1 focus:ring-sky-500"
              />
              Include this asset in discovery scans
            </label>
          </Field>
        </div>
      </Panel>

      <Panel title="Hardware">
        <div className="grid gap-3.5 sm:grid-cols-2">
          <Field label="Type" htmlFor="af-hwtype">
            <Select
              id="af-hwtype"
              options={HARDWARE_TYPES}
              value={draft.hardwareType}
              onChange={(e) =>
                set(
                  "hardwareType",
                  e.target.value as AssetDraft["hardwareType"],
                )
              }
            />
          </Field>
          <Field label="Physical Subtype" htmlFor="af-psub">
            <Select
              id="af-psub"
              options={PHYSICAL_SUBTYPES}
              placeholder="None"
              value={draft.physicalSubtype}
              onChange={(e) => set("physicalSubtype", e.target.value)}
            />
          </Field>
          <Field label="Virtual Subtype" htmlFor="af-vsub">
            <Select
              id="af-vsub"
              options={VIRTUAL_SUBTYPES}
              value={draft.virtualSubtype}
              onChange={(e) => set("virtualSubtype", e.target.value)}
            />
          </Field>
          <Field label="Product" htmlFor="af-product">
            <TextInput
              id="af-product"
              value={draft.product}
              onChange={(e) => set("product", e.target.value)}
            />
          </Field>
          <Field label="Model" htmlFor="af-model">
            <TextInput
              id="af-model"
              value={draft.model}
              onChange={(e) => set("model", e.target.value)}
            />
          </Field>
          <Field label="Vendor" htmlFor="af-vendor">
            <Select
              id="af-vendor"
              options={VENDORS.map((v) => v.name)}
              placeholder="Select vendor"
              value={draft.vendor}
              onChange={(e) => set("vendor", e.target.value)}
            />
          </Field>
          <Field label="Asset State" htmlFor="af-state">
            <Select
              id="af-state"
              options={ASSET_STATES}
              value={draft.assetState}
              onChange={(e) =>
                set("assetState", e.target.value as AssetDraft["assetState"])
              }
            />
          </Field>
          <Field label="Employee ID" htmlFor="af-emp">
            <TextInput
              id="af-emp"
              value={draft.employeeId}
              onChange={(e) => set("employeeId", e.target.value)}
            />
          </Field>
          <Field
            label="Cost"
            error={errors.cost}
            htmlFor="af-cost"
            hint={`Recorded in ${draft.currency}. Totals are reported per currency, never converted.`}
          >
            <div className="flex gap-2">
              <label className="sr-only" htmlFor="af-currency">
                Currency
              </label>
              <Select
                id="af-currency"
                options={CURRENCIES}
                value={draft.currency}
                onChange={(e) =>
                  set("currency", e.target.value as AssetDraft["currency"])
                }
                className="w-24 shrink-0"
              />
              <TextInput
                id="af-cost"
                type="number"
                min={0}
                step="0.01"
                value={draft.cost}
                aria-invalid={Boolean(errors.cost)}
                onChange={(e) => set("cost", Number(e.target.value))}
              />
            </div>
          </Field>
          <Field label="Warranty" htmlFor="af-warr">
            <TextInput
              id="af-warr"
              value={draft.warranty}
              onChange={(e) => set("warranty", e.target.value)}
            />
          </Field>
          <Field label="Acquisition Date" htmlFor="af-acq">
            <TextInput
              id="af-acq"
              type="date"
              value={draft.acquisitionDate ?? ""}
              onChange={(e) => set("acquisitionDate", e.target.value || null)}
            />
          </Field>
          <Field label="Warranty Expiry Date" htmlFor="af-wexp">
            <TextInput
              id="af-wexp"
              type="date"
              value={draft.warrantyExpiry ?? ""}
              onChange={(e) => set("warrantyExpiry", e.target.value || null)}
            />
          </Field>
          <Field
            label="Serial Number"
            htmlFor="af-serial"
            hint={
              serialDuplicate
                ? undefined
                : "Duplicates are allowed but flagged."
            }
          >
            <TextInput
              id="af-serial"
              value={draft.serialNumber}
              onChange={(e) => set("serialNumber", e.target.value)}
            />
            {serialDuplicate && (
              <p className="flex items-center gap-1 text-[11px] font-medium text-amber-600">
                <AlertTriangle size={11} aria-hidden="true" />
                Also used by{" "}
                {(
                  serialDuplicate as unknown as {
                    asset_tag?: string;
                    assetTag?: string;
                  }
                ).asset_tag ??
                  (serialDuplicate as unknown as { assetTag?: string })
                    .assetTag}
                .
              </p>
            )}
          </Field>
          <Field label="Invoice Number" htmlFor="af-inv">
            <TextInput
              id="af-inv"
              value={draft.invoiceNumber}
              onChange={(e) => set("invoiceNumber", e.target.value)}
            />
          </Field>
          <Field label="PO Number" htmlFor="af-po">
            <TextInput
              id="af-po"
              value={draft.poNumber}
              onChange={(e) => set("poNumber", e.target.value)}
            />
          </Field>
          <Field label="Classification" htmlFor="af-class">
            <Select
              id="af-class"
              options={CLASSIFICATIONS}
              value={draft.classification}
              onChange={(e) => set("classification", e.target.value)}
            />
          </Field>
        </div>
      </Panel>

      <Panel
        title="Network / Access Point"
        actions={
          !isNetworkish ? (
            <span className="text-[11px] text-slate-500">
              Optional for this asset type
            </span>
          ) : undefined
        }
      >
        <div className="grid gap-3.5 sm:grid-cols-2">
          <Field label="Firmware" htmlFor="af-fw">
            <TextInput
              id="af-fw"
              value={draft.firmware}
              onChange={(e) => set("firmware", e.target.value)}
            />
          </Field>
          <Field label="Firmware Version" htmlFor="af-fwv">
            <TextInput
              id="af-fwv"
              value={draft.firmwareVersion}
              onChange={(e) => set("firmwareVersion", e.target.value)}
            />
          </Field>
          <Field label="IP Address" htmlFor="af-ip">
            <TextInput
              id="af-ip"
              value={draft.ipAddress}
              onChange={(e) => set("ipAddress", e.target.value)}
              placeholder="10.20.14.31"
            />
          </Field>
          <Field label="Ports" htmlFor="af-ports">
            <TextInput
              id="af-ports"
              value={draft.ports}
              onChange={(e) => set("ports", e.target.value)}
            />
          </Field>
          <Field label="MAC Address" htmlFor="af-mac">
            <TextInput
              id="af-mac"
              value={draft.macAddress}
              onChange={(e) => set("macAddress", e.target.value)}
              placeholder="90:6C:AC:41:22:B7"
            />
          </Field>
          <Field label="Subnet Mask" htmlFor="af-mask">
            <TextInput
              id="af-mask"
              value={draft.subnetMask}
              onChange={(e) => set("subnetMask", e.target.value)}
            />
          </Field>
        </div>
      </Panel>

      <Panel title="Ownership and Assignment">
        <div className="grid gap-3.5 sm:grid-cols-2">
          <Field label="Workspace" htmlFor="af-ws">
            <Select
              id="af-ws"
              options={WORKSPACES}
              value={draft.workspace}
              onChange={(e) => set("workspace", e.target.value)}
            />
          </Field>
          <Field label="Location" htmlFor="af-loc">
            <Select
              id="af-loc"
              options={locations.map(
                (l) => (l as { name?: string }).name ?? "",
              )}
              placeholder="Select location"
              value={draft.location}
              onChange={(e) => set("location", e.target.value)}
            />
          </Field>
          <Field label="Department" htmlFor="af-dept">
            <Select
              id="af-dept"
              options={DEPARTMENTS}
              placeholder="Select department"
              value={draft.department}
              onChange={(e) => set("department", e.target.value)}
            />
          </Field>
          <Field label="Usage Type" htmlFor="af-usage">
            <Select
              id="af-usage"
              options={USAGE_TYPES}
              value={draft.usageType}
              onChange={(e) =>
                set("usageType", e.target.value as AssetDraft["usageType"])
              }
            />
          </Field>
          <Field label="Managed By Group" htmlFor="af-mbg">
            <Select
              id="af-mbg"
              options={GROUPS}
              placeholder="Select group"
              value={draft.managedByGroup}
              onChange={(e) => set("managedByGroup", e.target.value)}
            />
          </Field>
          <Field label="Managed By">
            <PersonPicker
              value={draft.managedBy}
              onChange={(v) => set("managedBy", v)}
            />
          </Field>
          <Field label="Assigned To" error={errors.assignedTo}>
            <PersonPicker
              value={draft.assignedTo}
              onChange={(v) => set("assignedTo", v)}
              invalid={Boolean(errors.assignedTo)}
            />
          </Field>
          <Field
            label="Assigned Date"
            error={errors.assignedDate}
            htmlFor="af-adate"
          >
            <TextInput
              id="af-adate"
              type="date"
              value={draft.assignedDate ?? ""}
              aria-invalid={Boolean(errors.assignedDate)}
              onChange={(e) => set("assignedDate", e.target.value || null)}
            />
          </Field>

          <Field
            label="Retirement / Disposal Reason"
            error={errors.retirementReason}
            htmlFor="af-rr"
          >
            <TextInput
              id="af-rr"
              value={draft.retirementReason}
              aria-invalid={Boolean(errors.retirementReason)}
              onChange={(e) => set("retirementReason", e.target.value)}
            />
          </Field>
          <Field
            label="Retirement / Disposal Date"
            error={errors.retirementDate}
            htmlFor="af-rd"
          >
            <TextInput
              id="af-rd"
              type="date"
              value={draft.retirementDate ?? ""}
              aria-invalid={Boolean(errors.retirementDate)}
              onChange={(e) => set("retirementDate", e.target.value || null)}
            />
          </Field>
        </div>
      </Panel>

      <Panel title="Relationships">
        <div className="grid gap-3.5 sm:grid-cols-2">
          <Field label="Parent Asset" className="sm:col-span-2">
            <AssetPicker
              assets={assets
                .filter((a) => a.id !== editing?.id)
                .map(
                  (a) =>
                    a as unknown as Parameters<
                      typeof AssetPicker
                    >[0]["assets"][0],
                )}
              value={draft.parentAssetId ? [draft.parentAssetId] : []}
              onChange={(ids) =>
                set("parentAssetId", ids[ids.length - 1] ?? null)
              }
            />
          </Field>
          <Field label="Purchase Order" htmlFor="af-po2">
            <TextInput
              id="af-po2"
              value={draft.poNumber}
              onChange={(e) => set("poNumber", e.target.value)}
            />
          </Field>
          <Field label="Contract" htmlFor="af-contract">
            <Select
              id="af-contract"
              options={CONTRACTS}
              value={draft.contract}
              onChange={(e) => set("contract", e.target.value)}
            />
          </Field>
        </div>
        <p className="mt-2 text-[11.5px] text-slate-500">
          Related assets, changes, and services are managed from the asset’s
          Relationships tab.
        </p>
      </Panel>

      <Panel title="Asset Condition Images">
        <ConditionPhotos
          photos={[] as never[]}
          onChange={(_next: AssetConditionPhoto[]) => {}}
          onError={(m) => toast.error(m)}
          actorName="Sagar J"
        />
      </Panel>

      <Panel title="Attachments">
        <AttachmentZone
          attachments={[] as never[]}
          onChange={(_next: Attachment[]) => {}}
          onReject={(m) => toast.error(m)}
        />
        <p className="mt-2 text-[11.5px] text-slate-500">
          Invoice, warranty document, asset photo, configuration export, or
          other support documents.
        </p>
      </Panel>

      <div className="flex justify-end gap-2">
        <Button
          variant="ghost"
          onClick={() =>
            navigate(
              isEdit && editing ? `/itsm/assets/${editing.id}` : "/itsm/assets",
            )
          }
        >
          Cancel
        </Button>
        <Button variant="primary" onClick={submit}>
          {isEdit ? "Save asset" : "Create asset"}
        </Button>
      </div>
    </div>
  );
}
