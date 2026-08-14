/**
 * Generic kanban board with drag-and-drop plus a keyboard-accessible fallback.
 *
 * Every drop is validated by the caller's `canDrop` before it is applied, so a
 * board can never bypass the workflow rules the detail pages enforce.
 */

import { useState, type ReactNode } from 'react';

import { cn } from '../lib/cn';
import type { RuleResult } from '../data/rules';

interface BoardProps<T, C extends string> {
  columns: readonly C[];
  items: T[];
  columnOf: (item: T) => string;
  itemKey: (item: T) => string;
  renderCard: (item: T) => ReactNode;
  canDrop: (item: T, column: C) => RuleResult;
  onDrop: (item: T, column: C) => void;
  onRejected: (reason: string) => void;
}

export function Board<T, C extends string>({
  columns,
  items,
  columnOf,
  itemKey,
  renderCard,
  canDrop,
  onDrop,
  onRejected,
}: BoardProps<T, C>) {
  const [dragging, setDragging] = useState<string | null>(null);
  const [hovered, setHovered] = useState<C | null>(null);

  function attempt(item: T, column: C) {
    const verdict = canDrop(item, column);
    if (!verdict.ok) {
      onRejected(verdict.reason ?? 'That move is not allowed.');
      return;
    }
    onDrop(item, column);
  }

  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {columns.map((col) => {
        const colItems = items.filter((i) => columnOf(i) === col);
        return (
          <section
            key={col}
            onDragOver={(e) => {
              e.preventDefault();
              setHovered(col);
            }}
            onDragLeave={() => setHovered((h) => (h === col ? null : h))}
            onDrop={(e) => {
              e.preventDefault();
              setHovered(null);
              const id = e.dataTransfer.getData('text/plain');
              const item = items.find((i) => itemKey(i) === id);
              if (item) attempt(item, col);
            }}
            className={cn(
              'flex w-64 shrink-0 flex-col rounded-lg border bg-white transition-colors',
              hovered === col ? 'border-sky-600 bg-sky-50' : 'border-slate-200',
            )}
          >
            <header className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
              <h2 className="text-[12.5px] font-semibold text-slate-800">{col}</h2>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">
                {colItems.length}
              </span>
            </header>

            <ul className="flex-1 space-y-2 p-2">
              {colItems.map((item) => {
                const id = itemKey(item);
                return (
                  <li
                    key={id}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData('text/plain', id);
                      setDragging(id);
                    }}
                    onDragEnd={() => setDragging(null)}
                    className={cn(
                      'rounded-md border border-slate-300 bg-white p-2.5 transition-opacity',
                      dragging === id && 'opacity-40',
                    )}
                  >
                    {renderCard(item)}

                    {/* Keyboard path — drag-and-drop alone is not accessible. */}
                    <label className="mt-2 block">
                      <span className="sr-only">Move to another column</span>
                      <select
                        value=""
                        onChange={(e) => {
                          const target = e.target.value as C;
                          if (target) attempt(item, target);
                          e.target.value = '';
                        }}
                        className="w-full rounded border border-slate-300 bg-white px-1.5 py-1 text-[11px] text-slate-500 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                      >
                        <option value="">Move to…</option>
                        {columns
                          .filter((c) => c !== col)
                          .map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                      </select>
                    </label>
                  </li>
                );
              })}
              {colItems.length === 0 && (
                <li className="rounded border border-dashed border-slate-200 px-2 py-6 text-center text-[11.5px] text-slate-400">
                  Nothing here
                </li>
              )}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
