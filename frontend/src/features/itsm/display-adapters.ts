/**
 * Compatibility adapters between the backend API types and the ITSM UI.
 */

import type {
  ApprovalDecision,
  AssetEvent,
  AssetHardwareType,
  AssetRecord,
  AssetStatus,
  AssetUsageType,
  ChangePlanningData,
  ChangeEvent,
  ChangeRecord,
  ChangeTask,
  ChangeType,
} from "./api-types";
import type { AssetRelationship } from "./data/types";

// ── Change display type ────────────────────────────────────────────────

export interface ChangeApprovalDisplay {
  id: string;
  change_id: string;
  stage: number;
  approver_id: string;
  name: string;
  approverName: string;
  decision: ApprovalDecision;
  comments: string;
  decided_at: string | null;
  decidedAt: string | null;
  created_at: string;
}

export interface ChangeDisplay extends Omit<
  ChangeRecord,
  "approvals" | "tasks" | "events"
> {
  approvals: ChangeApprovalDisplay[];
  tasks: ChangeTask[];
  events: ChangeEvent[];
  changeId: string;
  subject: string;
  changeType: ChangeType;
  plannedStart: string | null;
  plannedEnd: string | null;
  actualStart: string | null;
  actualEnd: string | null;
  requesterId: string;
  agentId: string | null;
  closureNotes: string;
  emergencyJustification: string;
  sourceTicketId: string | null;
  sourceTicketNumber: string | null;
  group: string;
  createdAt: string;
  updatedAt: string;
  maintenanceWindow: string | null;
  planning: ChangePlanningData;
  activity: (ChangeEvent & { at: string; actor: string; action: string })[];
  attachments: never[];
  assetIds: string[];
  implementationTasks: ChangeTask[];
}

export function toChangeDisplay(c: ChangeRecord): ChangeDisplay {
  const mappedEvents = c.events.map((e) => ({
    ...e,
    at: e.created_at,
    actor: e.actor_id ?? "system",
    action: e.event_type,
  }));
  return {
    ...c,
    changeId: c.change_number,
    subject: c.title,
    changeType: c.change_type,
    plannedStart: c.planned_start,
    plannedEnd: c.planned_end,
    actualStart: c.actual_start,
    actualEnd: c.actual_end,
    requesterId: c.requested_by_id,
    agentId: c.assigned_to_id,
    closureNotes: c.closure_notes,
    emergencyJustification: c.emergency_justification,
    sourceTicketId: c.source_ticket_id,
    sourceTicketNumber: null,
    group: "",
    createdAt: c.created_at,
    updatedAt: c.updated_at,
    maintenanceWindow: c.maintenance_window,
    planning: c.planning_data,
    approvals: c.approvals.map((a) => ({
      ...a,
      name: a.approver_id,
      approverName: a.approver_id,
      decidedAt: a.decided_at,
    })),
    activity: mappedEvents,
    attachments: [],
    assetIds: [],
    implementationTasks: c.tasks,
  };
}

// ── Asset display type ─────────────────────────────────────────────────

export type { AssetRelationship };

export interface AssetDisplay extends AssetRecord {
  assetTag: string;
  assetType: string;
  assetState: AssetStatus;
  assignedTo: string | null;
  assignedDate: string | null;
  warrantyExpiry: string | null;
  endOfLife: string | null;
  acquisitionDate: string | null;
  retirementDate: string | null;
  retirementReason: string | null;
  hardwareType: AssetHardwareType;
  usageType: AssetUsageType;
  physicalSubtype: string | null;
  virtualSubtype: string | null;
  serialNumber: string | null;
  invoiceNumber: string | null;
  poNumber: string | null;
  ipAddress: string | null;
  macAddress: string | null;
  managedBy: string | null;
  managedByGroup: string | null;
  parentAssetId: string | null;
  createdAt: string;
  updatedAt: string;
  activity: (AssetEvent & { at: string; actor: string; action: string })[];
  conditionPhotos: never[];
  relationships: AssetRelationship[];
  attachments: never[];
  ticketAssetLinks: never[];
  workspace: string;
  employeeId: string | null;
  discoveryEnabled: boolean;
  createdBySource: string;
  ports: string | null;
  subnetMask: string | null;
  firmware: string | null;
  firmwareVersion: string | null;
  warranty: string | null;
  contract: string | null;
}

export function toAssetDisplay(a: AssetRecord): AssetDisplay {
  const mappedEvents = a.events.map((e) => ({
    ...e,
    at: e.created_at,
    actor: e.actor_id ?? "system",
    action: e.event_type,
  }));
  return {
    ...a,
    assetTag: a.asset_tag,
    assetType: a.asset_type,
    assetState: a.status,
    assignedTo: a.assigned_to_id,
    assignedDate: a.assigned_date,
    warrantyExpiry: a.warranty_expiry,
    endOfLife: a.end_of_life,
    acquisitionDate: a.acquisition_date,
    retirementDate: a.retirement_date,
    retirementReason: a.retirement_reason,
    hardwareType: a.hardware_type,
    usageType: a.usage_type,
    physicalSubtype: a.physical_subtype,
    virtualSubtype: a.virtual_subtype,
    serialNumber: a.serial_number,
    invoiceNumber: a.invoice_number,
    poNumber: a.po_number,
    ipAddress: a.ip_address,
    macAddress: a.mac_address,
    managedBy: a.managed_by_group,
    managedByGroup: a.managed_by_group,
    parentAssetId: a.parent_asset_id,
    createdAt: a.created_at,
    updatedAt: a.updated_at,
    activity: mappedEvents,
    conditionPhotos: [],
    relationships: [],
    attachments: [],
    ticketAssetLinks: [],
    workspace: "",
    employeeId: null,
    discoveryEnabled: false,
    createdBySource: "manual",
    ports: null,
    subnetMask: null,
    firmware: null,
    firmwareVersion: null,
    warranty: a.warranty_info,
    contract: a.contract,
  };
}
