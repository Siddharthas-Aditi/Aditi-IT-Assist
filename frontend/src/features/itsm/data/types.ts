/**
 * Domain types for the ITSM Change + Asset modules.
 *
 * These mirror the shape a real backend would return so the mock store can be
 * swapped for API calls without touching page components.
 */

// ── Shared ─────────────────────────────────────────────────────────────

export const PRIORITIES = ['Low', 'Medium', 'High', 'Urgent'] as const;
export type Priority = (typeof PRIORITIES)[number];

export const IMPACTS = ['Low', 'Medium', 'High'] as const;
export type Impact = (typeof IMPACTS)[number];

export const RISKS = ['Low', 'Medium', 'High'] as const;
export type Risk = (typeof RISKS)[number];

/** Low/medium/high scales share one visual treatment across the app. */
export type Level = 'Low' | 'Medium' | 'High' | 'Urgent';

export interface Person {
  id: string;
  name: string;
  email: string;
  department: string;
}

// ── Change management ──────────────────────────────────────────────────

export const CHANGE_STATUSES = [
  'Draft',
  'Open',
  'Planning',
  'Pending Approval',
  'Scheduled',
  'In Progress',
  'Completed',
  'Rejected',
  'Cancelled',
] as const;
export type ChangeStatus = (typeof CHANGE_STATUSES)[number];

/** Columns rendered on the change board, in order. */
export const CHANGE_BOARD_STATUSES: ChangeStatus[] = [
  'Draft',
  'Planning',
  'Pending Approval',
  'Scheduled',
  'In Progress',
  'Completed',
];

export const CHANGE_TYPES = ['Standard', 'Normal', 'Emergency'] as const;
export type ChangeType = (typeof CHANGE_TYPES)[number];

export const APPROVAL_DECISIONS = ['Pending', 'Approved', 'Rejected'] as const;
export type ApprovalDecision = (typeof APPROVAL_DECISIONS)[number];

export interface ApprovalStage {
  id: string;
  stage: number;
  name: string;
  approverId: string;
  approverName: string;
  decision: ApprovalDecision;
  comments: string;
  decidedAt: string | null;
}

export interface ImplementationTask {
  id: string;
  label: string;
  done: boolean;
}

/** The nine free-text planning fields captured on every change. */
export interface ChangePlanning {
  reasonForChange: string;
  impactAnalysis: string;
  rolloutPlan: string;
  backupPlan: string;
  validationPlan: string;
  communicationPlan: string;
  implementationSteps: string;
  rollbackTrigger: string;
  postImplementationReview: string;
}

export interface ActivityEntry {
  id: string;
  at: string;
  actor: string;
  action: string;
  detail?: string;
}

export interface Attachment {
  id: string;
  name: string;
  sizeBytes: number;
  kind: string;
  uploadedAt: string;
}

export interface Change {
  id: string;
  changeId: string;
  /** Set when the change was raised from a support ticket. */
  sourceTicketId: string | null;
  sourceTicketNumber: string | null;
  workspace: string;
  requesterId: string;
  subject: string;
  changeType: ChangeType;
  status: ChangeStatus;
  priority: Priority;
  impact: Impact;
  risk: Risk;
  group: string;
  agentId: string | null;
  description: string;
  plannedStart: string;
  plannedEnd: string;
  actualStart: string | null;
  actualEnd: string | null;
  department: string;
  category: string;
  maintenanceWindow: string;
  /** Asset ids this change touches. */
  assetIds: string[];
  attachments: Attachment[];
  planning: ChangePlanning;
  approvals: ApprovalStage[];
  implementationTasks: ImplementationTask[];
  closureNotes: string;
  /** Required when changeType === 'Emergency'. */
  emergencyJustification: string;
  activity: ActivityEntry[];
  createdAt: string;
  updatedAt: string;
}

export interface ChangeTemplate {
  id: string;
  name: string;
  changeType: ChangeType;
  defaultPriority: Priority;
  defaultImpact: Impact;
  defaultRisk: Risk;
  defaultCategory: string;
  defaultDepartment: string;
  defaultMaintenanceWindow: string;
  requiredApprovals: string[];
  planning: ChangePlanning;
  archived: boolean;
  lastUsedAt: string | null;
  createdAt: string;
}

