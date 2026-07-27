/** Admin page — manage ticket category hierarchy + cascading preview. */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';

import { PageHeader } from '@/components/admin';
import { CategoryTreeEditor } from '@/features/tickets/CategoryTreeEditor';
import {
  filterActiveTree,
  findByName,
} from '@/features/tickets/categoryTreeUtils';
import { ticketCategoriesApi, type TicketCategoryNode } from '@/lib/api';

const SELECT_CLASS =
  'w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground';

function CascadePreview({ roots }: { roots: TicketCategoryNode[] }) {
  const [category, setCategory] = useState('');
  const [subcategory, setSubcategory] = useState('');
  const [item, setItem] = useState('');

  const l1Node = useMemo(() => findByName(roots, category), [roots, category]);
  const l2Options = useMemo(() => l1Node?.children ?? [], [l1Node]);
  const l2Node = useMemo(() => findByName(l2Options, subcategory), [l2Options, subcategory]);
  const l3Options = useMemo(() => l2Node?.children ?? [], [l2Node]);

  return (
    <div className="space-y-3">
      <div>
        <label htmlFor="preview-category" className="mb-1 block text-xs font-medium text-muted-foreground">
          Category
        </label>
        <select
          id="preview-category"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setSubcategory('');
            setItem('');
          }}
          className={SELECT_CLASS}
        >
          <option value="">Select…</option>
          {roots.map((n) => (
            <option key={n.id} value={n.name}>
              {n.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="preview-subcategory" className="mb-1 block text-xs font-medium text-muted-foreground">
          Sub-Category
        </label>
        <select
          id="preview-subcategory"
          value={subcategory}
          disabled={!category}
          onChange={(e) => {
            setSubcategory(e.target.value);
            setItem('');
          }}
          className={SELECT_CLASS}
        >
          <option value="">Select…</option>
          {l2Options.map((n) => (
            <option key={n.id} value={n.name}>
              {n.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="preview-item" className="mb-1 block text-xs font-medium text-muted-foreground">
          Item
        </label>
        <select
          id="preview-item"
          value={item}
          disabled={!subcategory || l3Options.length === 0}
          onChange={(e) => setItem(e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="">Select…</option>
          {l3Options.map((n) => (
            <option key={n.id} value={n.name}>
              {n.name}
            </option>
          ))}
        </select>
        {subcategory && l3Options.length === 0 && (
          <p className="mt-1 text-xs text-amber-700">
            No active items under this sub-category — agents cannot close tickets here until items exist.
          </p>
        )}
      </div>
    </div>
  );
}

export function TicketCategoriesPage() {
  const [tree, setTree] = useState<TicketCategoryNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadTree = useCallback(async () => {
    const { categories } = await ticketCategoriesApi.tree();
    setTree(categories);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    loadTree()
      .catch((e: unknown) => {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : 'Failed to load categories');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadTree]);

  const refresh = async () => {
    setRefreshing(true);
    setLoadError(null);
    try {
      await loadTree();
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : 'Failed to refresh');
    } finally {
      setRefreshing(false);
    }
  };

  const activePreviewRoots = useMemo(() => filterActiveTree(tree), [tree]);

  return (
    <>
      <PageHeader
        title="Manage Category"
        description="Configure the cascading Category → Sub-Category → Item options used when IT closes tickets"
        breadcrumbs={[{ label: 'Ticket Categories' }]}
        actions={
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading || refreshing}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> Refresh
          </button>
        }
      />

      <div className="p-6">
        {loadError && (
          <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            {loadError}
          </p>
        )}
        {actionError && (
          <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            {actionError}
          </p>
        )}

        {loading ? (
          <div className="py-16 text-center text-muted-foreground">Loading category tree…</div>
        ) : (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_320px]">
            <section className="rounded-xl border border-border bg-card p-4">
              <h2 className="mb-4 text-sm font-semibold text-foreground">Category tree</h2>
              <CategoryTreeEditor
                tree={tree}
                onChanged={loadTree}
                onError={setActionError}
              />
            </section>

            <section className="rounded-xl border border-border bg-card p-4 xl:sticky xl:top-4 xl:self-start">
              <h2 className="mb-1 text-sm font-semibold text-foreground">Dropdown Choices – Preview</h2>
              <p className="mb-4 text-xs text-muted-foreground">
                Active options only — mirrors what IT staff see on Close and Properties.
              </p>
              <CascadePreview roots={activePreviewRoots} />
            </section>
          </div>
        )}
      </div>
    </>
  );
}
