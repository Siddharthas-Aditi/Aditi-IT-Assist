import { useState } from 'react';

import type { FilterValues, SavedView } from './FilterBar';

/**
 * Saved list views, kept per-list in sessionStorage.
 *
 * Session-scoped on purpose: these are throwaway working sets, and the module
 * has no backend to own them.
 */
export function useSavedViews(storageKey: string) {
  const [views, setViews] = useState<SavedView[]>(() => {
    try {
      const raw = window.sessionStorage.getItem(storageKey);
      return raw ? (JSON.parse(raw) as SavedView[]) : [];
    } catch {
      return [];
    }
  });

  function commit(next: SavedView[]) {
    setViews(next);
    try {
      window.sessionStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      // Non-fatal — views simply won't survive a reload.
    }
  }

  return {
    views,
    save(name: string, search: string, filters: FilterValues) {
      commit([...views.filter((v) => v.name !== name), { name, search, filters }]);
    },
    remove(name: string) {
      commit(views.filter((v) => v.name !== name));
    },
  };
}
