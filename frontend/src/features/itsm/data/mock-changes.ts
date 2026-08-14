/** Seed change records — 16 rows spanning every status and change type. */

import type {
  Change,
  ChangePlanning,
  ChangeStatus,
  ChangeType,
  Impact,
  Priority,
  Risk,
} from './types';

function at(daysFromNow: number, hour = 22): string {
  const d = new Date();
  d.setDate(d.getDate() + daysFromNow);
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
}

function planning(over: Partial<ChangePlanning> = {}): ChangePlanning {
  return {
    reasonForChange: 'Scheduled maintenance to keep the estate on a supported baseline.',
    impactAnalysis: 'Limited to the named systems during the approved maintenance window.',
    rolloutPlan: 'Staged rollout with a health check between each batch.',
    backupPlan: 'Configuration export and snapshot captured before any change is applied.',
    validationPlan: 'Post-change smoke tests plus 30 minutes of dashboard observation.',
    communicationPlan: 'Advance notice to affected teams, completion note on the status page.',
    implementationSteps: 'Prepare\nApply\nVerify\nRelease',
    rollbackTrigger: 'Any failed validation step, or error rate above the agreed threshold.',
    postImplementationReview: '',
    ...over,
  };
}

interface Seed {
  subject: string;
  changeType: ChangeType;
  status: ChangeStatus;
  priority: Priority;
  impact: Impact;
  risk: Risk;
  category: string;
  department: string;
  group: string;
  requesterId: string;
  agentId: string | null;
  startIn: number;
  durationHours: number;
  assetTags?: string[];
  emergencyJustification?: string;
}

