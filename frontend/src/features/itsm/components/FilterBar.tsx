/** Search + dropdown filter strip with saved views, shared by both list pages. */

import { useState } from 'react';
import { Bookmark, Search, X } from 'lucide-react';

import { cn } from '../lib/cn';
import { Button } from './ui';

export interface FilterSpec {
  key: string;
  label: string;
  options: readonly string[];
  /** Renders as a date input instead of a select. */
  type?: 'select' | 'date';
}

export type FilterValues = Record<string, string>;

export interface SavedView {
  name: string;
  search: string;
  filters: FilterValues;
}

interface FilterBarProps {
  searchPlaceholder: string;
  search: string;
  onSearchChange: (v: string) => void;
  specs: FilterSpec[];
  values: FilterValues;
  onChange: (next: FilterValues) => void;
  savedViews: SavedView[];
  onSaveView: (name: string) => void;
  onApplyView: (view: SavedView) => void;
  onDeleteView: (name: string) => void;
}

export function FilterBar({
  searchPlaceholder,
  search,
  onSearchChange,
  specs,
  values,
  onChange,
  savedViews,
  onSaveView,
  onApplyView,
  onDeleteView,
}: FilterBarProps) {
  const [savingName, setSavingName] = useState('');
  const [showSave, setShowSave] = useState(false);

  const activeCount = Object.values(values).filter(Boolean).length;

  function set(key: string, value: string) {
    onChange({ ...values, [key]: value });
  }

  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[240px] flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500"
            aria-hidden="true"
          />
          <input
            type="search"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            className="w-full rounded-md border border-slate-300 bg-white py-1.5 pl-8 pr-3 text-[13px] text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          />
        </div>

        <Button
          variant="ghost"
          onClick={() => setShowSave((s) => !s)}
          aria-expanded={showSave}
          title="Saved views"
        >
          <Bookmark size={14} /> Views{savedViews.length ? ` (${savedViews.length})` : ''}
        </Button>

        {activeCount > 0 && (
          <Button variant="ghost" onClick={() => onChange({})}>
            <X size={14} /> Clear {activeCount} filter{activeCount > 1 ? 's' : ''}
          </Button>
        )}
      </div>

      {showSave && (
        <div className="rounded-md border border-slate-200 bg-white p-3">
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={savingName}
              onChange={(e) => setSavingName(e.target.value)}
              placeholder="Name this view…"
              aria-label="Saved view name"
              className="w-56 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-[13px] text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
            <Button
              variant="primary"
              disabled={!savingName.trim()}
              onClick={() => {
                onSaveView(savingName.trim());
                setSavingName('');
              }}
            >
              Save current view
            </Button>
          </div>
          {savedViews.length > 0 && (
            <ul className="mt-2.5 flex flex-wrap gap-1.5">
              {savedViews.map((v) => (
                <li key={v.name}>
                  <span className="inline-flex items-center gap-1 rounded border border-slate-300 bg-slate-100 py-0.5 pl-2 pr-1 text-[12px] text-slate-800">
                    <button
                      type="button"
                      onClick={() => onApplyView(v)}
                      className="hover:text-sky-700 focus:outline-none focus-visible:underline"
                    >
                      {v.name}
                    </button>
                    <button
                      type="button"
                      onClick={() => onDeleteView(v.name)}
                      aria-label={`Delete view ${v.name}`}
                      className="rounded p-0.5 text-slate-500 hover:text-red-600 focus:outline-none focus-visible:ring-1 focus-visible:ring-red-400"
                    >
                      <X size={11} />
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {specs.map((spec) => (
          <label key={spec.key} className="flex flex-col gap-0.5">
            <span className="text-[10.5px] uppercase tracking-wide text-slate-500">
              {spec.label}
            </span>
            {spec.type === 'date' ? (
              <input
                type="date"
                value={values[spec.key] ?? ''}
                onChange={(e) => set(spec.key, e.target.value)}
                className={cn(
                  'rounded-md border bg-white px-2 py-1 text-[12px] text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500',
                  values[spec.key] ? 'border-sky-400' : 'border-slate-300',
                )}
              />
            ) : (
              <select
                value={values[spec.key] ?? ''}
                onChange={(e) => set(spec.key, e.target.value)}
                className={cn(
                  'min-w-[130px] rounded-md border bg-white px-2 py-1 text-[12px] text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500',
                  values[spec.key] ? 'border-sky-400' : 'border-slate-300',
                )}
              >
                <option value="">All</option>
                {spec.options.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            )}
          </label>
        ))}
      </div>
    </div>
  );
}
