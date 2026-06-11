/** Tag/keyword input — add with Enter or comma, remove with click. */

import { X } from 'lucide-react';
import { useState } from 'react';

interface Props {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
}

export function TagsInput({ values, onChange, placeholder = 'Add and press Enter' }: Props) {
  const [draft, setDraft] = useState('');

  const add = (raw: string) => {
    const tag = raw.trim().toLowerCase();
    if (tag && !values.includes(tag)) onChange([...values, tag]);
    setDraft('');
  };

  const remove = (tag: string) => onChange(values.filter((t) => t !== tag));

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-white p-2">
      {values.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
        >
          {tag}
          <button
            type="button"
            onClick={() => remove(tag)}
            className="hover:text-red-600"
            aria-label={`Remove ${tag}`}
          >
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            add(draft);
          } else if (e.key === 'Backspace' && !draft && values.length) {
            remove(values[values.length - 1]);
          }
        }}
        onBlur={() => draft && add(draft)}
        placeholder={placeholder}
        className="min-w-[120px] flex-1 border-0 bg-transparent text-sm outline-none"
      />
    </div>
  );
}