const SEEDS: Seed[] = [
  {
    subject: 'Upgrade FortiAP firmware to v7.4.6 across Bangalore floor 1',
    changeType: 'Normal',
    status: 'Scheduled',
    priority: 'High',
    impact: 'Medium',
    risk: 'Medium',
    category: 'Network',
    department: 'Shared Services – IT & Infrastructure',
    group: 'Network Operations',
    requesterId: 'u-sagar',
    agentId: 'u-madhukar',
    startIn: 3,
    durationHours: 4,
    assetTags: ['BLR_FAP10', 'BLR_FAP11'],
  },
  {
    subject: 'Monthly production server patch baseline – February',
    changeType: 'Normal',
    status: 'Pending Approval',
    priority: 'High',
    impact: 'High',
    risk: 'Medium',
    category: 'Server',
    department: 'Shared Services – IT & Infrastructure',
    group: 'Infrastructure',
    requesterId: 'u-madhukar',
    agentId: 'u-madhukar',
    startIn: 7,
    durationHours: 6,
    assetTags: ['BLR_SRV12', 'BLR_SRV13'],
  },
  {
    subject: 'Roll Cloudflare WARP 2026.3 to all managed endpoints',
    changeType: 'Normal',
    status: 'Planning',
    priority: 'Medium',
    impact: 'Medium',
    risk: 'Medium',
    category: 'Security',
    department: 'Security & Compliance',
    group: 'Security Operations',
    requesterId: 'u-arjun',
    agentId: 'u-arjun',
    startIn: 12,
    durationHours: 3,
  },
  {
    subject: 'Emergency firewall rule rollback after outbound SMTP block',
    changeType: 'Emergency',
    status: 'Completed',
    priority: 'Urgent',
    impact: 'High',
    risk: 'High',
    category: 'Security',
    department: 'Security & Compliance',
    group: 'Security Operations',
    requesterId: 'u-arjun',
    agentId: 'u-sagar',
    startIn: -4,
    durationHours: 2,
    assetTags: ['BLR_FGT01'],
    emergencyJustification:
      'Outbound SMTP was blocked by a mis-scoped rule, halting all customer notification email. Immediate rollback required.',
  },
  {
    subject: 'Replace failed distribution switch in Hyderabad comms room',
    changeType: 'Emergency',
    status: 'In Progress',
    priority: 'Urgent',
    impact: 'High',
    risk: 'High',
    category: 'Network',
    department: 'Shared Services – IT & Infrastructure',
    group: 'Network Operations',
    requesterId: 'u-madhukar',
    agentId: 'u-madhukar',
    startIn: 0,
    durationHours: 5,
    assetTags: ['HYD_SW03'],
    emergencyJustification:
      'Switch HYD_SW03 has failed its second power supply. Half of the Hyderabad floor is offline.',
  },
  {
    subject: 'Standard laptop refresh – Engineering batch 4',
    changeType: 'Standard',
    status: 'Scheduled',
    priority: 'Low',
    impact: 'Low',
    risk: 'Low',
    category: 'End User Computing',
    department: 'Engineering',
    group: 'Service Desk',
    requesterId: 'u-siddhartha',
    agentId: 'u-sagar',
    startIn: 5,
    durationHours: 8,
    assetTags: ['BLR_LT1050', 'BLR_LT1051'],
  },
  {
    subject: 'Decommission retired ThinkPad fleet and certify disposal',
    changeType: 'Standard',
    status: 'Completed',
    priority: 'Low',
    impact: 'Low',
    risk: 'Low',
    category: 'End User Computing',
    department: 'Shared Services – IT & Infrastructure',
    group: 'Service Desk',
    requesterId: 'u-sagar',
    agentId: 'u-sagar',
    startIn: -18,
    durationHours: 4,
    assetTags: ['BLR_LT0912', 'BLR_LT0901'],
  },
  {
    subject: 'Enable 802.1X on Pune training room access point',
    changeType: 'Normal',
    status: 'Open',
    priority: 'Medium',
    impact: 'Low',
    risk: 'Low',
    category: 'Network',
    department: 'Shared Services – IT & Infrastructure',
    group: 'Network Operations',
    requesterId: 'u-anita',
    agentId: null,
    startIn: 20,
    durationHours: 2,
    assetTags: ['PUN_FAP02'],
  },
  {
    subject: 'Migrate build runners to Standard D8s v5 sizing',
    changeType: 'Normal',
    status: 'Draft',
    priority: 'Medium',
    impact: 'Medium',
    risk: 'Low',
    category: 'Cloud',
    department: 'Engineering',
    group: 'Cloud Platform',
    requesterId: 'u-rahul',
    agentId: null,
    startIn: 25,
    durationHours: 3,
    assetTags: ['CLD_VM021'],
  },
  {
    subject: 'Quarterly access review automation for Finance systems',
    changeType: 'Normal',
    status: 'Rejected',
    priority: 'Medium',
    impact: 'Medium',
    risk: 'High',
    category: 'Application',
    department: 'Finance',
    group: 'Security Operations',
    requesterId: 'u-priya',
    agentId: 'u-arjun',
    startIn: 9,
    durationHours: 4,
  },
  {
    subject: 'Retire legacy VPN concentrator in Dallas',
    changeType: 'Normal',
    status: 'Cancelled',
    priority: 'Low',
    impact: 'Medium',
    risk: 'Medium',
    category: 'Network',
    department: 'Shared Services – IT & Infrastructure',
    group: 'Network Operations',
    requesterId: 'u-naresh',
    agentId: null,
    startIn: -10,
    durationHours: 6,
    assetTags: ['DAL_FGT02'],
  },
  {
    subject: 'Deploy monitor firmware update to UltraSharp fleet',
    changeType: 'Standard',
    status: 'Planning',
    priority: 'Low',
    impact: 'Low',
    risk: 'Low',
    category: 'End User Computing',
    department: 'Engineering',
    group: 'Service Desk',
    requesterId: 'u-rahul',
    agentId: 'u-sagar',
    startIn: 14,
    durationHours: 2,
    assetTags: ['BLR_MON2201', 'BLR_MON2202'],
  },
  {
    subject: 'Rotate FortiGate admin credentials and enforce MFA',
    changeType: 'Normal',
    status: 'Pending Approval',
    priority: 'High',
    impact: 'Medium',
    risk: 'High',
    category: 'Security',
    department: 'Security & Compliance',
    group: 'Security Operations',
    requesterId: 'u-arjun',
    agentId: 'u-arjun',
    startIn: 4,
    durationHours: 2,
    assetTags: ['BLR_FGT01', 'DAL_FGT02'],
  },
  {
    subject: 'Expand Bangalore Wi-Fi coverage to the new mezzanine',
    changeType: 'Normal',
    status: 'In Progress',
    priority: 'Medium',
    impact: 'Low',
    risk: 'Low',
    category: 'Network',
    department: 'Shared Services – IT & Infrastructure',
    group: 'Network Operations',
    requesterId: 'u-sagar',
    agentId: 'u-madhukar',
    startIn: -1,
    durationHours: 10,
    assetTags: ['BLR_FAP10', 'BLR_SW07'],
  },
  {
    subject: 'Onboard Samsung ViewFinity monitors to asset discovery',
    changeType: 'Standard',
    status: 'Completed',
    priority: 'Low',
    impact: 'Low',
    risk: 'Low',
    category: 'End User Computing',
    department: 'Finance',
    group: 'IT Team',
    requesterId: 'u-priya',
    agentId: 'u-sagar',
    startIn: -25,
    durationHours: 3,
    assetTags: ['HYD_MON3110'],
  },
  {
    subject: 'Patch database hosts for CVE-2026-1043',
    changeType: 'Emergency',
    status: 'Scheduled',
    priority: 'Urgent',
    impact: 'High',
    risk: 'High',
    category: 'Database',
    department: 'Engineering',
    group: 'Infrastructure',
    requesterId: 'u-madhukar',
    agentId: 'u-madhukar',
    startIn: 1,
    durationHours: 3,
    assetTags: ['BLR_SRV13'],
    emergencyJustification:
      'Actively exploited remote code execution in the database engine. Vendor advises patching within 48 hours.',
  },
];