// ── Asset management ───────────────────────────────────────────────────

export const ASSET_STATES = [
  'In Stock',
  'Assigned',
  'In Use',
  'Under Repair',
  'Reserved',
  'Lost',
  'Retired',
  'Disposed',
] as const;
export type AssetState = (typeof ASSET_STATES)[number];

export const USAGE_TYPES = ['Permanent', 'Loaner', 'Temporary', 'Shared'] as const;
export type UsageType = (typeof USAGE_TYPES)[number];

export const HARDWARE_TYPES = ['Physical', 'Virtual'] as const;
export type HardwareType = (typeof HARDWARE_TYPES)[number];

export const CURRENCIES = ['INR', 'USD'] as const;
export type CurrencyCode = (typeof CURRENCIES)[number];

export const CURRENCY_LABELS: Record<CurrencyCode, string> = {
  INR: '₹ Indian Rupee (INR)',
  USD: '$ US Dollar (USD)',
};

export const ASSET_CONDITIONS = [
  'New',
  'Good',
  'Fair',
  'Minor Damage',
  'Damaged',
  'Faulty',
] as const;
export type AssetCondition = (typeof ASSET_CONDITIONS)[number];

/**
 * A dated condition photo.
 *
 * `dataUrl` holds a downscaled JPEG rather than the original upload — the
 * draft UI previously retained it in browser storage, and full-resolution photos would blow the
 * quota after a handful of assets.
 */
export interface AssetConditionPhoto {
  id: string;
  name: string;
  condition: AssetCondition;
  note: string;
  dataUrl: string;
  capturedAt: string;
  capturedBy: string;
}

export const RELATIONSHIP_TARGETS = [
  'User',
  'Change',
  'Vendor',
  'Purchase Order',
  'Contract',
  'Parent Asset',
  'Child Asset',
  'Application / Service',
] as const;
export type RelationshipTarget = (typeof RELATIONSHIP_TARGETS)[number];

export interface AssetRelationship {
  id: string;
  targetType: RelationshipTarget;
  targetId: string;
  targetLabel: string;
  owner: string;
  createdAt: string;
}

export interface Asset {
  id: string;

  // General
  assetTag: string;
  name: string;
  assetType: string;
  impact: Impact;
  description: string;
  endOfLife: string | null;
  discoveryEnabled: boolean;
  createdBySource: string;
  source: string;

  // Hardware
  hardwareType: HardwareType;
  physicalSubtype: string;
  virtualSubtype: string;
  product: string;
  model: string;
  vendor: string;
  assetState: AssetState;
  employeeId: string;
  cost: number;
  /** Currency the `cost` figure is denominated in. */
  currency: CurrencyCode;
  warranty: string;
  acquisitionDate: string | null;
  warrantyExpiry: string | null;
  serialNumber: string;
  invoiceNumber: string;
  poNumber: string;
  classification: string;

  // Network / access point
  firmware: string;
  firmwareVersion: string;
  ipAddress: string;
  ports: string;
  macAddress: string;
  subnetMask: string;

  // Ownership and assignment
  workspace: string;
  location: string;
  department: string;
  usageType: UsageType;
  managedByGroup: string;
  managedBy: string;
  assignedTo: string;
  assignedDate: string | null;

  // Lifecycle bookkeeping
  retirementReason: string;
  retirementDate: string | null;

  // Relationships
  parentAssetId: string | null;
  relationships: AssetRelationship[];
  contract: string;

  /** Dated photographic record of the asset's physical condition. */
  conditionPhotos: AssetConditionPhoto[];
  attachments: Attachment[];
  activity: ActivityEntry[];
  createdAt: string;
  updatedAt: string;
}

// ── Reference data ─────────────────────────────────────────────────────

export interface AssetTypeRef {
  id: string;
  name: string;
  category: string;
  description: string;
}

export interface LocationRef {
  id: string;
  name: string;
  country: string;
  city: string;
  timezone: string;
}

export interface VendorRef {
  id: string;
  name: string;
  contactName: string;
  email: string;
  phone: string;
  supportUrl: string;
}
