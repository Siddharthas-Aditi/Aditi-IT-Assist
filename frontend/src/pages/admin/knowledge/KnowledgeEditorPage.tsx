/** Structured article editor — create from template or blank, or edit a non-published article. */

import { ArrowLeft, Eye, Save } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import {
  ARTICLE_TYPE_OPTIONS,
  AUDIENCE_OPTIONS,
  ArticlePreviewPanel,
  AuthorWarnings,
  CompletenessScore,
  DuplicateHints,
  FieldWarning,
  StepsEditor,
  TagsInput,
  TemplateSelector,
  useArticle,
  useAuthorWarnings,
  useCompleteness,
  useCreateArticle,
  useCreateFromTemplate,
  useCreateOwnershipGroup,
  useDuplicateHints,
  useOwnershipGroups,
  useTemplates,
  useUpdateArticle,
} from '@/features/knowledge';
import type {
  ArticleDetail,
  ArticleTemplate,
  ArticleType,
  ArticleWritePayload,
  Audience,
  AuthorWarning,
  Step,
  VisibilityScope,
} from '@/types/knowledge';

const EMPTY: ArticleWritePayload = {
  title: '',
  short_summary: '',
  article_type: 'troubleshooting',
  audience: 'employee',
  visibility_scope: 'public_internal',
  category: '',
  subcategory: '',
  product_or_system: '',
  platform: '',
  issue_type: '',
  severity_hint: '',
  tags: [],
  keywords: [],
  ownership_group_id: '',
  content: '',
  symptoms: [],
  probable_causes: [],
  prerequisites: [],
  troubleshooting_steps: [],
  resolution_steps: [],
  validation_steps: [],
  escalation_criteria: '',
  escalation_target_team: '',
  citation_label: '',
  review_interval_days: 180,
};

// ── Helpers ────────────────────────────────────────────────────────

function LinesInput({
  label,
  value,
  onChange,
  placeholder,
  warning,
}: {
  label: string;
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  warning?: AuthorWarning | null;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-foreground">{label}</label>
      <textarea
        value={value.join('\n')}
        onChange={(e) =>
          onChange(
            e.target.value
              .split('\n')
              .map((l) => l.trimStart())
              .filter(Boolean),
          )
        }
        rows={3}
        placeholder={placeholder ?? 'One item per line'}
        className={`w-full rounded-lg border px-2.5 py-2 text-sm outline-none focus:border-primary ${
          warning?.severity === 'error'
            ? 'border-red-300 bg-red-50/30'
            : warning?.severity === 'warning'
              ? 'border-amber-300'
              : 'border-border'
        }`}
      />
      {warning && (
        <p
          className={`mt-1 text-xs ${warning.severity === 'error' ? 'text-red-600' : 'text-amber-600'}`}
        >
          {warning.message}
        </p>
      )}
    </div>
  );
}

function Field({
  label,
  children,
  required,
}: {
  label: string;
  children: React.ReactNode;
  required?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-foreground">
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </label>
      {children}
    </div>
  );
}

const inputCls =
  'w-full rounded-lg border border-border px-2.5 py-2 text-sm outline-none focus:border-primary';
const inputErrCls =
  'w-full rounded-lg border border-red-300 bg-red-50/30 px-2.5 py-2 text-sm outline-none focus:border-red-500';

// ── Main component ─────────────────────────────────────────────────

