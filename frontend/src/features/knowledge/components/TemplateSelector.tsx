/** Template selector — card grid shown when creating a new article. */

import { FileText, X } from 'lucide-react';
import { useMemo } from 'react';

import type { ArticleTemplate } from '@/types/knowledge';

interface Props {
  templates: ArticleTemplate[];
  onSelect: (template: ArticleTemplate) => void;
  onDismiss: () => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  'email/outlook': 'Email & Outlook',
  'video-conferencing/zoom': 'Video Conferencing',
  'device-management/intune': 'Device Management',
  'hardware/camera': 'Hardware — Camera',
  'hardware/other': 'Hardware — General',
  'network/connectivity': 'Network & VPN',
  'access/permissions': 'Access & Permissions',
};

export function TemplateSelector({ templates, onSelect, onDismiss }: Props) {
  const grouped = useMemo(() => {
    const map = new Map<string, ArticleTemplate[]>();
    for (const t of templates) {
      const list = map.get(t.category) ?? [];
      list.push(t);
      map.set(t.category, list);
    }
    return Array.from(map.entries());
  }, [templates]);

  return (
    <div className="rounded-xl border border-border bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Start from a template</h2>
          <p className="text-xs text-gray-500">
            Pre-filled scaffolds speed up authoring — or start blank below.
          </p>
        </div>
        <button
          onClick={onDismiss}
          className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          title="Start blank"
        >
          <X size={16} />
        </button>
      </div>

      {/* Template grid */}
      <div className="p-4">
        {grouped.map(([category, items]) => (
          <div key={category} className="mb-5 last:mb-0">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
              {CATEGORY_LABELS[category] ?? category}
            </p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {items.map((t) => (
                <button
                  key={t.key}
                  onClick={() => onSelect(t)}
                  className="group flex items-start gap-3 rounded-lg border border-border bg-white p-3 text-left transition hover:border-primary hover:bg-primary/5"
                >
                  <span className="text-xl leading-none">{t.icon}</span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-800 group-hover:text-primary">
                      {t.label}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-gray-500">{t.description}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        ))}

        {/* Start blank CTA */}
        <div className="mt-4 border-t border-border pt-4">
          <button
            onClick={onDismiss}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-gray-300 py-2.5 text-sm text-gray-500 transition hover:border-gray-400 hover:text-gray-700"
          >
            <FileText size={15} />
            Start with a blank article
          </button>
        </div>
      </div>
    </div>
  );
}
