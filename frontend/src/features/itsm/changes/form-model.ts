/** Draft shape and validation for the change form. */

import type {
  Change,
  ChangePlanning,
  ChangeStatus,
  ChangeTemplate,
  ChangeType,
  Impact,
  Priority,
  Risk,
} from '../data/types';

export interface ChangeDraft {
  workspace: string;
  requesterId: string;
  subject: string;
  changeType: ChangeType;
  status: ChangeStatus;
  priority: Priority;
  impact: Impact;
  risk: Risk;
  group: string;
  agentId: string;
  description: string;
  plannedStart: string;
  plannedEnd: string;
  department: string;
  category: string;
  maintenanceWindow: string;
  assetIds: string[];
  emergencyJustification: string;
  planning: ChangePlanning;
}

export const EMPTY_PLANNING: ChangePlanning = {
  reasonForChange: '',
  impactAnalysis: '',
  rolloutPlan: '',
  backupPlan: '',
  validationPlan: '',
  communicationPlan: '',
  implementationSteps: '',
  rollbackTrigger: '',
  postImplementationReview: '',
};

/** The nine planning textareas, in display order. */
export const PLANNING_FIELDS: { key: keyof ChangePlanning; label: string; hint: string }[] = [
  { key: 'reasonForChange', label: 'Reason for Change', hint: 'Why this work is needed.' },
  { key: 'impactAnalysis', label: 'Impact Analysis', hint: 'Who and what is affected.' },
  { key: 'rolloutPlan', label: 'Rollout Plan', hint: 'How the change is applied.' },
  { key: 'backupPlan', label: 'Backup Plan', hint: 'What is captured before starting.' },
  { key: 'validationPlan', label: 'Validation Plan', hint: 'How success is confirmed.' },
  { key: 'communicationPlan', label: 'Communication Plan', hint: 'Who is told, and when.' },
  { key: 'implementationSteps', label: 'Implementation Steps', hint: 'One step per line.' },
  { key: 'rollbackTrigger', label: 'Rollback Trigger', hint: 'The condition that aborts the change.' },
  {
    key: 'postImplementationReview',
    label: 'Post-Implementation Review Notes',
    hint: 'Completed after the change lands.',
  },
];

export function emptyDraft(): ChangeDraft {
  return {
    workspace: 'IT Operations',
    requesterId: '',
    subject: '',
    changeType: 'Normal',
    status: 'Open',
    priority: 'Medium',
    impact: 'Low',
    risk: 'Low',
    group: '',
    agentId: '',
    description: '',
    plannedStart: '',
    plannedEnd: '',
    department: '',
    category: '',
    maintenanceWindow: '',
    assetIds: [],
    emergencyJustification: '',
    planning: { ...EMPTY_PLANNING },
  };
}

export function draftFromChange(change: Change): ChangeDraft {
  return {
    workspace: change.workspace,
    requesterId: change.requesterId,
    subject: change.subject,
    changeType: change.changeType,
    status: change.status,
    priority: change.priority,
    impact: change.impact,
    risk: change.risk,
    group: change.group,
    agentId: change.agentId ?? '',
    description: change.description,
    plannedStart: change.plannedStart.slice(0, 16),
    plannedEnd: change.plannedEnd.slice(0, 16),
    department: change.department,
    category: change.category,
    maintenanceWindow: change.maintenanceWindow,
    assetIds: [...change.assetIds],
    emergencyJustification: change.emergencyJustification,
    planning: { ...change.planning },
  };
}

export function applyTemplate(draft: ChangeDraft, tpl: ChangeTemplate): ChangeDraft {
  return {
    ...draft,
    changeType: tpl.changeType,
    priority: tpl.defaultPriority,
    impact: tpl.defaultImpact,
    risk: tpl.defaultRisk,
    category: tpl.defaultCategory,
    department: tpl.defaultDepartment,
    maintenanceWindow: tpl.defaultMaintenanceWindow,
    planning: { ...tpl.planning },
  };
}

export type ChangeErrors = Partial<Record<keyof ChangeDraft, string>>;

/**
 * Validate the required fields.
 *
 * Draft saves skip validation entirely — the point of a draft is to capture
 * incomplete work — so this only runs on submit.
 */
export function validateChange(draft: ChangeDraft): ChangeErrors {
  const errors: ChangeErrors = {};

  if (!draft.workspace) errors.workspace = 'Workspace is required.';
  if (!draft.requesterId) errors.requesterId = 'Select a requester.';
  if (!draft.subject.trim()) errors.subject = 'Subject is required.';
  else if (draft.subject.trim().length < 5) errors.subject = 'Use at least 5 characters.';
  if (!draft.changeType) errors.changeType = 'Change type is required.';
  if (!draft.status) errors.status = 'Status is required.';

  const plain = draft.description.replace(/<[^>]*>/g, '').trim();
  if (!plain) errors.description = 'Description is required.';

  if (!draft.plannedStart) errors.plannedStart = 'Planned start is required.';
  if (!draft.plannedEnd) errors.plannedEnd = 'Planned end is required.';
  if (
    draft.plannedStart &&
    draft.plannedEnd &&
    new Date(draft.plannedEnd) <= new Date(draft.plannedStart)
  ) {
    errors.plannedEnd = 'Planned end must be after the planned start.';
  }

  if (draft.changeType === 'Emergency' && !draft.emergencyJustification.trim()) {
    errors.emergencyJustification = 'An emergency change requires a justification.';
  }

  return errors;
}

export const MAX_ATTACHMENT_BYTES = 40 * 1024 * 1024;
