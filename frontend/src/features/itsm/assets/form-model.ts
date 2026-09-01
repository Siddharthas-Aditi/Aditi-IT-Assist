/** Draft shape and validation for the asset form. */

import { requiresAssignee, requiresRetirementReason } from '../data/rules';
import type { Asset } from '../data/types';

export type AssetDraft = Omit<Asset, 'id' | 'createdAt' | 'updatedAt' | 'activity' | 'relationships'>;

export function emptyAssetDraft(): AssetDraft {
  return {
    assetTag: '',
    name: '',
    assetType: '',
    impact: 'Low',
    description: '',
    endOfLife: null,
    discoveryEnabled: false,
    createdBySource: 'Manual',
    source: 'Manual',

    hardwareType: 'Physical',
    physicalSubtype: '',
    virtualSubtype: 'Not Applicable',
    product: '',
    model: '',
    vendor: '',
    assetState: 'In Stock',
    employeeId: '',
    cost: 0,
    currency: 'INR',
    warranty: '3 years',
    acquisitionDate: null,
    warrantyExpiry: null,
    serialNumber: '',
    invoiceNumber: '',
    poNumber: '',
    classification: 'Internal',

    firmware: '',
    firmwareVersion: '',
    ipAddress: '',
    ports: '',
    macAddress: '',
    subnetMask: '',

    workspace: 'IT Operations',
    location: '',
    department: '',
    usageType: 'Permanent',
    managedByGroup: '',
    managedBy: '',
    assignedTo: '',
    assignedDate: null,

    retirementReason: '',
    retirementDate: null,

    parentAssetId: null,
    contract: 'No Contract',
    conditionPhotos: [],
    attachments: [],
  };
}

export function draftFromAsset(asset: Asset): AssetDraft {
  const { id: _id, createdAt: _c, updatedAt: _u, activity: _a, relationships: _r, ...rest } = asset;
  return { ...rest };
}

export type AssetErrors = Partial<Record<keyof AssetDraft, string>>;

/** Blocking validation. Serial duplicates warn separately and never block. */
export function validateAsset(
  draft: AssetDraft,
  existingAssetTags: Iterable<string> = [],
  exceptTag?: string,
): AssetErrors {
  const errors: AssetErrors = {};

  if (!draft.name.trim()) errors.name = 'Asset name is required.';
  if (!draft.assetType) errors.assetType = 'Asset type is required.';

  if (!draft.assetTag.trim()) {
    errors.assetTag = 'Asset tag is required.';
  } else if (
    [...existingAssetTags].some(
      (tag) =>
        tag.toLowerCase() === draft.assetTag.trim().toLowerCase() &&
        tag.toLowerCase() !== exceptTag?.toLowerCase(),
    )
  ) {
    errors.assetTag = 'This asset tag is already in use.';
  }

  if (draft.cost < 0) errors.cost = 'Cost cannot be negative.';

  if (requiresAssignee(draft.assetState)) {
    if (!draft.assignedTo) {
      errors.assignedTo = `"Assigned To" is required when the state is ${draft.assetState}.`;
    }
    if (!draft.assignedDate) {
      errors.assignedDate = `"Assigned Date" is required when the state is ${draft.assetState}.`;
    }
  }

  if (requiresRetirementReason(draft.assetState)) {
    if (!draft.retirementReason.trim()) {
      errors.retirementReason = `A reason is required to mark an asset ${draft.assetState}.`;
    }
    if (!draft.retirementDate) {
      errors.retirementDate = `A date is required to mark an asset ${draft.assetState}.`;
    }
  }

  return errors;
}
