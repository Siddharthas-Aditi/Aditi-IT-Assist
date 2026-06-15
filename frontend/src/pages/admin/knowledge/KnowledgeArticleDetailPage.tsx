/** Knowledge article detail — content, retrieval preview, review, versions. */

import { ArrowLeft, History, Pencil, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import {
  ArticleMetadataPanel,
  ArticlePreviewPanel,
  ArticleStatusBadge,
  LifecycleActions,
  Modal,
  RetrievalPreviewPanel,
  useArticle,
  useDeleteArticle,
  useFeedback,
  useReviewNotes,
} from '@/features/knowledge';
import { hasPermission, P } from '@/lib/permissions';
import { useAuthStore } from '@/stores/auth-store';

type Tab = 'content' | 'retrieval' | 'review' | 'feedback';

const TABS: { key: Tab; label: string }[] = [
  { key: 'content', label: 'Content' },
  { key: 'retrieval', label: 'Retrieval Preview' },
  { key: 'review', label: 'Review Notes' },
  { key: 'feedback', label: 'Feedback' },
];

export function KnowledgeArticleDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const { data: article, isLoading, isError } = useArticle(id);
  const { data: reviewNotes } = useReviewNotes(id);
  const { data: feedback } = useFeedback(id);
  const deleteArticle = useDeleteArticle();
  const [tab, setTab] = useState<Tab>('content');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  if (isLoading) return <div className="p-6 text-muted-foreground">Loading article…</div>;
  if (isError || !article)
    return <div className="p-6 text-red-600">Article not found.</div>;

  const canEdit = hasPermission(user, P.KNOWLEDGE_UPDATE_OWN);
  const canDelete = hasPermission(user, P.KNOWLEDGE_DELETE);

  const handleDelete = async () => {
    setDeleteError(null);
    try {
      await deleteArticle.mutateAsync(article.id);
      navigate('/dashboard/knowledge');
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : 'Delete failed');
    }
  };

  return (
    <div className="p-6">
      <Link
        to="/dashboard/knowledge"
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={15} /> Back to articles
      </Link>

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-gray-900">{article.title}</h1>
            <ArticleStatusBadge status={article.status} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            v{article.version} · {article.slug}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to={`/dashboard/knowledge/${article.id}/versions`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent"
          >
            <History size={15} /> History
          </Link>
          {canEdit && article.status !== 'published' && (
            <Link
              to={`/dashboard/knowledge/${article.id}/edit`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent"
            >
              <Pencil size={15} /> Edit
            </Link>
          )}
          {canDelete && (
            <button
              onClick={() => { setShowDeleteConfirm(true); setDeleteError(null); }}
              className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50"
            >
              <Trash2 size={15} /> Delete
            </button>
          )}
        </div>
      </div>

      <div className="mb-5 rounded-xl border border-border bg-card p-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Lifecycle
        </h3>
        {article.status === 'approved' && !article.ownership_group_id && (
          <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            <span className="mt-0.5 shrink-0">⚠️</span>
            <span>
              This article needs an <strong>ownership group</strong> before it can be published.{' '}
              {canEdit && (
                <Link
                  to={`/dashboard/knowledge/${article.id}/edit`}
                  className="font-medium underline hover:text-amber-900"
                >
                  Edit article to assign one →
                </Link>
              )}
            </span>
          </div>
        )}
        <LifecycleActions article={article} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="mb-4 flex gap-1 border-b border-border">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`border-b-2 px-3 py-2 text-sm font-medium ${
                  tab === t.key
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'content' && (
            <div className="rounded-xl border border-border bg-white p-5">
              <ArticlePreviewPanel article={article} />
            </div>
          )}
          {tab === 'retrieval' && <RetrievalPreviewPanel articleId={article.id} />}
          {tab === 'review' && (
            <div className="space-y-2">
              {(reviewNotes ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No review notes yet.</p>
              ) : (
                reviewNotes!.map((n) => (
                  <div key={n.id} className="rounded-lg border border-border bg-white p-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium capitalize text-foreground">
                        {n.decision.replace('_', ' ')}
                      </span>
                      <span className="text-muted-foreground">
                        {new Date(n.created_at).toLocaleString()}
                      </span>
                    </div>
                    {n.note && <p className="mt-1 text-sm text-muted-foreground">{n.note}</p>}
                    {n.from_status && n.to_status && n.from_status !== n.to_status && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {n.from_status} → {n.to_status}
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
          {tab === 'feedback' && (
            <div className="space-y-2">
              {(feedback ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No feedback yet.</p>
              ) : (
                feedback!.map((f) => (
                  <div key={f.id} className="rounded-lg border border-border bg-white p-3 text-sm">
                    <div className="flex items-center gap-2">
                      <span
                        className={
                          f.was_helpful
                            ? 'text-emerald-600'
                            : f.was_helpful === false
                              ? 'text-red-600'
                              : 'text-muted-foreground'
                        }
                      >
                        {f.was_helpful ? '👍 Helpful' : f.was_helpful === false ? '👎 Not helpful' : '—'}
                      </span>
                      {f.rating != null && (
                        <span className="text-muted-foreground">{f.rating}/5</span>
                      )}
                      <span className="ml-auto text-xs text-muted-foreground">{f.source}</span>
                    </div>
                    {f.comment && <p className="mt-1 text-muted-foreground">{f.comment}</p>}
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        <aside>
          <ArticleMetadataPanel article={article} />
        </aside>
      </div>

      {/* Delete confirmation modal */}
      <Modal
        open={showDeleteConfirm}
        title="Delete article"
        onClose={() => setShowDeleteConfirm(false)}
        footer={
          <>
            <button
              onClick={() => setShowDeleteConfirm(false)}
              className="rounded-lg border border-border px-3 py-1.5 text-sm"
            >
              Cancel
            </button>
            <button
              onClick={handleDelete}
              disabled={deleteArticle.isPending}
              className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {deleteArticle.isPending ? 'Deleting…' : 'Delete permanently'}
            </button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">
          Are you sure you want to permanently delete{' '}
          <strong className="text-foreground">"{article.title}"</strong>?
          {article.status === 'published' && (
            <> This article is currently <strong>published</strong> and will be removed from the retrieval index immediately.</>
          )}
          {' '}This action cannot be undone.
        </p>
        {deleteError && <p className="mt-2 text-xs text-red-600">{deleteError}</p>}
      </Modal>
    </div>
  );
}
