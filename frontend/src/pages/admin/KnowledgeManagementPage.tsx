/** Knowledge management list page — admin/lead control of KB articles. */

import { BarChart3, BookOpen, Database, FolderTree, ListChecks, Plus, Upload } from 'lucide-react';
import { useState } from 'react';
import { Link, NavLink } from 'react-router-dom';

import { EmptyState } from '@/components/ui';
import {
  ArticleStatusBadge,
  KnowledgeFilters,
  StaleArticleWarning,
  useArticles,
} from '@/features/knowledge';
import { hasPermission, P } from '@/lib/permissions';
import { useAuthStore } from '@/stores/auth-store';
import type { ArticleFilters } from '@/types/knowledge';

const SUB_NAV = [
  { to: '/dashboard/knowledge', label: 'Articles', icon: BookOpen, end: true },
  { to: '/dashboard/knowledge/review', label: 'Review Queue', icon: ListChecks },
  { to: '/dashboard/knowledge/taxonomy', label: 'Taxonomy', icon: FolderTree },
  { to: '/dashboard/knowledge/indexing', label: 'Indexing', icon: Database },
  { to: '/dashboard/knowledge/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/dashboard/knowledge/upload', label: 'Upload', icon: Upload },
];

export function KnowledgeManagementPage() {
  const user = useAuthStore((s) => s.user);
  const [filters, setFilters] = useState<ArticleFilters>({ limit: 25, offset: 0 });
  const { data, isLoading, isError } = useArticles(filters);

  const canCreate = hasPermission(user, P.KNOWLEDGE_CREATE);

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Knowledge Base</h1>
          <p className="mt-1 text-sm text-gray-500">
            Author, govern, and publish AI-ready knowledge articles
          </p>
        </div>
        {canCreate && (
          <Link
            to="/dashboard/knowledge/new"
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90"
          >
            <Plus size={16} /> New Article
          </Link>
        )}
      </div>

      <nav className="mb-5 flex gap-1 border-b border-border">
        {SUB_NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium ${
                isActive
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`
            }
          >
            <item.icon size={15} /> {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="mb-4">
        <KnowledgeFilters filters={filters} onChange={setFilters} />
      </div>

      {isLoading ? (
        <div className="py-16 text-center text-muted-foreground">Loading articles…</div>
      ) : isError ? (
        <div className="py-16 text-center text-red-600">Failed to load knowledge articles.</div>
      ) : !data || data.articles.length === 0 ? (
        <EmptyState
          icon={<BookOpen className="h-7 w-7 text-primary" />}
          title="No articles found"
          description="Adjust your filters, or create the first knowledge article for this domain."
          action={
            canCreate ? (
              <Link
                to="/dashboard/knowledge/new"
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white"
              >
                Create article
              </Link>
            ) : undefined
          }
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Title</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Category</th>
                <th className="px-4 py-2.5 font-medium">Audience</th>
                <th className="px-4 py-2.5 font-medium">Quality</th>
                <th className="px-4 py-2.5 font-medium">Used</th>
                <th className="px-4 py-2.5 font-medium">v</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.articles.map((a) => (
                <tr key={a.id} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5">
                    <Link
                      to={`/dashboard/knowledge/${a.id}`}
                      className="font-medium text-foreground hover:text-primary"
                    >
                      {a.title}
                    </Link>
                    {a.is_stale && (
                      <span className="ml-2 align-middle">
                        <StaleArticleWarning dueAt={a.next_review_due_at} compact />
                      </span>
                    )}
                    {a.short_summary && (
                      <p className="truncate text-xs text-muted-foreground">{a.short_summary}</p>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <ArticleStatusBadge status={a.status} />
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">{a.category}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{a.audience}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {a.quality_score != null ? a.quality_score.toFixed(2) : '—'}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">{a.usage_count}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{a.version}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total > 0 && (
        <p className="mt-3 text-xs text-muted-foreground">
          Showing {data.articles.length} of {data.total} articles
        </p>
      )}
    </div>
  );
}
