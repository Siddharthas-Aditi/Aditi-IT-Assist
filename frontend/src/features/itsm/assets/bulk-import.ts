/**
 * Bulk asset import from a delimited file.
 *
 * Parsing is done here (pure, no DOM) so the rules are unit-testable and the
 * page only renders the result. Rows are validated individually: a bad row is
 * reported and skipped rather than failing the whole file, because a 200-row
 * spreadsheet with two typos should still import 198 assets.
 */

import { ASSET_STATES, CURRENCIES, IMPACTS, USAGE_TYPES } from '../data/types';
import type { Asset, AssetState, CurrencyCode, Impact, UsageType } from '../data/types';
import { emptyAssetDraft } from './form-model';

/** Column header → the asset field it fills. Matching is case/space-insensitive. */
export const IMPORT_COLUMNS: { header: string; required?: boolean; note: string }[] = [
  { header: 'Asset Tag', required: true, note: 'Unique. Rows with a duplicate tag are rejected.' },
  { header: 'Asset Name', required: true, note: 'Free text.' },
  { header: 'Asset Type', required: true, note: 'e.g. Laptop, Access Point, Monitor.' },
  { header: 'Serial Number', note: 'Duplicates are allowed but flagged later.' },
  { header: 'Model', note: 'Free text.' },
  { header: 'Product', note: 'Free text.' },
  { header: 'Vendor', note: 'Free text.' },
  { header: 'Asset State', note: `One of: ${ASSET_STATES.join(', ')}. Defaults to In Stock.` },
  { header: 'Cost', note: 'Number only, no symbols or separators.' },
  { header: 'Currency', note: `INR or USD. Defaults to INR.` },
  { header: 'Location', note: 'Matched against your locations list.' },
  { header: 'Department', note: 'Free text.' },
  { header: 'Usage Type', note: `One of: ${USAGE_TYPES.join(', ')}.` },
  { header: 'Impact', note: `One of: ${IMPACTS.join(', ')}.` },
  { header: 'Employee ID', note: 'Free text.' },
  { header: 'Warranty Expiry', note: 'YYYY-MM-DD.' },
  { header: 'End of Life', note: 'YYYY-MM-DD.' },
  { header: 'IP Address', note: 'Network gear only.' },
  { header: 'MAC Address', note: 'Network gear only.' },
];

export interface ImportIssue {
  row: number;
  message: string;
}

export interface ImportResult {
  /** Rows that passed validation, ready to hand to the store. */
  valid: Omit<Asset, 'id' | 'createdAt' | 'updatedAt'>[];
  errors: ImportIssue[];
  warnings: ImportIssue[];
  totalRows: number;
}

/**
 * Split delimited text into rows of cells.
 *
 * Handles quoted fields containing the delimiter, escaped `""` quotes, and
 * CRLF — the three things that break a naive `split(',')` on real exports.
 */
export function parseDelimited(text: string, delimiter = ','): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];

    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        cell += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
    } else if (ch === delimiter) {
      row.push(cell);
      cell = '';
    } else if (ch === '\n') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
    } else if (ch !== '\r') {
      cell += ch;
    }
  }

  // Trailing cell / row (files often lack a final newline).
  if (cell.length > 0 || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }

  return rows.filter((r) => r.some((c) => c.trim() !== ''));
}

/** Tab-separated files are what "copy from Excel" actually produces. */
export function detectDelimiter(text: string): string {
  const firstLine = text.split('\n')[0] ?? '';
  const tabs = (firstLine.match(/\t/g) ?? []).length;
  const commas = (firstLine.match(/,/g) ?? []).length;
  const semis = (firstLine.match(/;/g) ?? []).length;
  if (tabs > commas && tabs > semis) return '\t';
  if (semis > commas) return ';';
  return ',';
}

function normalise(header: string): string {
  return header.trim().toLowerCase().replace(/[\s_-]+/g, '');
}

function pick<T extends string>(
  raw: string,
  allowed: readonly T[],
  fallback: T,
): { value: T; ok: boolean } {
  const needle = raw.trim().toLowerCase();
  if (!needle) return { value: fallback, ok: true };
  const hit = allowed.find((a) => a.toLowerCase() === needle);
  return hit ? { value: hit, ok: true } : { value: fallback, ok: false };
}

function isoDate(raw: string): string | null {
  const v = raw.trim();
  if (!v) return null;
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString().slice(0, 10);
}

/**
 * Turn parsed rows into asset drafts.
 *
 * `existingTags` seeds duplicate detection so tags that clash *within the file*
 * are caught too, not just clashes against what is already stored.
 */