const APPROVER_BY_GROUP: Record<string, { id: string; name: string }> = {
  'Network Operations': { id: 'u-madhukar', name: 'Madhukar Rao' },
  Infrastructure: { id: 'u-madhukar', name: 'Madhukar Rao' },
  'Security Operations': { id: 'u-arjun', name: 'Arjun Desai' },
  'Service Desk': { id: 'u-sagar', name: 'Sagar J' },
  'IT Team': { id: 'u-sagar', name: 'Sagar J' },
  'Cloud Platform': { id: 'u-hareesh', name: 'Hareesh Kumar' },
};

/** Terminal-ish statuses that imply the approval gate has already resolved. */
const APPROVED_STATUSES: ChangeStatus[] = ['Scheduled', 'In Progress', 'Completed'];

export function seedChanges(assetIdByTag: Record<string, string>): Change[] {
  return SEEDS.map((seed, i) => {
    const approver = APPROVER_BY_GROUP[seed.group] ?? { id: 'u-sagar', name: 'Sagar J' };
    const decided = APPROVED_STATUSES.includes(seed.status);
    const rejected = seed.status === 'Rejected';
    const started = seed.status === 'In Progress' || seed.status === 'Completed';
    const finished = seed.status === 'Completed';

    return {
      id: `change-${i + 1}`,
      changeId: `CHG-${String(1001 + i)}`,
      sourceTicketId: null,
      sourceTicketNumber: null,
      workspace: 'IT Operations',
      requesterId: seed.requesterId,
      subject: seed.subject,
      changeType: seed.changeType,
      status: seed.status,
      priority: seed.priority,
      impact: seed.impact,
      risk: seed.risk,
      group: seed.group,
      agentId: seed.agentId,
      description: `<p>${seed.subject}. Work is coordinated by the ${seed.group} group within the approved maintenance window.</p>`,
      plannedStart: at(seed.startIn, 22),
      plannedEnd: at(seed.startIn, 22 + Math.min(seed.durationHours, 1)),
      actualStart: started ? at(seed.startIn, 22) : null,
      actualEnd: finished ? at(seed.startIn + 1, 2) : null,
      department: seed.department,
      category: seed.category,
      maintenanceWindow:
        seed.changeType === 'Emergency'
          ? 'Emergency – Immediate'
          : 'Weeknight – 23:00 to 02:00 IST',
      assetIds: (seed.assetTags ?? [])
        .map((tag) => assetIdByTag[tag])
        .filter((id): id is string => Boolean(id)),
      attachments: [],
      planning: planning({
        postImplementationReview: finished
          ? 'Completed inside the window with no rollback. No follow-up actions required.'
          : '',
      }),
      approvals: [
        {
          id: `apr-${i + 1}-1`,
          stage: 1,
          name: `${seed.group} Lead`,
          approverId: approver.id,
          approverName: approver.name,
          decision: rejected ? 'Rejected' : decided ? 'Approved' : 'Pending',
          comments: rejected
            ? 'Scope overlaps an in-flight audit. Resubmit after the audit closes.'
            : decided
              ? 'Approved. Proceed within the stated window.'
              : '',
          decidedAt: decided || rejected ? at(seed.startIn - 2, 11) : null,
        },
        ...(seed.impact === 'High'
          ? [
              {
                id: `apr-${i + 1}-2`,
                stage: 2,
                name: 'Change Advisory Board',
                approverId: 'u-hareesh',
                approverName: 'Hareesh Kumar',
                decision: (decided ? 'Approved' : 'Pending') as 'Approved' | 'Pending',
                comments: decided ? 'CAB reviewed. No objections.' : '',
                decidedAt: decided ? at(seed.startIn - 1, 15) : null,
              },
            ]
          : []),
      ],
      implementationTasks: [
        { id: `t-${i}-1`, label: 'Confirm backups and rollback path', done: started },
        { id: `t-${i}-2`, label: 'Notify affected teams', done: started },
        { id: `t-${i}-3`, label: 'Apply the change', done: finished },
        { id: `t-${i}-4`, label: 'Run validation plan', done: finished },
        { id: `t-${i}-5`, label: 'Confirm monitoring is clean', done: finished },
      ],
      closureNotes: finished
        ? 'All validation steps passed. Monitoring clean for 30 minutes after completion.'
        : '',
      emergencyJustification: seed.emergencyJustification ?? '',
      activity: [
        {
          id: `ca-${i}-1`,
          at: at(seed.startIn - 5, 10),
          actor: 'System',
          action: 'Change created',
        },
        ...(decided
          ? [
              {
                id: `ca-${i}-2`,
                at: at(seed.startIn - 2, 11),
                actor: approver.name,
                action: 'Approved change',
              },
            ]
          : []),
      ],
      createdAt: at(seed.startIn - 5, 10),
      updatedAt: at(Math.min(seed.startIn, 0), 12),
    };
  });
}
