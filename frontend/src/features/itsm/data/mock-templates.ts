/** The three seeded change templates surfaced in the "recently used" list. */

import type { ChangePlanning, ChangeTemplate } from './types';

function planning(over: Partial<ChangePlanning>): ChangePlanning {
  return {
    reasonForChange: '',
    impactAnalysis: '',
    rolloutPlan: '',
    backupPlan: '',
    validationPlan: '',
    communicationPlan: '',
    implementationSteps: '',
    rollbackTrigger: '',
    postImplementationReview: '',
    ...over,
  };
}

export function seedTemplates(): ChangeTemplate[] {
  return [
    {
      id: 'tpl-patch-day-stage',
      name: 'Routine Server Patch Updates – Day & Stage',
      changeType: 'Standard',
      defaultPriority: 'Medium',
      defaultImpact: 'Low',
      defaultRisk: 'Low',
      defaultCategory: 'Server',
      defaultDepartment: 'Shared Services – IT & Infrastructure',
      defaultMaintenanceWindow: 'Weeknight – 23:00 to 02:00 IST',
      requiredApprovals: ['Infrastructure Lead'],
      planning: planning({
        reasonForChange:
          'Monthly OS and security patch baseline for day and staging tier servers.',
        impactAnalysis:
          'Staging workloads only. No customer-facing impact expected. Build pipelines pause for the window.',
        rolloutPlan:
          '1. Snapshot each host.\n2. Apply patch baseline in batches of five.\n3. Reboot and verify services.',
        backupPlan: 'Pre-patch VM snapshots retained for 72 hours.',
        validationPlan:
          'Smoke test staging endpoints, confirm agent check-in, verify no failed services.',
        communicationPlan:
          'Notify Engineering channel 24 hours before and on completion.',
        implementationSteps:
          'Snapshot hosts\nApply patches\nReboot\nVerify services\nRelease pipeline hold',
        rollbackTrigger:
          'Any host failing to return to service within 20 minutes of reboot.',
        postImplementationReview: '',
      }),
      archived: false,
      lastUsedAt: new Date(Date.now() - 3 * 86400000).toISOString(),
      createdAt: new Date(Date.now() - 200 * 86400000).toISOString(),
    },
    {
      id: 'tpl-patch-production',
      name: 'Routine Server Patch Updates – Production',
      changeType: 'Normal',
      defaultPriority: 'High',
      defaultImpact: 'High',
      defaultRisk: 'Medium',
      defaultCategory: 'Server',
      defaultDepartment: 'Shared Services – IT & Infrastructure',
      defaultMaintenanceWindow: 'Weekend – Sat 22:00 to Sun 04:00 IST',
      requiredApprovals: ['Infrastructure Lead', 'Change Advisory Board'],
      planning: planning({
        reasonForChange:
          'Monthly security patch baseline for production compute to close known CVEs.',
        impactAnalysis:
          'Production workloads restart in a rolling fashion. Brief connection resets possible per node.',
        rolloutPlan:
          'Rolling patch, one availability zone at a time, health check between zones.',
        backupPlan:
          'Full VM snapshots plus verified database backup taken before the window opens.',
        validationPlan:
          'Synthetic transactions against each service, error-rate dashboard held below baseline for 30 minutes.',
        communicationPlan:
          'Change notice to all staff 72 hours prior. Status page updated at start and completion.',
        implementationSteps:
          'Confirm backups\nDrain zone A\nPatch and reboot zone A\nHealth check\nRepeat for zone B\nRelease traffic',
        rollbackTrigger:
          'Error rate above 2% for five consecutive minutes, or any zone failing health check twice.',
        postImplementationReview: '',
      }),
      archived: false,
      lastUsedAt: new Date(Date.now() - 9 * 86400000).toISOString(),
      createdAt: new Date(Date.now() - 240 * 86400000).toISOString(),
    },
    {
      id: 'tpl-cloudflare-warp',
      name: 'Update Cloudflare WARP – Organization Wide',
      changeType: 'Normal',
      defaultPriority: 'Medium',
      defaultImpact: 'Medium',
      defaultRisk: 'Medium',
      defaultCategory: 'Security',
      defaultDepartment: 'Security & Compliance',
      defaultMaintenanceWindow: 'Weeknight – 23:00 to 02:00 IST',
      requiredApprovals: ['Security Lead'],
      planning: planning({
        reasonForChange:
          'Roll the Cloudflare WARP client to the current release across all managed endpoints.',
        impactAnalysis:
          'All remote users reconnect once. Split-tunnel policy unchanged. Brief VPN drop per device.',
        rolloutPlan:
          'Pilot ring (IT, 20 devices) → Engineering ring → organization wide over three nights.',
        backupPlan: 'Previous client version pinned in Intune for one-click rollback.',
        validationPlan:
          'Confirm tunnel health, DNS resolution, and access to internal apps for each ring before advancing.',
        communicationPlan:
          'Email plus Teams notice per ring, with a reconnect instruction card.',
        implementationSteps:
          'Stage package in Intune\nDeploy pilot ring\nValidate\nDeploy engineering ring\nValidate\nDeploy org wide',
        rollbackTrigger:
          'More than 5% of a ring failing to establish a tunnel within 15 minutes.',
        postImplementationReview: '',
      }),
      archived: false,
      lastUsedAt: new Date(Date.now() - 16 * 86400000).toISOString(),
      createdAt: new Date(Date.now() - 150 * 86400000).toISOString(),
    },
  ];
}