export function buildImport(
  rows: string[][],
  existingAssetTags: Iterable<string> = [],
): ImportResult {
  const errors: ImportIssue[] = [];
  const warnings: ImportIssue[] = [];
  const valid: Omit<Asset, 'id' | 'createdAt' | 'updatedAt'>[] = [];

  if (rows.length === 0) {
    return { valid, errors: [{ row: 0, message: 'The file is empty.' }], warnings, totalRows: 0 };
  }

  const headers = rows[0].map(normalise);
  const body = rows.slice(1);

  const col = (name: string) => headers.indexOf(normalise(name));
  const idx = {
    assetTag: col('Asset Tag'),
    name: col('Asset Name'),
    assetType: col('Asset Type'),
    serialNumber: col('Serial Number'),
    model: col('Model'),
    product: col('Product'),
    vendor: col('Vendor'),
    assetState: col('Asset State'),
    cost: col('Cost'),
    currency: col('Currency'),
    location: col('Location'),
    department: col('Department'),
    usageType: col('Usage Type'),
    impact: col('Impact'),
    employeeId: col('Employee ID'),
    warrantyExpiry: col('Warranty Expiry'),
    endOfLife: col('End of Life'),
    ipAddress: col('IP Address'),
    macAddress: col('MAC Address'),
  };

  const missing = (['assetTag', 'name', 'assetType'] as const).filter((k) => idx[k] === -1);
  if (missing.length) {
    return {
      valid,
      errors: [
        {
          row: 1,
          message: `Missing required column(s): ${missing
            .map((m) => IMPORT_COLUMNS.find((c) => normalise(c.header) === normalise(m))?.header ?? m)
            .join(', ')}. Download the template for the expected headers.`,
        },
      ],
      warnings,
      totalRows: body.length,
    };
  }

  const seenInFile = new Set<string>();
  const existingTags = new Set([...existingAssetTags].map((tag) => tag.toLowerCase()));

  body.forEach((cells, i) => {
    // +2: one for the header row, one because humans count from 1.
    const rowNo = i + 2;
    const get = (at: number) => (at >= 0 ? (cells[at] ?? '').trim() : '');

    const assetTag = get(idx.assetTag);
    const name = get(idx.name);
    const assetType = get(idx.assetType);

    if (!assetTag) {
      errors.push({ row: rowNo, message: 'Asset Tag is required.' });
      return;
    }
    if (!name) {
      errors.push({ row: rowNo, message: `“${assetTag}” has no Asset Name.` });
      return;
    }
    if (!assetType) {
      errors.push({ row: rowNo, message: `“${assetTag}” has no Asset Type.` });
      return;
    }

    const key = assetTag.toLowerCase();
    if (seenInFile.has(key)) {
      errors.push({ row: rowNo, message: `“${assetTag}” appears more than once in this file.` });
      return;
    }
    if (existingTags.has(key)) {
      errors.push({ row: rowNo, message: `“${assetTag}” already exists in the inventory.` });
      return;
    }
    seenInFile.add(key);

    const rawCost = get(idx.cost).replace(/[,\s]/g, '');
    const cost = rawCost ? Number(rawCost) : 0;
    if (rawCost && !Number.isFinite(cost)) {
      warnings.push({ row: rowNo, message: `“${assetTag}”: cost “${get(idx.cost)}” is not a number — set to 0.` });
    }

    const state = pick<AssetState>(get(idx.assetState), ASSET_STATES, 'In Stock');
    if (!state.ok) {
      warnings.push({
        row: rowNo,
        message: `“${assetTag}”: unknown Asset State “${get(idx.assetState)}” — set to In Stock.`,
      });
    }

    const currency = pick<CurrencyCode>(get(idx.currency), CURRENCIES, 'INR');
    if (!currency.ok) {
      warnings.push({
        row: rowNo,
        message: `“${assetTag}”: unknown Currency “${get(idx.currency)}” — set to INR.`,
      });
    }

    const usage = pick<UsageType>(get(idx.usageType), USAGE_TYPES, 'Permanent');
    const impact = pick<Impact>(get(idx.impact), IMPACTS, 'Low');

    const draft = emptyAssetDraft();
    valid.push({
      ...draft,
      assetTag,
      name,
      assetType,
      serialNumber: get(idx.serialNumber),
      model: get(idx.model),
      product: get(idx.product),
      vendor: get(idx.vendor),
      assetState: state.value,
      cost: Number.isFinite(cost) ? cost : 0,
      currency: currency.value,
      location: get(idx.location),
      department: get(idx.department),
      usageType: usage.value,
      impact: impact.value,
      employeeId: get(idx.employeeId),
      warrantyExpiry: isoDate(get(idx.warrantyExpiry)),
      endOfLife: isoDate(get(idx.endOfLife)),
      ipAddress: get(idx.ipAddress),
      macAddress: get(idx.macAddress),
      createdBySource: 'CSV Import',
      source: 'CSV Import',
      relationships: [],
      activity: [
        {
          id: `act-import-${rowNo}`,
          at: new Date().toISOString(),
          actor: 'Bulk import',
          action: 'Asset imported from file',
        },
      ],
    });
  });

  return { valid, errors, warnings, totalRows: body.length };
}

/** CSV text for the downloadable template. */
export function templateCsv(): string {
  const headers = IMPORT_COLUMNS.map((c) => c.header);
  const example = [
    'BLR_LT9001',
    'ThinkPad T14 – New Hire',
    'Laptop',
    'PF9XY1ZZ',
    'ThinkPad T14 Gen 4',
    'ThinkPad T14',
    'Lenovo India',
    'In Stock',
    '132000',
    'INR',
    'India - Bangalore',
    'Engineering',
    'Permanent',
    'Low',
    'ADT-9001',
    '2028-03-31',
    '2030-03-31',
    '',
    '',
  ];
  return `${headers.join(',')}\n${example.join(',')}\n`;
}
