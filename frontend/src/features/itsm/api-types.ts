/**
 * Backend-aligned types for the Changes and Assets domain.
 *
 * Mirrors the Pydantic schemas from backend/app/schemas/change.py and
 * backend/app/schemas/asset.py (snake_case, as FastAPI returns them).
 */

// ── Change ────────────────────────────────────────────────────────────

export type ChangeType = "standard" | "normal" | "emergency";

export type ChangeStatus =
  | "draft"
  | "submitted"
  | "planning"
  | "pending_approval"
  | "scheduled"
  | "in_progress"
  | "implemented"
  | "rolled_back"
  | "rejected"
  | "cancelled"
  | "closed";

export type ApprovalDecision = "pending" | "approved" | "rejected";

export interface ChangePlanningData {
  reason_for_change: string;
  impact_analysis: string;
  rollout_plan: string;
  backup_plan: string;
  validation_plan: string;
  communication_plan: string;
  implementation_steps: string;
  rollback_trigger: string;
  post_implementation_review: string;
}

export interface ChangeApproval {
  id: string;
  change_id: string;
  stage: number;
  approver_id: string;
  decision: ApprovalDecision;
  comments: string;
  decided_at: string | null;
  created_at: string;
}

export interface ChangeTask {
  id: string;
  change_id: string;
  label: string;
  done: boolean;
  position: number;
  created_at: string;
}

export interface ChangeEvent {
  id: string;
  change_id: string;
  actor_id: string | null;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  detail: string | null;
  created_at: string;
}

export interface ChangeRecord {
  id: string;
  change_number: string;
  source_ticket_id: string | null;
  requested_by_id: string;
  assigned_to_id: string | null;
  title: string;
  description: string;
  change_type: ChangeType;
  status: ChangeStatus;
  priority: string;
  impact: string;
  risk: string;
  department: string | null;
  category: string | null;
  maintenance_window: string | null;
  planned_start: string | null;
  planned_end: string | null;
  actual_start: string | null;
  actual_end: string | null;
  closure_notes: string;
  emergency_justification: string;
  planning_data: ChangePlanningData;
  approvals: ChangeApproval[];
  tasks: ChangeTask[];
  events: ChangeEvent[];
  created_at: string;
  updated_at: string;
}

export interface ChangeListResponse {
  items: ChangeRecord[];
  total: number;
}

export interface LinkedAsset {
  id: string;
  asset_tag: string;
  name: string;
  status: AssetStatus;
}

export interface ChangeAssetLinksResponse {
  items: LinkedAsset[];
}

export interface ChangeCreatePayload {
  title: string;
  description?: string;
  change_type?: ChangeType;
  priority?: string;
  impact?: string;
  risk?: string;
  department?: string;
  category?: string;
  maintenance_window?: string;
  planned_start?: string;
  planned_end?: string;
  emergency_justification?: string;
  planning_data?: Partial<ChangePlanningData>;
  source_ticket_id?: string;
  asset_ids?: string[];
}

export interface ChangeUpdatePayload {
  title?: string;
  description?: string;
  priority?: string;
  impact?: string;
  risk?: string;
  department?: string;
  category?: string;
  maintenance_window?: string;
  planned_start?: string | null;
  planned_end?: string | null;
  emergency_justification?: string;
  planning_data?: Partial<ChangePlanningData>;
  assigned_to_id?: string | null;
  closure_notes?: string;
}

export interface ChangeTransitionPayload {
  to_status: ChangeStatus;
  comment?: string;
}

export interface ApprovalCreatePayload {
  approver_id: string;
  stage: number;
}

export interface ApprovalDecidePayload {
  decision: ApprovalDecision;
  comments?: string;
}

export interface ChangeTaskCreatePayload {
  label: string;
  position?: number;
}

export interface ChangeTaskUpdatePayload {
  done?: boolean;
  label?: string;
}

// ── Asset ─────────────────────────────────────────────────────────────

export type AssetStatus =
  | "in_stock"
  | "assigned"
  | "in_use"
  | "under_repair"
  | "reserved"
  | "lost"
  | "retired"
  | "disposed";

export type AssetHardwareType = "physical" | "virtual";
export type AssetUsageType = "permanent" | "loaner" | "temporary" | "shared";
export type AssetCondition =
  | "new"
  | "good"
  | "fair"
  | "minor_damage"
  | "damaged"
  | "faulty";

export interface AssetEvent {
  id: string;
  asset_id: string;
  actor_id: string | null;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  detail: string | null;
  created_at: string;
}

