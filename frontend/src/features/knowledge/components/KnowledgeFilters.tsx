/** Filter/search bar for the knowledge list page. */

import { Search } from 'lucide-react';

import type { ArticleFilters } from '@/types/knowledge';
import { STATUS_OPTIONS } from '../constants';

interface Props {
  filters: ArticleFilters;
  onChange: (next: ArticleFilters) => void;
}

export function KnowledgeFilters({ filters, onChange }: Props) {
  const set = (patch: Partial<ArticleFilters>) => onChange({ ...filters, ...patch, offset: 0 });

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative flex-1 min-w-[220px]">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          value={filters.search ?? ''}
          onChange={(e) => set({ search: e.target.value })}
          placeholder="Search title, summary, tags…"
          className="w-full rounded-lg border border-border py-2 pl-9 pr-3 text-sm outline-none focus:border-primary"
        />
      </div>

      <select
        value={filters.status ?? ''}
        onChange={(e) => set({ status: e.target.value as ArticleFilters['status'] })}
        className="rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary"
      >
        <option value="">All statuses</option>
        {STATUS_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>

      <input
        value={filters.category ?? ''}
        onChange={(e) => set({ category: e.target.value })}
        placeholder="Category"
        className="w-40 rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary"
      />

      <input
        value={filters.platform ?? ''}
        onChange={(e) => set({ platform: e.target.value })}
        placeholder="Platform"
        className="w-32 rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary"
      />

      <label className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm">
        <input
          type="checkbox"
          checked={filters.review_due ?? false}
          onChange={(e) => set({ review_due: e.target.checked })}
        />
        Review due
      </label>
    </div>
  );
}
