/** Searchable person picker, asset multi-select, and the attachment drop zone. */

import { useMemo, useRef, useState } from 'react';
import { Paperclip, Search, X } from 'lucide-react';

import { PEOPLE } from '../data/reference';
import { newClientId } from '../client-id';
import type { Asset, Attachment } from '../data/types';
import { cn } from '../lib/cn';
import { Button } from './ui';

// ── Requester / agent picker ───────────────────────────────────────────

export function PersonPicker({
  value,
  onChange,
  id,
  invalid,
  allowAddNew = false,
}: {
  value: string;
  onChange: (id: string) => void;
  id?: string;
  invalid?: boolean;
  allowAddNew?: boolean;
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [extra, setExtra] = useState<{ id: string; name: string; email: string }[]>([]);

  const all = useMemo(() => [...PEOPLE, ...extra], [extra]);
  const chosen = all.find((p) => p.id === value);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return all.slice(0, 6);
    return all
      .filter(
        (p) => p.name.toLowerCase().includes(needle) || p.email.toLowerCase().includes(needle),
      )
      .slice(0, 6);
  }, [query, all]);

  function addNew() {
    const name = query.trim();
    if (!name) return;
    const person = {
      id: newClientId('user'),
      name,
      email: `${name.toLowerCase().replace(/\s+/g, '.')}@aditiconsulting.com`,
    };
    setExtra((e) => [...e, person]);
    onChange(person.id);
    setQuery('');
    setOpen(false);
  }

  if (chosen) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-slate-300 bg-white px-2.5 py-1.5">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-sky-100 text-[10px] font-semibold text-sky-700">
          {chosen.name.charAt(0)}
        </span>
        <span className="flex-1 truncate text-[13px] text-slate-900">{chosen.name}</span>
        <button
          type="button"
          onClick={() => onChange('')}
          aria-label="Clear selection"
          className="rounded p-0.5 text-slate-500 hover:text-red-600 focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
        >
          <X size={13} />
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <Search
        size={13}
        aria-hidden="true"
        className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500"
      />
      <input
        id={id}
        value={query}
        aria-invalid={invalid}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        placeholder="Search people…"
        className={cn(
          'w-full rounded-md border bg-white py-1.5 pl-8 pr-3 text-[13px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-1',
          invalid
            ? 'border-red-600 focus:border-red-500 focus:ring-red-500'
            : 'border-slate-300 focus:border-sky-500 focus:ring-sky-500',
        )}
      />
      {open && (
        <ul className="absolute z-30 mt-1 w-full overflow-hidden rounded-md border border-slate-300 bg-white shadow-xl">
          {matches.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onChange(p.id);
                  setQuery('');
                  setOpen(false);
                }}
                className="block w-full px-3 py-1.5 text-left text-[12.5px] text-slate-700 hover:bg-slate-100 hover:text-slate-900"
              >
                {p.name}
                <span className="ml-1.5 text-slate-500">{p.email}</span>
              </button>
            </li>
          ))}
          {allowAddNew && query.trim() && (
            <li className="border-t border-slate-200">
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={addNew}
                className="block w-full px-3 py-1.5 text-left text-[12.5px] font-medium text-sky-700 hover:bg-slate-100"
              >
                + Add new requester “{query.trim()}”
              </button>
            </li>
          )}
          {matches.length === 0 && !allowAddNew && (
            <li className="px-3 py-1.5 text-[12.5px] text-slate-500">No matches.</li>
          )}
        </ul>
      )}
    </div>
  );
}

// ── Asset association ──────────────────────────────────────────────────

export function AssetPicker({
  assets,
  value,
  onChange,
}: {
  assets: Asset[];
  value: string[];
  onChange: (ids: string[]) => void;
}) {
  const [query, setQuery] = useState('');
  const selected = assets.filter((a) => value.includes(a.id));

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];
    return assets
      .filter((a) => !value.includes(a.id))
      .filter(
        (a) =>
          a.assetTag.toLowerCase().includes(needle) ||
          a.name.toLowerCase().includes(needle) ||
          a.serialNumber.toLowerCase().includes(needle),
      )
      .slice(0, 6);
  }, [query, assets, value]);

  return (
    <div className="space-y-1.5">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search assets by tag, name, or serial…"
        aria-label="Search assets to associate"
        className="w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-[13px] text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
      />
      {matches.length > 0 && (
        <ul className="overflow-hidden rounded-md border border-slate-300 bg-white">
          {matches.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => {
                  onChange([...value, a.id]);
                  setQuery('');
                }}
                className="block w-full px-3 py-1.5 text-left text-[12.5px] text-slate-700 hover:bg-slate-100 hover:text-slate-900"
              >
                <span className="font-medium text-sky-700">{a.assetTag}</span> — {a.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {selected.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {selected.map((a) => (
            <li key={a.id}>
              <span className="inline-flex items-center gap-1 rounded border border-slate-300 bg-slate-100 py-0.5 pl-2 pr-1 text-[12px] text-slate-800">
                {a.assetTag}
                <button
                  type="button"
                  onClick={() => onChange(value.filter((id) => id !== a.id))}
                  aria-label={`Remove ${a.assetTag}`}
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
  );
}

// ── Attachments ────────────────────────────────────────────────────────

export const MAX_UPLOAD_BYTES = 40 * 1024 * 1024;

export function AttachmentZone({
  attachments,
  onChange,
  onReject,
}: {
  attachments: Attachment[];
  onChange: (next: Attachment[]) => void;
  onReject: (message: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function accept(files: FileList | null) {
    if (!files?.length) return;
    const next: Attachment[] = [];
    for (const file of Array.from(files)) {
      if (file.size > MAX_UPLOAD_BYTES) {
        onReject(`“${file.name}” is larger than the 40 MB limit.`);
        continue;
      }
      next.push({
        id: newClientId('att'),
        name: file.name,
        sizeBytes: file.size,
        kind: file.type || 'application/octet-stream',
        uploadedAt: new Date().toISOString(),
      });
    }
    if (next.length) onChange([...attachments, ...next]);
  }

  return (
    <div className="space-y-2">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          accept(e.dataTransfer.files);
        }}
        className={cn(
          'rounded-md border border-dashed px-4 py-6 text-center transition-colors',
          dragging ? 'border-sky-500 bg-sky-50' : 'border-slate-300 bg-slate-50',
        )}
      >
        <Paperclip size={18} className="mx-auto mb-1.5 text-slate-500" aria-hidden="true" />
        <p className="text-[12.5px] text-slate-500">
          Drag files here or{' '}
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="rounded font-medium text-sky-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
          >
            browse
          </button>
        </p>
        <p className="mt-0.5 text-[11px] text-slate-500">Maximum file size 40 MB.</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="sr-only"
          onChange={(e) => {
            accept(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      {attachments.length > 0 && (
        <ul className="space-y-1">
          {attachments.map((a) => (
            <li
              key={a.id}
              className="flex items-center gap-2 rounded border border-slate-200 bg-white px-2.5 py-1.5 text-[12.5px]"
            >
              <Paperclip size={12} className="text-slate-500" aria-hidden="true" />
              <span className="flex-1 truncate text-slate-800">{a.name}</span>
              <span className="text-slate-500">{(a.sizeBytes / 1024).toFixed(0)} KB</span>
              <Button
                variant="ghost"
                onClick={() => onChange(attachments.filter((x) => x.id !== a.id))}
                aria-label={`Remove ${a.name}`}
              >
                <X size={12} />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
