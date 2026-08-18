/**
 * Currency formatting for asset cost.
 *
 * Assets are bought in the currency of the region that bought them, so cost is
 * stored with its own currency code rather than converted. Totals are reported
 * **per currency** — this module deliberately provides no FX conversion,
 * because inventing a rate would silently misstate the numbers.
 */

import type { CurrencyCode } from './types';

const FORMATTERS: Record<CurrencyCode, Intl.NumberFormat> = {
  INR: new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }),
  USD: new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }),
};

export const CURRENCY_SYMBOLS: Record<CurrencyCode, string> = {
  INR: '₹',
  USD: '$',
};

export function formatMoney(amount: number, currency: CurrencyCode = 'INR'): string {
  return (FORMATTERS[currency] ?? FORMATTERS.INR).format(amount || 0);
}

/** Sum a set of costs, grouped by currency (never summed across them). */
export function totalsByCurrency(
  rows: { cost: number; currency: CurrencyCode }[],
): { currency: CurrencyCode; total: number }[] {
  const map = new Map<CurrencyCode, number>();
  rows.forEach((r) => {
    const cur = r.currency ?? 'INR';
    map.set(cur, (map.get(cur) ?? 0) + (r.cost || 0));
  });
  return [...map.entries()]
    .map(([currency, total]) => ({ currency, total }))
    .sort((a, b) => b.total - a.total);
}

/** Render grouped totals as "₹12,34,000 + $4,500". */
export function formatTotals(rows: { cost: number; currency: CurrencyCode }[]): string {
  const totals = totalsByCurrency(rows);
  if (totals.length === 0) return formatMoney(0, 'INR');
  return totals.map((t) => formatMoney(t.total, t.currency)).join(' + ');
}
