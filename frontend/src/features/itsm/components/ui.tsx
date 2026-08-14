/**
 * Compact primitives for the ITSM modules.
 *
 * Denser than the shared `components/ui` set (smaller type, tighter padding)
 * because Change and Asset screens are data-heavy tables and long forms, but
 * they use the same light surfaces and slate ink as the rest of the console so
 * the modules read as part of Aditi IT Assist rather than a separate product.
 */

import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';
import { forwardRef, useId } from 'react';

import { cn } from '../lib/cn';
import type { Level } from '../data/types';

// ── Buttons ────────────────────────────────────────────────────────────

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-sky-600 text-white hover:bg-sky-700 focus-visible:outline-sky-600',
  secondary:
    'bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 focus-visible:outline-slate-500',
  ghost: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-slate-500',
  danger: 'bg-red-600 text-white hover:bg-red-700 focus-visible:outline-red-600',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ variant = 'secondary', className, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors',
        'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2',
        'disabled:cursor-not-allowed disabled:opacity-50',
        VARIANTS[variant],
        className,
      )}
    />
  );
}

// ── Form controls ──────────────────────────────────────────────────────

const CONTROL =
  'w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-[13px] text-slate-900 ' +
  'placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500 ' +
  'disabled:cursor-not-allowed disabled:opacity-60';

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function TextInput({ className, ...rest }, ref) {
    return <input ref={ref} {...rest} className={cn(CONTROL, className)} />;
  },
);

export const TextArea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function TextArea({ className, rows = 3, ...rest }, ref) {
  return <textarea ref={ref} rows={rows} {...rest} className={cn(CONTROL, className)} />;
});

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  options: readonly string[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { options, placeholder, className, ...rest },
  ref,
) {
  return (
    <select ref={ref} {...rest} className={cn(CONTROL, 'pr-8', className)}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
});

interface FieldProps {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  htmlFor?: string;
  className?: string;
  children: ReactNode;
}

/** Label + control + inline validation, wired for screen readers. */
export function Field({ label, required, error, hint, htmlFor, className, children }: FieldProps) {
  return (
    <div className={cn('space-y-1', className)}>
      <label
        htmlFor={htmlFor}
        className="block text-[12px] font-medium text-slate-700"
      >
        {label}
        {required && (
          <span className="ml-0.5 text-red-600" aria-hidden="true">
            *
          </span>
        )}
        {required && <span className="sr-only"> (required)</span>}
      </label>
      {children}
      {hint && !error && <p className="text-[11px] text-slate-500">{hint}</p>}
      {error && (
        <p role="alert" className="text-[11px] font-medium text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}

/** Field wrapper that generates and wires its own id. */
export function LabeledField({
  label,
  required,
  error,
  hint,
  render,
}: Omit<FieldProps, 'children' | 'htmlFor'> & {
  render: (props: { id: string; 'aria-invalid': boolean }) => ReactNode;
}) {
  const id = useId();
  return (
    <Field label={label} required={required} error={error} hint={hint} htmlFor={id}>
      {render({ id, 'aria-invalid': Boolean(error) })}
    </Field>
  );
}

// ── Badges ─────────────────────────────────────────────────────────────

const STATUS_TONES: Record<string, string> = {
  // Change statuses
  Draft: 'bg-slate-100 text-slate-700 ring-slate-300',
  Open: 'bg-sky-50 text-sky-800 ring-sky-200',
  Planning: 'bg-indigo-50 text-indigo-800 ring-indigo-200',
  'Pending Approval': 'bg-amber-50 text-amber-800 ring-amber-200',
  Scheduled: 'bg-violet-50 text-violet-800 ring-violet-200',
  'In Progress': 'bg-blue-50 text-blue-800 ring-blue-200',
  Completed: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  Rejected: 'bg-red-50 text-red-800 ring-red-200',
  Cancelled: 'bg-slate-100 text-slate-500 ring-slate-300',
  // Asset states
  'In Stock': 'bg-slate-100 text-slate-700 ring-slate-300',
  Assigned: 'bg-sky-50 text-sky-800 ring-sky-200',
  'In Use': 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  'Under Repair': 'bg-amber-50 text-amber-800 ring-amber-200',
  Reserved: 'bg-violet-50 text-violet-800 ring-violet-200',
  Lost: 'bg-red-50 text-red-800 ring-red-200',
  Retired: 'bg-slate-100 text-slate-500 ring-slate-300',
  Disposed: 'bg-slate-200 text-slate-600 ring-slate-300',
  // Approval decisions
  Approved: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  Pending: 'bg-amber-50 text-amber-800 ring-amber-200',
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset',
        STATUS_TONES[status] ?? 'bg-slate-100 text-slate-700 ring-slate-300',
      )}
    >
      {status}
    </span>
  );
}

const LEVEL_TONES: Record<Level, { dot: string; text: string }> = {
  Low: { dot: 'bg-emerald-500', text: 'text-emerald-700' },
  Medium: { dot: 'bg-amber-500', text: 'text-amber-700' },
  High: { dot: 'bg-orange-500', text: 'text-orange-700' },
  Urgent: { dot: 'bg-red-500', text: 'text-red-700' },
};

/** Priority / risk / impact share one dot-plus-label treatment. */
export function LevelIndicator({ level }: { level: string }) {
  const tone = LEVEL_TONES[level as Level] ?? LEVEL_TONES.Low;
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-[12px]', tone.text)}>
      <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', tone.dot)} aria-hidden="true" />
      {level}
    </span>
  );
}

export function ChangeTypeBadge({ type }: { type: string }) {
  const tone =
    type === 'Emergency'
      ? 'bg-red-50 text-red-800 ring-red-200'
      : type === 'Standard'
        ? 'bg-slate-100 text-slate-700 ring-slate-300'
        : 'bg-sky-50 text-sky-800 ring-sky-200';
  return (
    <span
      className={cn(
        'inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset',
        tone,
      )}
    >
      {type}
    </span>
  );
}

// ── Layout helpers ─────────────────────────────────────────────────────

export function Panel({
  title,
  actions,
  children,
  className,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('rounded-lg border border-slate-200 bg-white', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-2.5">
          {title && <h2 className="text-[13px] font-semibold text-slate-800">{title}</h2>}
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

/** Read-only key/value row used across both detail pages. */
export function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(120px,180px)_1fr] gap-3 py-1.5">
      <dt className="text-[12px] text-slate-500">{label}</dt>
      <dd className="text-[13px] text-slate-800">{children || '—'}</dd>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <p className="text-[14px] font-medium text-slate-700">{title}</p>
      {description && <p className="max-w-md text-[12px] text-slate-500">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 px-6 py-14 text-slate-500" role="status">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-300 border-t-sky-400" />
      <span className="text-[13px]">{label}</span>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-600"
    >
      {message}
    </div>
  );
}
