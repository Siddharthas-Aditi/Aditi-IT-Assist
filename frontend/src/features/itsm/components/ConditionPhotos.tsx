/**
 * Dated photographic record of an asset's physical condition.
 *
 * Uploads are downscaled to a bounded JPEG before they are stored: the module
 * stays in the draft UI, and a handful of full-resolution phone photos
 * would exceed the quota and silently drop the whole store.
 */

import { useRef, useState } from 'react';
import { Camera, Trash2, X } from 'lucide-react';

import { newClientId } from '../client-id';
import {
  ASSET_CONDITIONS,
  type AssetCondition,
  type AssetConditionPhoto,
} from '../data/types';
import { cn } from '../lib/cn';
import { Button, EmptyState, Field, Select, TextInput } from './ui';

/** Long edge, in pixels, that stored photos are reduced to. */
const MAX_EDGE = 640;
const JPEG_QUALITY = 0.72;
const MAX_SOURCE_BYTES = 15 * 1024 * 1024;

const CONDITION_TONES: Record<AssetCondition, string> = {
  New: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  Good: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  Fair: 'bg-amber-50 text-amber-800 ring-amber-200',
  'Minor Damage': 'bg-amber-50 text-amber-800 ring-amber-200',
  Damaged: 'bg-red-50 text-red-800 ring-red-200',
  Faulty: 'bg-red-50 text-red-800 ring-red-200',
};

/** Read a file into a downscaled JPEG data URL via canvas. */
function downscale(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Could not read the file.'));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error('That file is not a readable image.'));
      img.onload = () => {
        const scale = Math.min(1, MAX_EDGE / Math.max(img.width, img.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(img.width * scale));
        canvas.height = Math.max(1, Math.round(img.height * scale));
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          reject(new Error('Canvas is unavailable in this browser.'));
          return;
        }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL('image/jpeg', JPEG_QUALITY));
      };
      img.src = reader.result as string;
    };
    reader.readAsDataURL(file);
  });
}

interface ConditionPhotosProps {
  photos: AssetConditionPhoto[];
  onChange: (next: AssetConditionPhoto[]) => void;
  onError: (message: string) => void;
  actorName: string;
  /** Detail pages render read-only until the user opts into editing. */
  readOnly?: boolean;
}

export function ConditionPhotos({
  photos,
  onChange,
  onError,
  actorName,
  readOnly = false,
}: ConditionPhotosProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [condition, setCondition] = useState<AssetCondition>('Good');
  const [note, setNote] = useState('');
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<AssetConditionPhoto | null>(null);

  async function accept(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    const added: AssetConditionPhoto[] = [];
    for (const file of Array.from(files)) {
      if (!file.type.startsWith('image/')) {
        onError(`“${file.name}” is not an image.`);
        continue;
      }
      if (file.size > MAX_SOURCE_BYTES) {
        onError(`“${file.name}” is larger than 15 MB.`);
        continue;
      }
      try {
        added.push({
          id: newClientId('photo'),
          name: file.name,
          condition,
          note: note.trim(),
          dataUrl: await downscale(file),
          capturedAt: new Date().toISOString(),
          capturedBy: actorName,
        });
      } catch (err) {
        onError(err instanceof Error ? err.message : `Could not process “${file.name}”.`);
      }
    }
    setBusy(false);
    if (added.length) {
      onChange([...photos, ...added]);
      setNote('');
    }
  }

  return (
    <div className="space-y-3">
      {!readOnly && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Condition for new photos" htmlFor="cond-select">
              <Select
                id="cond-select"
                options={ASSET_CONDITIONS}
                value={condition}
                onChange={(e) => setCondition(e.target.value as AssetCondition)}
              />
            </Field>
            <Field label="Note (optional)" htmlFor="cond-note">
              <TextInput
                id="cond-note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. Scratch on lid, hinge loose"
              />
            </Field>
          </div>

          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              void accept(e.dataTransfer.files);
            }}
            className={cn(
              'rounded-md border border-dashed px-4 py-6 text-center transition-colors',
              dragging ? 'border-sky-500 bg-sky-50' : 'border-slate-300 bg-slate-50',
            )}
          >
            <Camera size={18} className="mx-auto mb-1.5 text-slate-400" aria-hidden="true" />
            <p className="text-[12.5px] text-slate-600">
              Drag condition photos here or{' '}
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="rounded font-medium text-sky-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
              >
                browse
              </button>
            </p>
            <p className="mt-0.5 text-[11px] text-slate-500">
              {busy
                ? 'Processing…'
                : `Images are stored at up to ${MAX_EDGE}px. Source files up to 15 MB.`}
            </p>
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              multiple
              capture="environment"
              className="sr-only"
              onChange={(e) => {
                void accept(e.target.files);
                e.target.value = '';
              }}
            />
          </div>
        </>
      )}

      {photos.length === 0 ? (
        <EmptyState
          title="No condition photos"
          description="Photograph the asset at issue, handover, and return so its state is on record."
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {photos.map((p) => (
            <li
              key={p.id}
              className="overflow-hidden rounded-lg border border-slate-200 bg-white"
            >
              <button
                type="button"
                onClick={() => setPreview(p)}
                className="block w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
                aria-label={`View full size photo ${p.name}`}
              >
                <img
                  src={p.dataUrl}
                  alt={`${p.condition}${p.note ? ` — ${p.note}` : ''}`}
                  className="h-32 w-full bg-slate-100 object-cover"
                />
              </button>
              <div className="space-y-1 p-2">
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={cn(
                      'inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset',
                      CONDITION_TONES[p.condition],
                    )}
                  >
                    {p.condition}
                  </span>
                  {!readOnly && (
                    <button
                      type="button"
                      onClick={() => onChange(photos.filter((x) => x.id !== p.id))}
                      aria-label={`Remove photo ${p.name}`}
                      className="rounded p-0.5 text-slate-400 hover:text-red-600 focus:outline-none focus-visible:ring-1 focus-visible:ring-red-500"
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
                {p.note && <p className="text-[11.5px] text-slate-700">{p.note}</p>}
                <p className="text-[10.5px] text-slate-500">
                  {new Date(p.capturedAt).toLocaleDateString()} · {p.capturedBy}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}

      {preview && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Photo ${preview.name}`}
          onClick={() => setPreview(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
        >
          <div className="max-h-full max-w-3xl overflow-auto rounded-lg bg-white p-3">
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-[13px] font-medium text-slate-800">
                {preview.condition}
                {preview.note ? ` — ${preview.note}` : ''}
              </p>
              <Button variant="ghost" onClick={() => setPreview(null)} aria-label="Close preview">
                <X size={14} />
              </Button>
            </div>
            <img src={preview.dataUrl} alt={preview.name} className="max-h-[70vh] w-auto" />
          </div>
        </div>
      )}
    </div>
  );
}
