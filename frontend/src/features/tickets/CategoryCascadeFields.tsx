/** Shared L1 → L2 → L3 category cascade selects for Close and Properties forms. */

import { useEffect, useMemo, useState } from 'react';

import { ticketCategoriesApi, type TicketCategoryNode } from '@/lib/api';

import { filterActiveTree } from './categoryTreeUtils';

const SELECT_CLASS =
  'w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-500';

const LABEL_CLASS = 'mb-1 block text-xs font-medium text-gray-600';

export interface CategoryCascadeValues {
  category: string;
  subcategory: string;
  item: string;
}

interface Props extends CategoryCascadeValues {
  onChange: (values: CategoryCascadeValues) => void;
  disabled?: boolean;
}

function findChildByName(
  nodes: TicketCategoryNode[] | undefined,
  name: string,
): TicketCategoryNode | undefined {
  return nodes?.find((n) => n.name === name);
}

export function CategoryCascadeFields({
  category,
  subcategory,
  item,
  onChange,
  disabled = false,
}: Props) {
  const [roots, setRoots] = useState<TicketCategoryNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    ticketCategoriesApi
      .tree()
      .then(({ categories }) => {
        if (!cancelled) setRoots(filterActiveTree(categories));
      })
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
  }, []);

  const l1Node = useMemo(
    () => findChildByName(roots, category),
    [roots, category],
  );
  const l2Options = useMemo(
    () => l1Node?.children ?? [],
    [l1Node],
  );
  const l2Node = useMemo(
    () => findChildByName(l2Options, subcategory),
    [l2Options, subcategory],
  );
  const l3Options = useMemo(
    () => l2Node?.children ?? [],
    [l2Node],
  );
  const showEmptyItemsHint = Boolean(subcategory && l3Options.length === 0);

  const fieldsDisabled = disabled || loading;

  return (
    <div className="space-y-4">
      {loadError && (
        <p className="text-xs text-red-600" role="alert">
          {loadError}
        </p>
      )}

      <div>
        <label htmlFor="ticket-category" className={LABEL_CLASS}>
          Category <span className="text-red-500">*</span>
        </label>
        <select
          id="ticket-category"
          value={category}
          disabled={fieldsDisabled}
          onChange={(e) =>
            onChange({ category: e.target.value, subcategory: '', item: '' })
          }
          className={SELECT_CLASS}
        >
          <option value="">Select…</option>
          {roots.map((node) => (
            <option key={node.id} value={node.name}>
              {node.name}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="ticket-subcategory" className={LABEL_CLASS}>
          Sub-Category <span className="text-red-500">*</span>
        </label>
        <select
          id="ticket-subcategory"
          value={subcategory}
          disabled={fieldsDisabled || !category}
          onChange={(e) =>
            onChange({ category, subcategory: e.target.value, item: '' })
          }
          className={SELECT_CLASS}
        >
          <option value="">Select…</option>
          {l2Options.map((node) => (
            <option key={node.id} value={node.name}>
              {node.name}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="ticket-item" className={LABEL_CLASS}>
          Item <span className="text-red-500">*</span>
        </label>
        <select
          id="ticket-item"
          value={item}
          disabled={fieldsDisabled || !subcategory || l3Options.length === 0}
          onChange={(e) =>
            onChange({ category, subcategory, item: e.target.value })
          }
          className={SELECT_CLASS}
        >
          <option value="">Select…</option>
          {l3Options.map((node) => (
            <option key={node.id} value={node.name}>
              {node.name}
            </option>
          ))}
        </select>
        {showEmptyItemsHint && (
          <p className="mt-1 text-xs text-amber-700">
            No items configured — ask an IT admin to add items before closing.
          </p>
        )}
      </div>
    </div>
  );
}