export interface AssetRecord {
  id: string;
  asset_tag: string;
  name: string;
  asset_type: string;
  impact: string;
  description: string;
  status: AssetStatus;
  hardware_type: AssetHardwareType;
  usage_type: AssetUsageType;
  condition: AssetCondition;
  physical_subtype: string | null;
  virtual_subtype: string | null;
  product: string | null;
  model: string | null;
  vendor: string | null;
  serial_number: string | null;
  classification: string | null;
  cost: number | null;
  currency: string | null;
  warranty_info: string | null;
  acquisition_date: string | null;
  warranty_expiry: string | null;
  invoice_number: string | null;
  po_number: string | null;
  contract: string | null;
  ip_address: string | null;
  mac_address: string | null;
  location: string | null;
  department: string | null;
  managed_by_group: string | null;
  assigned_to_id: string | null;
  assigned_date: string | null;
  end_of_life: string | null;
  retirement_reason: string | null;
  retirement_date: string | null;
  source: string | null;
  parent_asset_id: string | null;
  events: AssetEvent[];
  created_at: string;
  updated_at: string;
}

export interface AssetListResponse {
  items: AssetRecord[];
  total: number;
}

export interface LinkedChange {
  id: string;
  change_number: string;
  title: string;
  status: ChangeStatus;
}

export interface LinkedTicket {
  id: string;
  ticket_number: string;
  title: string;
  status: string;
  priority: string;
}

export interface AssetChangeLinksResponse {
  items: LinkedChange[];
}

export interface AssetTicketLinksResponse {
  items: LinkedTicket[];
}

export interface AssetCreatePayload {
  asset_tag: string;
  name: string;
  asset_type?: string;
  impact?: string;
  description?: string;
  hardware_type?: AssetHardwareType;
  usage_type?: AssetUsageType;
  condition?: AssetCondition;
  vendor?: string;
  product?: string;
  model?: string;
  serial_number?: string;
  location?: string;
  department?: string;
  cost?: number;
  currency?: string;
  warranty_info?: string;
  acquisition_date?: string;
  warranty_expiry?: string;
  invoice_number?: string;
  po_number?: string;
  source?: string;
}

export interface AssetUpdatePayload {
  name?: string;
  asset_type?: string;
  impact?: string;
  description?: string;
  hardware_type?: AssetHardwareType;
  usage_type?: AssetUsageType;
  condition?: AssetCondition;
  vendor?: string;
  product?: string;
  model?: string;
  serial_number?: string;
  location?: string;
  department?: string;
  managed_by_group?: string;
  cost?: number;
  currency?: string;
  warranty_info?: string;
  acquisition_date?: string | null;
  warranty_expiry?: string | null;
  invoice_number?: string;
  po_number?: string;
  end_of_life?: string | null;
}

export interface AssetAssignPayload {
  assigned_to_id: string;
  assigned_date?: string;
}

export interface AssetRetirePayload {
  status: "retired" | "disposed";
  retirement_reason: string;
  retirement_date: string;
}

// ── Allowed transitions (mirrors backend CHANGE_TRANSITIONS) ──────────

export const CHANGE_TRANSITIONS: Record<ChangeStatus, ChangeStatus[]> = {
  draft: ["submitted", "planning", "cancelled"],
  submitted: ["planning", "pending_approval", "cancelled"],
  planning: ["pending_approval", "scheduled", "cancelled"],
  pending_approval: ["scheduled", "rejected", "planning", "cancelled"],
  scheduled: ["in_progress", "planning", "cancelled"],
  in_progress: ["implemented", "rolled_back", "cancelled"],
  implemented: ["closed"],
  rolled_back: ["planning"],
  rejected: ["planning"],
  cancelled: [],
  closed: [],
};

export const CHANGE_TERMINAL: Set<ChangeStatus> = new Set([
  "closed",
  "cancelled",
]);
export const ASSET_TERMINAL: Set<AssetStatus> = new Set([
  "retired",
  "disposed",
]);

/** Human-readable labels for Change statuses. */
export const CHANGE_STATUS_LABELS: Record<ChangeStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  planning: "Planning",
  pending_approval: "Pending Approval",
  scheduled: "Scheduled",
  in_progress: "In Progress",
  implemented: "Implemented",
  rolled_back: "Rolled Back",
  rejected: "Rejected",
  cancelled: "Cancelled",
  closed: "Closed",
};

/** Human-readable labels for Asset statuses. */
export const ASSET_STATUS_LABELS: Record<AssetStatus, string> = {
  in_stock: "In Stock",
  assigned: "Assigned",
  in_use: "In Use",
  under_repair: "Under Repair",
  reserved: "Reserved",
  lost: "Lost",
  retired: "Retired",
  disposed: "Disposed",
};
