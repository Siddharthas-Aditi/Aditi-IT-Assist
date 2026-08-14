/** Sortable, selectable, paginated table shared by the Change and Asset lists. */

import { useMemo, useState, type ReactNode } from 'react';
import { ChevronDown, ChevronUp, ChevronsUpDown } from 'lucide-react';

import { cn } from '../lib/cn';
import { Button, EmptyState } from './ui';

export interface Column<T> {
  key: string;
  header: string;
  /** Value used for sorting and CSV export. */
  value: (row: T) => string | number;
  /** Optional rich cell; falls back to `value`. */
  render?: (row: T) => ReactNode;
  width?: string;
  align?: 'left' | 'right';
}

interface DataTableProps<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  selectable?: boolean;
  selected?: Set<string>;
  onSelectedChange?: (next: Set<string>) => void;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
  pageSize?: number;
  initialSortKey?: string;
}

type SortDir = 'asc' | 'desc';

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  onRowClick,
  selectable = false,
  selected,
  onSelectedChange,
  emptyTitle = 'Nothing to show',
  emptyDescription,
  emptyAction,
  pageSize = 15,
  initialSortKey,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(initialSortKey ?? null);
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [page, setPage] = useState(0);

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    const col = columns.find((c) => c.key === sortKey);
    if (!col) return rows;
    return [...rows].sort((a, b) => {
      const av = col.value(a);
      const bv = col.value(b);
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av;
      }
      const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true });
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [rows, columns, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const visible = sorted.slice(safePage * pageSize, safePage * pageSize + pageSize);

  function toggleSort(key: string) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
    setPage(0);
  }

  const allVisibleSelected =
    selectable && visible.length > 0 && visible.every((r) => selected?.has(rowKey(r)));

  function toggleAll() {
    if (!onSelectedChange) return;
    const next = new Set(selected ?? []);
    if (allVisibleSelected) {
      visible.forEach((r) => next.delete(rowKey(r)));
    } else {
      visible.forEach((r) => next.add(rowKey(r)));
    }
    onSelectedChange(next);
  }

  function toggleOne(id: string) {
    if (!onSelectedChange) return;
    const next = new Set(selected ?? []);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectedChange(next);
  }

  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white">
        <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-slate-200 bg-white">
              {selectable && (
                <th scope="col" className="w-10 px-3 py-2">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={toggleAll}
                    aria-label="Select all rows on this page"
                    className="h-3.5 w-3.5 rounded border-slate-300 bg-slate-100 text-sky-500 focus:ring-1 focus:ring-sky-500"
                  />
                </th>
              )}
              {columns.map((col) => {
                const active = sortKey === col.key;
                return (
                  <th
                    key={col.key}
                    scope="col"
                    style={col.width ? { width: col.width } : undefined}
                    className={cn(
                      'whitespace-nowrap px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500',
                      col.align === 'right' && 'text-right',
                    )}
                    aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  >
                    <button
                      type="button"
                      onClick={() => toggleSort(col.key)}
                      className="inline-flex items-center gap-1 rounded transition-colors hover:text-slate-800 focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
                    >
                      {col.header}
                      {active ? (
                        sortDir === 'asc' ? (
                          <ChevronUp size={12} />
                        ) : (
                          <ChevronDown size={12} />
                        )
                      ) : (
                        <ChevronsUpDown size={12} className="opacity-40" />
                      )}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => {
              const id = rowKey(row);
              return (
                <tr
                  key={id}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={cn(
                    'border-b border-slate-200 last:border-0',
                    onRowClick && 'cursor-pointer hover:bg-slate-50',
                    selected?.has(id) && 'bg-sky-50',
                  )}
                >
                  {selectable && (
                    <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected?.has(id) ?? false}
                        onChange={() => toggleOne(id)}
                        aria-label={`Select row ${id}`}
                        className="h-3.5 w-3.5 rounded border-slate-300 bg-slate-100 text-sky-500 focus:ring-1 focus:ring-sky-500"
                      />
                    </td>
                  )}
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        'whitespace-nowrap px-3 py-2 text-[12.5px] text-slate-700',
                        col.align === 'right' && 'text-right',
                      )}
                    >
                      {col.render ? col.render(row) : col.value(row)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 px-3 py-2 text-[12px] text-slate-500">
        <span>
          Showing {safePage * pageSize + 1}–{Math.min((safePage + 1) * pageSize, sorted.length)} of{' '}
          {sorted.length}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={safePage === 0}
          >
            Previous
          </Button>
          <span aria-live="polite">
            Page {safePage + 1} of {pageCount}
          </span>
          <Button
            variant="ghost"
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={safePage >= pageCount - 1}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
