/** Ordered step-list builder for troubleshooting/resolution/validation sections. */

import { GripVertical, Plus, Trash2 } from 'lucide-react';

import type { Step } from '@/types/knowledge';

interface Props {
  label: string;
  steps: Step[];
  onChange: (steps: Step[]) => void;
}

export function StepsEditor({ label, steps, onChange }: Props) {
  const renumber = (list: Step[]): Step[] =>
    list.map((s, i) => ({ ...s, step_number: i + 1 }));

  const update = (index: number, patch: Partial<Step>) => {
    const next = steps.map((s, i) => (i === index ? { ...s, ...patch } : s));
    onChange(next);
  };

  const add = () =>
    onChange(renumber([...steps, { step_number: steps.length + 1, instruction: '', details: '' }]));

  const remove = (index: number) => onChange(renumber(steps.filter((_, i) => i !== index)));

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-foreground">{label}</label>
        <button
          type="button"
          onClick={add}
          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs font-medium text-primary hover:bg-primary/5"
        >
          <Plus size={14} /> Add step
        </button>
      </div>

      {steps.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
          No steps yet.
        </p>
      ) : (
        <ol className="space-y-2">
          {steps.map((step, index) => (
            <li key={index} className="flex gap-2 rounded-lg border border-border bg-white p-2">
              <div className="flex flex-col items-center pt-2 text-muted-foreground">
                <GripVertical size={14} />
                <span className="text-xs font-semibold">{index + 1}</span>
              </div>
              <div className="flex-1 space-y-1">
                <input
                  value={step.instruction}
                  onChange={(e) => update(index, { instruction: e.target.value })}
                  placeholder="Instruction"
                  className="w-full rounded-md border border-border px-2 py-1 text-sm outline-none focus:border-primary"
                />
                <input
                  value={step.details ?? ''}
                  onChange={(e) => update(index, { details: e.target.value })}
                  placeholder="Details (optional)"
                  className="w-full rounded-md border border-border px-2 py-1 text-xs text-muted-foreground outline-none focus:border-primary"
                />
              </div>
              <button
                type="button"
                onClick={() => remove(index)}
                className="self-start p-1 text-muted-foreground hover:text-red-600"
                aria-label="Remove step"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
