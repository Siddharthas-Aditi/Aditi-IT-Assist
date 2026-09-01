import { useState } from 'react';

import type { FilterValues, SavedView } from './FilterBar';

/** Saved list views stay in memory until a server-owned contract exists. */
export function useSavedViews(_storageKey: string) {
  const [views, setViews] = useState<SavedView[]>([]);

  function commit(next: SavedView[]) {
    setViews(next);
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
