/** Right-rail Properties form for the IT ticket workspace. */

import { useEffect, useState } from 'react';

import { Card } from '@/components/ui';
import { ticketsApi } from '@/lib/api';

import { CategoryCascadeFields } from './CategoryCascadeFields';

const STATUS_OPTIONS = [
  'new',
  'triaged',
  'in_progress',
  'waiting_for_user',
  'escalated',
  'resolved',
] as const;

const PRIORITY_OPTIONS = ['critical', 'high', 'medium', 'low'] as const;

const TYPE_OPTIONS = [
  { value: 'incident', label: 'Incident' },
  { value: 'service_request', label: 'Service Request' },
  { value: 'problem', label: 'Problem' },
  { value: 'change', label: 'Change' },
  { value: 'other', label: 'Other' },
] as const;

const URGENCY_OPTIONS = ['low', 'medium', 'high'] as const;

const IMPACT_OPTIONS = ['individual', 'team', 'department', 'organization'] as const;

const SELECT_CLASS =
  'w-full rounded-lg border border-border bg-card px-2.5 py-1.5 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-60';

const TEXTAREA_CLASS =
  'w-full rounded-lg border border-border bg-card p-2.5 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-60';

const LABEL_CLASS = 'mb-1 block text-xs font-medium text-muted-foreground';

export interface TicketPropertiesData {
  status: string;
  priority: string;
  ticket_type?: string | null;
  urgency?: string | null;
  impact?: string | null;
  source?: string | null;
  category?: string | null;
  subcategory?: string | null;
  item?: string | null;
  resolution_notes?: string | null;
}

interface Props {
  ticketId: string;
  ticket: TicketPropertiesData;
  agentLabel: string;
  disabled?: boolean;
  onUpdated: () => void;
  onError: (message: string) => void;
}

function fmtLabel(value: string): string {
  return value.replace(/_/g, ' ');
}

export function TicketPropertiesPanel({
  ticketId,
  ticket,
  agentLabel,
  disabled = false,
  onUpdated,
  onError,
}: Props) {
  const [priority, setPriority] = useState(ticket.priority);
  const [status, setStatus] = useState(ticket.status);
  const [ticketType, setTicketType] = useState(ticket.ticket_type ?? '');
  const [urgency, setUrgency] = useState(ticket.urgency ?? '');
  const [impact, setImpact] = useState(ticket.impact ?? '');
  const [category, setCategory] = useState(ticket.category ?? '');
  const [subcategory, setSubcategory] = useState(ticket.subcategory ?? '');
  const [item, setItem] = useState(ticket.item ?? '');
  const [resolutionNotes, setResolutionNotes] = useState(ticket.resolution_notes ?? '');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setPriority(ticket.priority);
    setStatus(ticket.status);
    setTicketType(ticket.ticket_type ?? '');
    setUrgency(ticket.urgency ?? '');
    setImpact(ticket.impact ?? '');
    setCategory(ticket.category ?? '');
    setSubcategory(ticket.subcategory ?? '');
    setItem(ticket.item ?? '');
    setResolutionNotes(ticket.resolution_notes ?? '');
  }, [ticket]);

  const fieldsDisabled = disabled || submitting;

  const handleUpdate = async () => {
    setSubmitting(true);
    onError('');
    try {
      await ticketsApi.update(ticketId, {
        priority,
        status,
        ticket_type: ticketType || null,
        urgency: urgency || null,
        impact: impact || null,
        category: category || null,
        subcategory: subcategory || null,
        item: item || null,
        resolution_notes: resolutionNotes || null,
      });
      onUpdated();
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Failed to update ticket');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <h2 className="mb-4 text-sm font-semibold text-foreground">Properties</h2>
      <div className="space-y-4">
        <Field label="Priority" htmlFor="ticket-priority">
          <select
            id="ticket-priority"
            value={priority}
            disabled={fieldsDisabled}
            onChange={(e) => setPriority(e.target.value)}
            className={SELECT_CLASS}
          >
            {PRIORITY_OPTIONS.map((p) => (
              <option key={p} value={p}>
                {fmtLabel(p)}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Status" htmlFor="ticket-status">
          <select
            id="ticket-status"
            value={status}
            disabled={fieldsDisabled}
            onChange={(e) => setStatus(e.target.value)}
            className={SELECT_CLASS}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {fmtLabel(s)}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Source">
          <p className="text-sm capitalize text-foreground">
            {ticket.source ? fmtLabel(ticket.source) : '—'}
          </p>
        </Field>

        <Field label="Type" htmlFor="ticket-type">
          <select
            id="ticket-type"
            value={ticketType}
            disabled={fieldsDisabled}
            onChange={(e) => setTicketType(e.target.value)}
            className={SELECT_CLASS}
          >
            <option value="">Select…</option>
            {TYPE_OPTIONS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Urgency" htmlFor="ticket-urgency">
          <select
            id="ticket-urgency"
            value={urgency}
            disabled={fieldsDisabled}
            onChange={(e) => setUrgency(e.target.value)}
            className={SELECT_CLASS}
          >
            <option value="">Select…</option>
            {URGENCY_OPTIONS.map((u) => (
              <option key={u} value={u}>
                {fmtLabel(u)}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Impact" htmlFor="ticket-impact">
          <select
            id="ticket-impact"
            value={impact}
            disabled={fieldsDisabled}
            onChange={(e) => setImpact(e.target.value)}
            className={SELECT_CLASS}
          >
            <option value="">Select…</option>
            {IMPACT_OPTIONS.map((i) => (
              <option key={i} value={i}>
                {fmtLabel(i)}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Agent">
          <p className="text-sm text-foreground">{agentLabel}</p>
        </Field>

        <CategoryCascadeFields
          category={category}
          subcategory={subcategory}
          item={item}
          onChange={({ category: c, subcategory: s, item: it }) => {
            setCategory(c);
            setSubcategory(s);
            setItem(it);
          }}
          disabled={fieldsDisabled}
        />

        <Field label="Resolution notes" htmlFor="ticket-resolution-notes">
          <textarea
            id="ticket-resolution-notes"
            value={resolutionNotes}
            onChange={(e) => setResolutionNotes(e.target.value)}
            rows={4}
            disabled={fieldsDisabled}
            placeholder="Draft resolution notes…"
            className={TEXTAREA_CLASS}
          />
        </Field>

        <button
          type="button"
          disabled={fieldsDisabled}
          onClick={() => void handleUpdate()}
          className="w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {submitting ? 'Updating…' : 'Update'}
        </button>
      </div>
    </Card>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className={LABEL_CLASS}>
        {label}
      </label>
      {children}
    </div>
  );
}
