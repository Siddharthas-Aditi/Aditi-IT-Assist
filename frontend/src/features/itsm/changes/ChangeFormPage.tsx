/** Create / edit a change — main form plus the nine planning fields. */

import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Search } from 'lucide-react';

import { AssetPicker, AttachmentZone, PersonPicker } from '../components/Pickers';
import { RichTextEditor } from '../components/RichText';
import { PageHeader } from '../components/chrome';
import { useToast } from '../components/toast-context';
import { Button, ErrorState, Field, Panel, Select, TextArea, TextInput } from '../components/ui';
import {
  CATEGORIES,
  DEPARTMENTS,
  GROUPS,
  MAINTENANCE_WINDOWS,
  PEOPLE,
  WORKSPACES,
} from '../data/reference';
import { initialStatusFor } from '../data/rules';
import {
  createChange,
  getChange,
  logChangeActivity,
  touchTemplate,
  useItsmState,
} from '../data/store';
import {
  CHANGE_STATUSES,
  CHANGE_TYPES,
  IMPACTS,
  PRIORITIES,
  RISKS,
  type Attachment,
} from '../data/types';
import {
  applyTemplate,
  clearSessionDraft,
  draftFromChange,
  emptyDraft,
  loadSessionDraft,
  PLANNING_FIELDS,
  saveSessionDraft,
  validateChange,
  type ChangeDraft,
  type ChangeErrors,
} from './form-model';

