import { describe, expect, it } from 'vitest';

import {
  canMoveAsset,
  canMoveChange,
  initialStatusFor,
  isExpiringSoon,
  requiresAssignee,
  requiresRetirementReason,
} from './rules';
import type { Asset, Change } from './types';

function change(over: Partial<Change> = {}): Change {
  return {
    id: 'c1',
    changeId: 'CHG-1001',
    sourceTicketId: null,
    sourceTicketNumber: null,
    workspace: 'IT Operations',
    requesterId: 'u-sagar',
    subject: 'Patch servers',
    changeType: 'Normal',
    status: 'Planning',
    priority: 'Medium',
    impact: 'Low',
    risk: 'Low',
    group: 'Infrastructure',
    agentId: null,
    description: '<p>x</p>',
    plannedStart: new Date().toISOString(),
    plannedEnd: new Date(Date.now() + 3600_000).toISOString(),
    actualStart: null,
    actualEnd: null,
    department: 'Engineering',
    category: 'Server',
    maintenanceWindow: 'Weeknight',
    assetIds: [],
    attachments: [],
    planning: {
      reasonForChange: '',
      impactAnalysis: '',
      rolloutPlan: '',
      backupPlan: '',
      validationPlan: '',
      communicationPlan: '',
      implementationSteps: '',
      rollbackTrigger: '',
      postImplementationReview: '',
    },
    approvals: [],
    implementationTasks: [],
    closureNotes: '',
    emergencyJustification: '',
    activity: [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    ...over,
  };
}

function asset(over: Partial<Asset> = {}): Asset {
  return {
    id: 'a1',
    assetTag: 'BLR_LT1',
    name: 'Laptop',
    assetType: 'Laptop',
    impact: 'Low',
    description: '',
    endOfLife: null,
    discoveryEnabled: false,
    createdBySource: 'Manual',
    source: 'Manual',
    hardwareType: 'Physical',
    physicalSubtype: 'Laptop',
    virtualSubtype: 'Not Applicable',
    product: 'ThinkPad',
    model: 'T14',
    vendor: 'Lenovo India',
    assetState: 'In Stock',
    employeeId: '',
    cost: 1000,
    warranty: '3 years',
    acquisitionDate: null,
    warrantyExpiry: null,
    serialNumber: 'SN1',
    invoiceNumber: '',
    poNumber: '',
    patchManaged: false,
    classification: 'Internal',
    dtaEndorsement: '',
    domain: '',
    lastAuditDate: null,
    region: 'APAC',
    availabilityZone: 'ap-south-1a',
    firmware: '',
    firmwareVersion: '',
    ipAddress: '',
    ports: '',
    macAddress: '',
    subnetMask: '',
    workspace: 'IT Operations',
    location: 'India – Bangalore',
    department: 'Engineering',
    usageType: 'Permanent',
    managedByGroup: 'IT Team',
    managedBy: 'u-sagar',
    assignedTo: '',
    assignedDate: null,
    retirementReason: '',
    retirementDate: null,
    parentAssetId: null,
    relationships: [],
    contract: 'No Contract',
    attachments: [],
    activity: [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    ...over,
  };
}

describe('change workflow', () => {
  it('rejects a transition that is not on the state graph', () => {
    const verdict = canMoveChange(change({ status: 'Completed' }), 'Planning');
    expect(verdict.ok).toBe(false);
  });

  it('blocks scheduling a Normal change with outstanding approvals', () => {
    const verdict = canMoveChange(
      change({
        status: 'Pending Approval',
        approvals: [
          {
            id: 'a',
            stage: 1,
            name: 'Lead',
            approverId: 'u1',
            approverName: 'Lead',
            decision: 'Pending',
            comments: '',
            decidedAt: null,
          },
        ],
      }),
      'Scheduled',
    );
    expect(verdict.ok).toBe(false);
    expect(verdict.reason).toMatch(/approval/i);
  });

  it('allows a Standard change to schedule without approval', () => {
    const verdict = canMoveChange(
      change({ changeType: 'Standard', status: 'Planning' }),
      'Scheduled',
    );
    expect(verdict.ok).toBe(true);
  });

  it('requires closure notes before completing', () => {
    const base = change({ status: 'In Progress' });
    expect(canMoveChange(base, 'Completed').ok).toBe(false);
    expect(canMoveChange({ ...base, closureNotes: 'Done.' }, 'Completed').ok).toBe(true);
  });

  it('routes submitted changes by type', () => {
    expect(initialStatusFor('Standard')).toBe('Planning');
    expect(initialStatusFor('Normal')).toBe('Pending Approval');
    expect(initialStatusFor('Emergency')).toBe('Pending Approval');
  });
});

describe('asset lifecycle', () => {
  it('cannot assign a disposed or retired asset', () => {
    for (const state of ['Disposed', 'Retired'] as const) {
      const verdict = canMoveAsset(asset({ assetState: state }), 'Assigned', {
        assignedTo: 'u-sagar',
        assignedDate: '2026-01-01',
      });
      expect(verdict.ok).toBe(false);
    }
  });

  it('requires assignee and date for Assigned / In Use', () => {
    expect(requiresAssignee('Assigned')).toBe(true);
    expect(requiresAssignee('In Use')).toBe(true);
    expect(requiresAssignee('In Stock')).toBe(false);

    expect(canMoveAsset(asset(), 'In Use').ok).toBe(false);
    expect(
      canMoveAsset(asset(), 'In Use', { assignedTo: 'u-sagar', assignedDate: '2026-01-01' }).ok,
    ).toBe(true);
  });

  it('requires a reason and date to retire or dispose', () => {
    expect(requiresRetirementReason('Retired')).toBe(true);
    expect(canMoveAsset(asset(), 'Retired').ok).toBe(false);
    expect(
      canMoveAsset(asset(), 'Retired', {
        retirementReason: 'Beyond repair',
        retirementDate: '2026-01-01',
      }).ok,
    ).toBe(true);
  });
});

describe('expiry window', () => {
  it('flags dates inside 90 days and already-expired dates', () => {
    const soon = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);
    const past = new Date(Date.now() - 10 * 86400000).toISOString().slice(0, 10);
    const far = new Date(Date.now() + 400 * 86400000).toISOString().slice(0, 10);

    expect(isExpiringSoon(soon)).toBe(true);
    expect(isExpiringSoon(past)).toBe(true);
    expect(isExpiringSoon(far)).toBe(false);
    expect(isExpiringSoon(null)).toBe(false);
  });
});
