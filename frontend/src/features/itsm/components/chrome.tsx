/** Page chrome: breadcrumbs, page headers, and tab strips. */

import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';

import { cn } from '../lib/cn';

export interface Crumb {
  label: string;
  to?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-1 text-[12px] text-slate-500">
        {items.map((c, i) => (
          <li key={`${c.label}-${i}`} className="flex items-center gap-1">
            {i > 0 && <ChevronRight size={12} aria-hidden="true" className="text-slate-400" />}
            {c.to ? (
              <Link
                to={c.to}
                className="rounded hover:text-sky-700 focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
              >
                {c.label}
              </Link>
            ) : (
              <span className="text-slate-700" aria-current="page">
                {c.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  crumbs,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  crumbs?: Crumb[];
}) {
  return (
    <header className="space-y-2">
      {crumbs && <Breadcrumbs items={crumbs} />}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-semibold tracking-tight text-slate-900">{title}</h1>
          {description && <p className="mt-0.5 text-[12.5px] text-slate-500">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}

interface TabsProps {
  tabs: readonly string[];
  active: string;
  onChange: (tab: string) => void;
  /** Vertical strip for detail pages; horizontal elsewhere. */
  orientation?: 'horizontal' | 'vertical';
}

export function Tabs({ tabs, active, onChange, orientation = 'horizontal' }: TabsProps) {
  const vertical = orientation === 'vertical';
  return (
    <div
      role="tablist"
      aria-orientation={orientation}
      className={cn(
        vertical
          ? 'flex w-44 shrink-0 flex-col gap-0.5'
          : 'flex flex-wrap gap-1 border-b border-slate-200',
      )}
    >
      {tabs.map((tab) => {
        const isActive = tab === active;
        return (
          <button
            key={tab}
            role="tab"
            type="button"
            aria-selected={isActive}
            onClick={() => onChange(tab)}
            className={cn(
              'text-left text-[13px] transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500',
              vertical
                ? cn(
                    'rounded-md px-3 py-1.5',
                    isActive
                      ? 'bg-slate-100 font-medium text-slate-900'
                      : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800',
                  )
                : cn(
                    '-mb-px border-b-2 px-3 py-2',
                    isActive
                      ? 'border-sky-500 font-medium text-slate-900'
                      : 'border-transparent text-slate-500 hover:text-slate-800',
                  ),
            )}
          >
            {tab}
          </button>
        );
      })}
    </div>
  );
}
