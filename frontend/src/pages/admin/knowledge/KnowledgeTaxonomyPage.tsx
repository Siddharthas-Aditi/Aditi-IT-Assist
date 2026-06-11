/** Taxonomy management — admin-managed classification vocabulary. */

import { Plus } from 'lucide-react';
import { useMemo, useState } from 'react';

import { useCreateTaxonomyTerm, useTaxonomy } from '@/features/knowledge';
import { hasPermission, P } from '@/lib/permissions';
import { useAuthStore } from '@/stores/auth-store';

const TERM_TYPES = ['category', 'subcategory', 'product', 'platform', 'issue_type', 'tag'];

export function KnowledgeTaxonomyPage() {
  const user = useAuthStore((s) => s.user);
  const { data: terms, isLoading } = useTaxonomy();
  const createTerm = useCreateTaxonomyTerm();
  const canManage = hasPermission(user, P.KNOWLEDGE_MANAGE_CATEGORIES);

  const [draft, setDraft] = useState({ term_type: 'category', key: '', label: '', mapping: '' });
  const [error, setError] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const map: Record<string, typeof terms> = {};
    for (const t of terms ?? []) (map[t.term_type] ??= []).push(t);
    return map;
  }, [terms]);

  const add = async () => {
    setError(null);
    if (!draft.key || !draft.label) return;
    try {
      await createTerm.mutateAsync({
        term_type: draft.term_type,
        key: draft.key,
        label: draft.label,
        ticket_category_mapping: draft.mapping || undefined,
      });
      setDraft({ term_type: draft.term_type, key: '', label: '', mapping: '' });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add term');
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900">Taxonomy</h1>
      <p className="mb-5 mt-1 text-sm text-gray-500">
        Standardize article classification. Map categories to ticket categories for aligned routing.
      </p>

      {canManage && (
        <div className="mb-6 rounded-xl border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-semibold text-foreground">Add term</h3>
          <div className="flex flex-wrap items-end gap-2">
            <select
              value={draft.term_type}
              onChange={(e) => setDraft({ ...draft, term_type: e.target.value })}
              className="rounded-lg border border-border px-2.5 py-2 text-sm"
            >
              {TERM_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <input
              value={draft.key}
              onChange={(e) => setDraft({ ...draft, key: e.target.value })}
              placeholder="key (e.g. email/outlook)"
              className="rounded-lg border border-border px-2.5 py-2 text-sm"
            />
            <input
              value={draft.label}
              onChange={(e) => setDraft({ ...draft, label: e.target.value })}
              placeholder="Label"
              className="rounded-lg border border-border px-2.5 py-2 text-sm"
            />
            <input
              value={draft.mapping}
              onChange={(e) => setDraft({ ...draft, mapping: e.target.value })}
              placeholder="Ticket category (optional)"
              className="rounded-lg border border-border px-2.5 py-2 text-sm"
            />
            <button
              onClick={add}
              disabled={createTerm.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              <Plus size={15} /> Add
            </button>
          </div>
          {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        </div>
      )}

      {isLoading ? (
        <div className="py-16 text-center text-muted-foreground">Loading taxonomy…</div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {TERM_TYPES.map((type) => (
            <div key={type} className="rounded-xl border border-border bg-white p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {type}
              </h3>
              <div className="space-y-1">
                {(grouped[type] ?? []).length === 0 ? (
                  <p className="text-xs text-muted-foreground">No terms.</p>
                ) : (
                  grouped[type]!.map((t) => (
                    <div
                      key={t.id}
                      className="flex items-center justify-between rounded-md border border-border px-2.5 py-1.5 text-sm"
                    >
                      <span className="font-medium text-foreground">{t.label}</span>
                      <span className="font-mono text-xs text-muted-foreground">{t.key}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
