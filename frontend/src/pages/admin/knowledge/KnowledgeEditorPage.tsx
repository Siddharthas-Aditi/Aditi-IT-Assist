/** Structured article editor — create a draft or edit a non-published article. */

import { AlertTriangle, ArrowLeft, Eye, Save } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import {
  ARTICLE_TYPE_OPTIONS,
  AUDIENCE_OPTIONS,
  ArticlePreviewPanel,
  StepsEditor,
  TagsInput,
  useArticle,
  useCreateArticle,
  useOwnershipGroups,
  useUpdateArticle,
} from '@/features/knowledge';
import type {
  ArticleDetail,
  ArticleType,
  Audience,
  ArticleWritePayload,
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

function LinesInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-foreground">{label}</label>
      <textarea
        value={value.join('\n')}
        onChange={(e) => onChange(e.target.value.split('\n').map((l) => l.trimStart()).filter(Boolean))}
        rows={3}
        placeholder={placeholder ?? 'One item per line'}
        className="w-full rounded-lg border border-border px-2.5 py-2 text-sm outline-none focus:border-primary"
      />
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-foreground">{label}</label>
      {children}
    </div>
  );
}

const inputCls =
  'w-full rounded-lg border border-border px-2.5 py-2 text-sm outline-none focus:border-primary';

export function KnowledgeEditorPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();

  const { data: existing } = useArticle(id);
  const { data: groups } = useOwnershipGroups();
  const create = useCreateArticle();
  const update = useUpdateArticle(id ?? '');

  const [form, setForm] = useState<ArticleWritePayload>(EMPTY);
  const [showPreview, setShowPreview] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  // Client-side completeness warnings (server enforces at publish).
  const warnings = useMemo(() => {
    const w: string[] = [];
    if (!form.short_summary?.trim()) w.push('Add a short summary to improve retrieval.');
    if ((form.resolution_steps?.length ?? 0) === 0 && (form.troubleshooting_steps?.length ?? 0) === 0)
      w.push('Add resolution or troubleshooting steps so the answer is actionable.');
    if ((form.tags?.length ?? 0) === 0) w.push('Add at least one tag for retrieval filtering.');
    if (!form.ownership_group_id) w.push('Assign an ownership group before publishing.');
    return w;
  }, [form]);

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

  const pending = create.isPending || update.isPending;

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

      {warnings.length > 0 && !showPreview && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <p className="mb-1 flex items-center gap-1.5 text-sm font-medium text-amber-800">
            <AlertTriangle size={15} /> Content quality suggestions
          </p>
          <ul className="list-disc pl-6 text-sm text-amber-700">
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {showPreview ? (
        <div className="rounded-xl border border-border bg-white p-5">
          <ArticlePreviewPanel article={previewArticle} />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <Field label="Title *">
              <input
                value={form.title}
                onChange={(e) => set('title', e.target.value)}
                className={inputCls}
                placeholder="e.g. Outlook Not Receiving Email"
              />
            </Field>
            <Field label="Short summary">
              <textarea
                value={form.short_summary ?? ''}
                onChange={(e) => set('short_summary', e.target.value)}
                rows={2}
                className={inputCls}
                placeholder="One or two sentences describing the problem and fix."
              />
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
            />
            <LinesInput
              label="Probable causes"
              value={form.probable_causes ?? []}
              onChange={(v) => set('probable_causes', v)}
            />
            <LinesInput
              label="Prerequisites"
              value={form.prerequisites ?? []}
              onChange={(v) => set('prerequisites', v)}
            />

            <StepsEditor
              label="Troubleshooting steps"
              steps={(form.troubleshooting_steps ?? []) as Step[]}
              onChange={(s) => set('troubleshooting_steps', s)}
            />
            <StepsEditor
              label="Resolution steps"
              steps={(form.resolution_steps ?? []) as Step[]}
              onChange={(s) => set('resolution_steps', s)}
            />
            <StepsEditor
              label="Validation steps"
              steps={(form.validation_steps ?? []) as Step[]}
              onChange={(s) => set('validation_steps', s)}
            />

            <Field label="Escalation criteria">
              <textarea
                value={form.escalation_criteria ?? ''}
                onChange={(e) => set('escalation_criteria', e.target.value)}
                rows={2}
                className={inputCls}
                placeholder="When should this be escalated to a human?"
              />
            </Field>
            <Field label="Escalation target team">
              <input
                value={form.escalation_target_team ?? ''}
                onChange={(e) => set('escalation_target_team', e.target.value)}
                className={inputCls}
              />
            </Field>
          </div>

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
            <Field label="Category *">
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
              />
            </Field>
            <Field label="Product / system">
              <input
                value={form.product_or_system ?? ''}
                onChange={(e) => set('product_or_system', e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="Platform">
              <input
                value={form.platform ?? ''}
                onChange={(e) => set('platform', e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="Ownership group">
              <select
                value={form.ownership_group_id ?? ''}
                onChange={(e) => set('ownership_group_id', e.target.value)}
                className={inputCls}
              >
                <option value="">— Select —</option>
                {(groups ?? []).map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.display_name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Tags">
              <TagsInput values={form.tags ?? []} onChange={(v) => set('tags', v)} />
            </Field>
            <Field label="Keywords">
              <TagsInput values={form.keywords ?? []} onChange={(v) => set('keywords', v)} />
            </Field>
            <Field label="Citation label">
              <input
                value={form.citation_label ?? ''}
                onChange={(e) => set('citation_label', e.target.value)}
                className={inputCls}
                placeholder="Shown next to AI answers"
              />
            </Field>
            <Field label="Review interval (days)">
              <input
                type="number"
                value={form.review_interval_days ?? 180}
                onChange={(e) => set('review_interval_days', Number(e.target.value))}
                className={inputCls}
              />
            </Field>
          </div>
        </div>
      )}
    </div>
  );
}
