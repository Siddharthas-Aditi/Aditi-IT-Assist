/** Device Execution API types — mirror of `backend/app/schemas/device_execution.py`. */

export type ActionKind = 'install_app' | 'remediation' | 'device_action';
export type RiskTier = 'low' | 'medium' | 'high';

export interface CatalogEntry {
  id: string;
  kind: ActionKind;
  display_name: string;
  risk_tier: RiskTier;
  reversible: boolean;
  description: string;
}

export interface DeviceCatalog {
  catalog_version: string;
  policy_version: string;
  autonomous_enabled: boolean;
  autonomous_medium_allowed: boolean;
  apps: CatalogEntry[];
  remediations: CatalogEntry[];
  device_actions: CatalogEntry[];
}

/** The device tool a catalog entry kind maps to. */
export const TOOL_FOR_KIND: Record<ActionKind, string> = {
  install_app: 'install_win32_app',
  remediation: 'run_remediation_script',
  device_action: 'device_action',
};

export interface DeviceActionRequest {
  tool_name: string;
  action_ref: string;
  device_id: string;
  employee_id: string;
  idempotency_key: string;
  justification: string;
  reason: string;
}

export type DeviceActionStatus =
  | 'executed'
  | 'pending_approval'
  | 'denied'
  | 'rejected'
  | 'error';

export type DeviceActionDecision = 'autonomous' | 'human_approval' | 'deny';

export interface DeviceActionOutcome {
  status: DeviceActionStatus;
  decision: DeviceActionDecision;
  tool_name: string;
  action_ref: string;
  device_id: string;
  risk_tier: RiskTier | null;
  reason: string;
  approval_id: string | null;
  result: Record<string, unknown> | null;
  policy_signals: string[];
  policy_version: string;
}

export interface DeviceApprovalDecision {
  employee_id: string;
}