export function KnowledgeEditorPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();

  const { data: existing } = useArticle(id);
  const { data: groups } = useOwnershipGroups();
  const { data: templates } = useTemplates();
  const create = useCreateArticle();
  const update = useUpdateArticle(id ?? '');
  const createFromTemplate = useCreateFromTemplate();
  const createGroup = useCreateOwnershipGroup();

  const [form, setForm] = useState<ArticleWritePayload>(EMPTY);
  const [showPreview, setShowPreview] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTemplatePicker, setShowTemplatePicker] = useState(!isEdit);
  // Inline ownership-group creation
  const [showCreateGroup, setShowCreateGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');

  // Server-side quality data (only for saved/existing articles)
  const { data: completenessReport } = useCompleteness(id);
  const { data: serverWarnings } = useAuthorWarnings(id);

  // Duplicate hints (triggered once title has ≥ 5 chars)
  const { data: duplicates, isFetching: dupFetching } = useDuplicateHints(form.title);

  // Load existing article into form
  useEffect(() => {
    if (existing) {
      setForm({
        ...EMPTY,
        ...existing,
        ownership_group_id: existing.ownership_group_id ?? '',
        tags: existing.tags ?? [],
        keywords: existing.keywords ?? [],
        symptoms: existing.symptoms ?? [],
        probable_causes: existing.probable_causes ?? [],
        prerequisites: existing.prerequisites ?? [],
        troubleshooting_steps: existing.troubleshooting_steps ?? [],
        resolution_steps: existing.resolution_steps ?? [],
        validation_steps: existing.validation_steps ?? [],
      });
    }
  }, [existing]);

  const set = <K extends keyof ArticleWritePayload>(key: K, value: ArticleWritePayload[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  // Client-side warnings (fast, no network round-trip; used before article is saved)
  const clientWarnings = useMemo<AuthorWarning[]>(() => {
    const w: AuthorWarning[] = [];
    if (!form.short_summary?.trim())
      w.push({ severity: 'error', field: 'short_summary', message: 'Short summary is required to publish.', guidance: 'Write 1–2 sentences describing the problem and solution.' });
    if ((form.resolution_steps?.length ?? 0) === 0 && (form.troubleshooting_steps?.length ?? 0) === 0 && !form.content?.trim())
      w.push({ severity: 'error', field: 'resolution_steps', message: 'Article has no actionable content.', guidance: 'Add resolution steps, troubleshooting steps, or body content.' });
    if ((form.tags?.length ?? 0) === 0)
      w.push({ severity: 'error', field: 'tags', message: 'At least one tag is required.', guidance: 'Tags are used in the AI retrieval pipeline.' });
    if (!form.ownership_group_id)
      w.push({ severity: 'error', field: 'ownership_group_id', message: 'Ownership group must be assigned.', guidance: 'Assign the team responsible for this article.' });
    if (!form.citation_label?.trim())
      w.push({ severity: 'error', field: 'citation_label', message: 'Citation label is missing.', guidance: 'Shown next to AI-generated answers citing this article.' });
    if ((form.symptoms?.length ?? 0) === 0)
      w.push({ severity: 'warning', field: 'symptoms', message: 'No symptoms listed.', guidance: 'Helps the AI match this article to user issues.' });
    if (!form.escalation_criteria?.trim())
      w.push({ severity: 'warning', field: 'escalation_criteria', message: 'Escalation criteria not defined.', guidance: 'Specify when to escalate to a human agent.' });
    if ((form.validation_steps?.length ?? 0) === 0)
      w.push({ severity: 'warning', field: 'validation_steps', message: 'No validation steps.', guidance: "Tell users how to confirm the fix worked." });
    return w;
  }, [form]);

  // Prefer server warnings for saved articles (richer guidance), else use client-side
  const activeWarnings: AuthorWarning[] = serverWarnings ?? clientWarnings;

  // Template selection: create-from-template then redirect to the new article's editor
  const handleTemplateSelect = async (template: ArticleTemplate) => {
    setShowTemplatePicker(false);
    setError(null);
    try {
      const article = await createFromTemplate.mutateAsync({
        template_key: template.key,
        ownership_group_id: form.ownership_group_id || undefined,
      });
      navigate(`/dashboard/knowledge/${article.id}/edit`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create from template');
    }
  };

  const submit = async () => {
    setError(null);
    const payload: ArticleWritePayload = {
      ...form,
      ownership_group_id: form.ownership_group_id || null,
    };
    try {
      if (isEdit) {
        await update.mutateAsync(payload);
        navigate(`/dashboard/knowledge/${id}`);
      } else {
        const created = await create.mutateAsync(payload);
        navigate(`/dashboard/knowledge/${created.id}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
    }
  };

  const previewArticle = {
    ...(existing ?? ({} as ArticleDetail)),
    ...form,
    tags: form.tags ?? [],
  } as ArticleDetail;

  const pending = create.isPending || update.isPending || createFromTemplate.isPending;
  const errorWarnings = activeWarnings.filter((w) => w.severity === 'error');

  // Helper: get first warning matching a field
  const warnFor = (field: string): AuthorWarning | null =>
    activeWarnings.find((w) => w.field === field) ?? null;

  // Template picker (new article flow only)
  if (!isEdit && showTemplatePicker && templates && templates.length > 0) {
    return (
      <div className="p-6">
        <Link
          to="/dashboard/knowledge"
          className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft size={15} /> Back to Knowledge Base
        </Link>
        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
        <TemplateSelector
          templates={templates}
          onSelect={handleTemplateSelect}
          onDismiss={() => setShowTemplatePicker(false)}
        />
      </div>
    );
  }

  return (
    <div className="p-6">
      <Link
        to={isEdit ? `/dashboard/knowledge/${id}` : '/dashboard/knowledge'}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={15} /> Cancel
      </Link>

      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">
          {isEdit ? 'Edit Article' : 'New Article'}
        </h1>
        <div className="flex gap-2">
          {!isEdit && templates && templates.length > 0 && (
            <button
              onClick={() => setShowTemplatePicker(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-accent"
            >
              📋 Use template
            </button>
          )}
          <button
            onClick={() => setShowPreview((p) => !p)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-accent"
          >
            <Eye size={15} /> {showPreview ? 'Edit' : 'Preview'}
          </button>
          <button
            onClick={submit}
            disabled={pending || !form.title || !form.category}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
          >
            <Save size={15} /> {isEdit ? 'Save Changes' : 'Save Draft'}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {showPreview ? (
        <div className="rounded-xl border border-border bg-white p-5">
          <ArticlePreviewPanel article={previewArticle} />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          {/* ── Left: content fields ─────────────────────────── */}
          <div className="space-y-4 lg:col-span-2">
            {/* Title + duplicate hints */}
            <Field label="Title" required>
              <input
                value={form.title}
                onChange={(e) => set('title', e.target.value)}
                className={inputCls}
                placeholder="e.g. Outlook Not Receiving Email"
              />
              <DuplicateHints
                hints={(duplicates ?? []).filter((d) => !id || d.id !== id)}
                loading={dupFetching && form.title.length >= 5}
              />
            </Field>

            <Field label="Short summary">
              <textarea
                value={form.short_summary ?? ''}
                onChange={(e) => set('short_summary', e.target.value)}
                rows={2}
                className={
                  warnFor('short_summary')?.severity === 'error' ? inputErrCls : inputCls
                }
                placeholder="One or two sentences describing the problem and fix."
              />
              <FieldWarning warnings={activeWarnings} field="short_summary" />
            </Field>

            <Field label="Overview / body content">
              <textarea
                value={form.content ?? ''}
                onChange={(e) => set('content', e.target.value)}
                rows={4}
                className={inputCls}
                placeholder="Optional free-text context (markdown allowed)."
              />
            </Field>

            <LinesInput
              label="Symptoms"
              value={form.symptoms ?? []}
              onChange={(v) => set('symptoms', v)}
              placeholder="One symptom per line"
              warning={warnFor('symptoms')}
            />
            <LinesInput
              label="Probable causes"
              value={form.probable_causes ?? []}
              onChange={(v) => set('probable_causes', v)}
              placeholder="One cause per line"
              warning={warnFor('probable_causes')}
            />
            <LinesInput
              label="Prerequisites"
              value={form.prerequisites ?? []}
              onChange={(v) => set('prerequisites', v)}
              placeholder="e.g. User is signed in to Outlook"
            />

            <StepsEditor
              label="Troubleshooting steps"
              steps={(form.troubleshooting_steps ?? []) as Step[]}
              onChange={(s) => set('troubleshooting_steps', s)}
            />
            <div>
              <StepsEditor
                label="Resolution steps"
                steps={(form.resolution_steps ?? []) as Step[]}
                onChange={(s) => set('resolution_steps', s)}
              />
              <FieldWarning warnings={activeWarnings} field="resolution_steps" />
            </div>
            <div>
              <StepsEditor
                label="Validation steps"
                steps={(form.validation_steps ?? []) as Step[]}
                onChange={(s) => set('validation_steps', s)}
              />
              <FieldWarning warnings={activeWarnings} field="validation_steps" />
            </div>

            <Field label="Escalation criteria">
              <textarea
                value={form.escalation_criteria ?? ''}
                onChange={(e) => set('escalation_criteria', e.target.value)}
                rows={2}
                className={inputCls}
                placeholder="When should this be escalated to a human?"
              />
              <FieldWarning warnings={activeWarnings} field="escalation_criteria" />
            </Field>

            <Field label="Escalation target team">
              <input
                value={form.escalation_target_team ?? ''}
                onChange={(e) => set('escalation_target_team', e.target.value)}
                className={inputCls}
                placeholder="e.g. Exchange / M365 Admin Team"
              />
            </Field>
          </div>

          {/* ── Right: metadata + quality widgets ──────────────── */}
          <div className="space-y-4">
            <Field label="Article type">
              <select
                value={form.article_type}
                onChange={(e) => set('article_type', e.target.value as ArticleType)}
                className={inputCls}
              >
                {ARTICLE_TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Audience">
              <select
                value={form.audience}
                onChange={(e) => set('audience', e.target.value as Audience)}
                className={inputCls}
              >
                {AUDIENCE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Visibility scope">
              <select
                value={form.visibility_scope}
                onChange={(e) => set('visibility_scope', e.target.value as VisibilityScope)}
                className={inputCls}
              >
                <option value="public_internal">All authenticated</option>
                <option value="it_only">IT staff only</option>
                <option value="admin_only">Admins only</option>
              </select>
            </Field>

            <Field label="Category" required>
              <input
                value={form.category}
                onChange={(e) => set('category', e.target.value)}
                className={inputCls}
                placeholder="e.g. email/outlook"
              />
            </Field>

            <Field label="Subcategory">
              <input
                value={form.subcategory ?? ''}
                onChange={(e) => set('subcategory', e.target.value)}
                className={inputCls}
                placeholder="e.g. email-delivery"
              />
              <FieldWarning warnings={activeWarnings} field="subcategory" />
            </Field>

            <Field label="Product / system">
              <input
                value={form.product_or_system ?? ''}
                onChange={(e) => set('product_or_system', e.target.value)}
                className={inputCls}
                placeholder="e.g. Microsoft Outlook"
              />
              <FieldWarning warnings={activeWarnings} field="product_or_system" />
            </Field>

            <Field label="Platform">
              <input
                value={form.platform ?? ''}
                onChange={(e) => set('platform', e.target.value)}
                className={inputCls}
                placeholder="e.g. Windows"
              />
            </Field>

            <Field label="Ownership group">
              {showCreateGroup ? (
                <div className="space-y-2">
                  <input
                    autoFocus
                    value={newGroupName}
                    onChange={(e) => setNewGroupName(e.target.value)}
                    placeholder="Team name (e.g. Endpoint & Productivity)"
                    className={inputCls}
                  />
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={createGroup.isPending || !newGroupName.trim()}
                      onClick={async () => {
                        const slug = newGroupName
                          .trim()
                          .toLowerCase()
                          .replace(/[^a-z0-9]+/g, '-')
                          .replace(/(^-|-$)/g, '');
                        try {
                          const g = await createGroup.mutateAsync({
                            name: slug,
                            display_name: newGroupName.trim(),
                          });
                          set('ownership_group_id', g.id);
                          setNewGroupName('');
                          setShowCreateGroup(false);
                        } catch {
                          // error stays in createGroup.error
                        }
                      }}
                      className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                    >
                      {createGroup.isPending ? 'Creating…' : 'Create'}
                    </button>
                    <button
                      type="button"
                      onClick={() => { setShowCreateGroup(false); setNewGroupName(''); }}
                      className="rounded-md border border-border px-3 py-1 text-xs"
                    >
                      Cancel
                    </button>
                  </div>
                  {createGroup.isError && (
                    <p className="text-xs text-red-600">
                      {createGroup.error instanceof Error ? createGroup.error.message : 'Failed to create group'}
                    </p>
                  )}
                </div>
              ) : (
                <div className="flex gap-2">
                  <select
                    value={form.ownership_group_id ?? ''}
                    onChange={(e) => set('ownership_group_id', e.target.value)}
                    className={`flex-1 ${
                      warnFor('ownership_group_id')?.severity === 'error' ? inputErrCls : inputCls
                    }`}
                  >
                    <option value="">— Select —</option>
                    {(groups ?? []).map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.display_name}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => setShowCreateGroup(true)}
                    title="Create a new ownership group"
                    className="shrink-0 rounded-lg border border-border px-2 py-1 text-xs hover:bg-accent"
                  >
                    + New
                  </button>
                </div>
              )}
              <FieldWarning warnings={activeWarnings} field="ownership_group_id" />
            </Field>

            <div>
              <Field label="Tags">
                <TagsInput values={form.tags ?? []} onChange={(v) => set('tags', v)} />
              </Field>
              <FieldWarning warnings={activeWarnings} field="tags" />
            </div>

            <Field label="Keywords">
              <TagsInput values={form.keywords ?? []} onChange={(v) => set('keywords', v)} />
            </Field>

            <Field label="Citation label">
              <input
                value={form.citation_label ?? ''}
                onChange={(e) => set('citation_label', e.target.value)}
                className={
                  warnFor('citation_label')?.severity === 'error' ? inputErrCls : inputCls
                }
                placeholder="Shown next to AI answers"
              />
              <FieldWarning warnings={activeWarnings} field="citation_label" />
            </Field>

            <Field label="Review interval (days)">
              <input
                type="number"
                value={form.review_interval_days ?? 180}
                onChange={(e) => set('review_interval_days', Number(e.target.value))}
                className={inputCls}
                min={30}
                max={1095}
              />
            </Field>

            {/* Completeness score (server-side, only for saved articles) */}
            {completenessReport && <CompletenessScore report={completenessReport} />}

            {/* Author warnings collapsible panel */}
            {activeWarnings.length > 0 && <AuthorWarnings warnings={activeWarnings} />}

            {/* Publish-block summary for unsaved articles */}
            {!id && errorWarnings.length > 0 && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                <p className="mb-1 font-semibold">
                  {errorWarnings.length} issue{errorWarnings.length !== 1 ? 's' : ''} must be
                  resolved before publishing
                </p>
                <ul className="list-disc space-y-0.5 pl-4">
                  {errorWarnings.map((w, i) => (
                    <li key={i}>{w.message}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