export function ChangeFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const { assets, templates, changes } = useItsmState();

  const [params] = useSearchParams();
  const editing = id ? getChange(id) : undefined;
  const isEdit = Boolean(id);

  // A change raised from a ticket arrives with the ticket's context in the
  // query string, so the specialist doesn't retype what support already knows.
  const ticketId = params.get('ticketId');
  const ticketNumber = params.get('ticketNumber') ?? '';
  const fromTicket = useMemo(
    () => (ticketId ? { id: ticketId, number: ticketNumber } : null),
    [ticketId, ticketNumber],
  );

  const [draft, setDraft] = useState<ChangeDraft>(() => {
    if (editing) return draftFromChange(editing);
    if (fromTicket) {
      const seeded = emptyDraft();
      const desc = params.get('description');
      return {
        ...seeded,
        subject: params.get('subject') ?? '',
        requesterId: params.get('requesterId') ?? '',
        category: params.get('category') ?? '',
        description: desc ? `<p>${desc}</p>` : '',
        assetIds: (params.get('assetIds') ?? '').split(',').filter(Boolean),
        planning: {
          ...seeded.planning,
          reasonForChange: params.get('ticketNumber')
            ? `Raised from support ticket ${params.get('ticketNumber')}.`
            : '',
        },
      };
    }
    return loadSessionDraft() ?? emptyDraft();
  });
  const [attachments, setAttachments] = useState<Attachment[]>(editing?.attachments ?? []);
  const [errors, setErrors] = useState<ChangeErrors>({});
  const [templateQuery, setTemplateQuery] = useState('');

  // Keep unsaved new-change state alive across navigation within the session.
  useEffect(() => {
    if (!isEdit && !fromTicket) saveSessionDraft(draft);
  }, [draft, isEdit, fromTicket]);

  const recentTemplates = useMemo(
    () =>
      templates
        .filter((t) => !t.archived)
        .filter((t) => t.name.toLowerCase().includes(templateQuery.trim().toLowerCase()))
        .sort((a, b) => (b.lastUsedAt ?? '').localeCompare(a.lastUsedAt ?? ''))
        .slice(0, 5),
    [templates, templateQuery],
  );

  function set<K extends keyof ChangeDraft>(key: K, value: ChangeDraft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
    setErrors((e) => ({ ...e, [key]: undefined }));
  }

  function setPlanning(key: keyof ChangeDraft['planning'], value: string) {
    setDraft((d) => ({ ...d, planning: { ...d.planning, [key]: value } }));
  }

  /** Emergency changes are High risk by default — the user may still raise it. */
  function onChangeType(next: string) {
    setDraft((d) => ({
      ...d,
      changeType: next as ChangeDraft['changeType'],
      risk: next === 'Emergency' ? 'High' : d.risk,
      maintenanceWindow:
        next === 'Emergency' ? 'Emergency – Immediate' : d.maintenanceWindow,
    }));
    setErrors((e) => ({ ...e, changeType: undefined }));
  }

  function persist(status: ChangeDraft['status'], announce: string) {
    const base = {
      workspace: draft.workspace,
      requesterId: draft.requesterId,
      subject: draft.subject.trim(),
      changeType: draft.changeType,
      status,
      priority: draft.priority,
      impact: draft.impact,
      risk: draft.risk,
      group: draft.group,
      agentId: draft.agentId || null,
      description: draft.description,
      plannedStart: draft.plannedStart ? new Date(draft.plannedStart).toISOString() : '',
      plannedEnd: draft.plannedEnd ? new Date(draft.plannedEnd).toISOString() : '',
      department: draft.department,
      category: draft.category,
      maintenanceWindow: draft.maintenanceWindow,
      assetIds: draft.assetIds,
      attachments,
      planning: draft.planning,
      emergencyJustification: draft.emergencyJustification,
    };

    if (isEdit && editing) {
      logChangeActivity(editing.id, 'Sagar J', announce, base);
      toast.success(announce);
      navigate(`/itsm/changes/${editing.id}`);
      return;
    }

    const created = createChange({
      ...base,
      sourceTicketId: fromTicket?.id ?? null,
      sourceTicketNumber: fromTicket?.number || null,
      actualStart: null,
      actualEnd: null,
      approvals:
        status === 'Draft'
          ? []
          : [
              {
                id: `apr-${Date.now()}`,
                stage: 1,
                name: `${draft.group || 'Change'} Lead`,
                approverId: 'u-hareesh',
                approverName: 'Hareesh Kumar',
                decision: 'Pending',
                comments: '',
                decidedAt: null,
              },
            ],
      implementationTasks: draft.planning.implementationSteps
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((label, i) => ({ id: `t-new-${i}`, label, done: false })),
      closureNotes: '',
      activity: [
        {
          id: `act-${Date.now()}`,
          at: new Date().toISOString(),
          actor: 'Sagar J',
          action: announce,
        },
      ],
    });

    clearSessionDraft();
    toast.success(`${created.changeId} ${announce.toLowerCase()}.`);
    navigate(`/itsm/changes/${created.id}`);
  }

  function onSubmit() {
    const found = validateChange(draft);
    setErrors(found);
    if (Object.keys(found).length > 0) {
      toast.error('Fix the highlighted fields before submitting.');
      const first = document.querySelector('[aria-invalid="true"]');
      (first as HTMLElement | null)?.focus();
      return;
    }
    persist(initialStatusFor(draft.changeType), isEdit ? 'Change updated' : 'Change submitted');
  }

  if (isEdit && !editing) {
    return <ErrorState message={`No change found for “${id}”.`} />;
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 pb-10">
      <PageHeader
        title={isEdit ? `Edit ${editing?.changeId}` : 'New change'}
        crumbs={[
          { label: 'Changes', to: '/itsm/changes' },
          { label: isEdit ? (editing?.changeId ?? 'Edit') : 'New change' },
        ]}
      />

      {fromTicket && (
        <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-[12.5px] text-sky-900">
          Raised from support ticket <strong>{fromTicket.number}</strong>. Requester, category, and
          any linked assets have been carried over.
        </div>
      )}

      {!isEdit && (
        <Panel title="Start from a template">
          <div className="relative mb-2.5">
            <Search
              size={14}
              aria-hidden="true"
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500"
            />
            <input
              value={templateQuery}
              onChange={(e) => setTemplateQuery(e.target.value)}
              placeholder="Search templates…"
              aria-label="Search templates"
              className="w-full rounded-md border border-slate-300 bg-white py-1.5 pl-8 pr-3 text-[13px] text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
          </div>
          <p className="mb-1.5 text-[11px] uppercase tracking-wide text-slate-500">
            Recently used templates
          </p>
          <ul className="space-y-1">
            {recentTemplates.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  onClick={() => {
                    setDraft((d) => applyTemplate(d, t));
                    touchTemplate(t.id);
                    toast.info(`Applied template “${t.name}”.`);
                  }}
                  className="w-full rounded border border-slate-200 bg-white px-3 py-2 text-left text-[12.5px] text-slate-800 transition-colors hover:border-sky-400 hover:bg-slate-100 focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
                >
                  {t.name}
                  <span className="ml-2 text-[11px] text-slate-500">{t.changeType}</span>
                </button>
              </li>
            ))}
            {recentTemplates.length === 0 && (
              <li className="text-[12.5px] text-slate-500">No templates match that search.</li>
            )}
          </ul>
        </Panel>
      )}

      <Panel title="Change details">
        <div className="grid gap-3.5 sm:grid-cols-2">
          <Field label="Workspace" required error={errors.workspace} htmlFor="cf-workspace">
            <Select
              id="cf-workspace"
              options={WORKSPACES}
              placeholder="Select workspace"
              value={draft.workspace}
              aria-invalid={Boolean(errors.workspace)}
              onChange={(e) => set('workspace', e.target.value)}
            />
          </Field>

          <Field label="Requester" required error={errors.requesterId} htmlFor="cf-requester">
            <PersonPicker
              id="cf-requester"
              value={draft.requesterId}
              onChange={(v) => set('requesterId', v)}
              invalid={Boolean(errors.requesterId)}
              allowAddNew
            />
          </Field>

          <Field
            label="Subject"
            required
            error={errors.subject}
            htmlFor="cf-subject"
            className="sm:col-span-2"
          >
            <TextInput
              id="cf-subject"
              value={draft.subject}
              aria-invalid={Boolean(errors.subject)}
              onChange={(e) => set('subject', e.target.value)}
              placeholder="Short summary of the change"
            />
          </Field>

          <Field label="Change Type" required error={errors.changeType} htmlFor="cf-type">
            <Select
              id="cf-type"
              options={CHANGE_TYPES}
              value={draft.changeType}
              aria-invalid={Boolean(errors.changeType)}
              onChange={(e) => onChangeType(e.target.value)}
            />
          </Field>

          <Field label="Status" required error={errors.status} htmlFor="cf-status">
            <Select
              id="cf-status"
              options={CHANGE_STATUSES}
              value={draft.status}
              aria-invalid={Boolean(errors.status)}
              onChange={(e) => set('status', e.target.value as ChangeDraft['status'])}
            />
          </Field>

          <Field label="Priority" htmlFor="cf-priority">
            <Select
              id="cf-priority"
              options={PRIORITIES}
              value={draft.priority}
              onChange={(e) => set('priority', e.target.value as ChangeDraft['priority'])}
            />
          </Field>

          <Field label="Impact" htmlFor="cf-impact">
            <Select
              id="cf-impact"
              options={IMPACTS}
              value={draft.impact}
              onChange={(e) => set('impact', e.target.value as ChangeDraft['impact'])}
            />
          </Field>

          <Field
            label="Risk"
            htmlFor="cf-risk"
            hint={draft.changeType === 'Emergency' ? 'Emergency changes default to High.' : undefined}
          >
            <Select
              id="cf-risk"
              options={RISKS}
              value={draft.risk}
              onChange={(e) => set('risk', e.target.value as ChangeDraft['risk'])}
            />
          </Field>

          <Field label="Group" htmlFor="cf-group">
            <Select
              id="cf-group"
              options={GROUPS}
              placeholder="Unassigned"
              value={draft.group}
              onChange={(e) => set('group', e.target.value)}
            />
          </Field>

          <Field label="Agent" htmlFor="cf-agent">
            <Select
              id="cf-agent"
              options={PEOPLE.map((p) => p.name)}
              placeholder="Unassigned"
              value={PEOPLE.find((p) => p.id === draft.agentId)?.name ?? ''}
              onChange={(e) =>
                set('agentId', PEOPLE.find((p) => p.name === e.target.value)?.id ?? '')
              }
            />
          </Field>

          <Field label="Department" htmlFor="cf-dept">
            <Select
              id="cf-dept"
              options={DEPARTMENTS}
              placeholder="Select department"
              value={draft.department}
              onChange={(e) => set('department', e.target.value)}
            />
          </Field>

          <Field label="Category" htmlFor="cf-cat">
            <Select
              id="cf-cat"
              options={CATEGORIES}
              placeholder="Select category"
              value={draft.category}
              onChange={(e) => set('category', e.target.value)}
            />
          </Field>

          <Field
            label="Description"
            required
            error={errors.description}
            className="sm:col-span-2"
          >
            <RichTextEditor
              value={draft.description}
              onChange={(html) => set('description', html)}
              invalid={Boolean(errors.description)}
              placeholder="Describe the change, the systems involved, and the expected outcome."
            />
          </Field>

          <Field
            label="Planned Start Date and Time"
            required
            error={errors.plannedStart}
            htmlFor="cf-start"
          >
            <TextInput
              id="cf-start"
              type="datetime-local"
              value={draft.plannedStart}
              aria-invalid={Boolean(errors.plannedStart)}
              onChange={(e) => set('plannedStart', e.target.value)}
            />
          </Field>

          <Field
            label="Planned End Date and Time"
            required
            error={errors.plannedEnd}
            htmlFor="cf-end"
          >
            <TextInput
              id="cf-end"
              type="datetime-local"
              value={draft.plannedEnd}
              aria-invalid={Boolean(errors.plannedEnd)}
              onChange={(e) => set('plannedEnd', e.target.value)}
            />
          </Field>

          <Field label="Maintenance Window" htmlFor="cf-window">
            <Select
              id="cf-window"
              options={MAINTENANCE_WINDOWS}
              placeholder="Select window"
              value={draft.maintenanceWindow}
              onChange={(e) => set('maintenanceWindow', e.target.value)}
            />
          </Field>

          <Field label="Associate Assets" className="sm:col-span-2">
            <AssetPicker
              assets={assets}
              value={draft.assetIds}
              onChange={(ids) => set('assetIds', ids)}
            />
          </Field>

          {draft.changeType === 'Emergency' && (
            <Field
              label="Emergency Justification"
              required
              error={errors.emergencyJustification}
              htmlFor="cf-ej"
              className="sm:col-span-2"
            >
              <TextArea
                id="cf-ej"
                value={draft.emergencyJustification}
                aria-invalid={Boolean(errors.emergencyJustification)}
                onChange={(e) => set('emergencyJustification', e.target.value)}
                placeholder="Why this cannot wait for the normal change process."
              />
            </Field>
          )}

          <Field label="Attachments" className="sm:col-span-2">
            <AttachmentZone
              attachments={attachments}
              onChange={setAttachments}
              onReject={(m) => toast.error(m)}
            />
          </Field>
        </div>
      </Panel>

      <Panel title="Planning">
        <div className="grid gap-3.5 sm:grid-cols-2">
          {PLANNING_FIELDS.map((f) => (
            <Field key={f.key} label={f.label} hint={f.hint} htmlFor={`pl-${f.key}`}>
              <TextArea
                id={`pl-${f.key}`}
                rows={f.key === 'implementationSteps' ? 5 : 3}
                value={draft.planning[f.key]}
                onChange={(e) => setPlanning(f.key, e.target.value)}
              />
            </Field>
          ))}
        </div>
      </Panel>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button
          variant="ghost"
          onClick={() => {
            clearSessionDraft();
            navigate(isEdit && editing ? `/itsm/changes/${editing.id}` : '/itsm/changes');
          }}
        >
          Cancel
        </Button>
        <Button onClick={() => persist('Draft', 'Saved as draft')}>Save as Draft</Button>
        <Button variant="primary" onClick={onSubmit}>
          {isEdit ? 'Save changes' : 'Submit'}
        </Button>
      </div>

      <p className="text-right text-[11px] text-slate-500">
        {changes.length} changes in this workspace.
      </p>
    </div>
  );
}
