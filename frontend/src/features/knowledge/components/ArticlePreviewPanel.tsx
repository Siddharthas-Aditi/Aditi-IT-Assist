/** Read-only rendering of a structured article (how a consumer would see it). */

import type { ArticleDetail, Step } from '@/types/knowledge';

function ListSection({ title, items }: { title: string; items: string[] }) {
  if (!items?.length) return null;
  return (
    <section>
      <h4 className="mb-1 text-sm font-semibold text-foreground">{title}</h4>
      <ul className="list-disc space-y-0.5 pl-5 text-sm text-muted-foreground">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function StepSection({ title, steps }: { title: string; steps: Step[] }) {
  if (!steps?.length) return null;
  return (
    <section>
      <h4 className="mb-1 text-sm font-semibold text-foreground">{title}</h4>
      <ol className="space-y-1.5 text-sm">
        {steps.map((s) => (
          <li key={s.step_number} className="flex gap-2">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
              {s.step_number}
            </span>
            <span>
              <span className="text-foreground">{s.instruction}</span>
              {s.details && <span className="block text-xs text-muted-foreground">{s.details}</span>}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function ArticlePreviewPanel({ article }: { article: ArticleDetail }) {
  return (
    <article className="space-y-5">
      <header>
        <h2 className="text-xl font-bold text-foreground">{article.title}</h2>
        {article.short_summary && (
          <p className="mt-1 text-sm text-muted-foreground">{article.short_summary}</p>
        )}
      </header>

      {article.content && (
        <section>
          <h4 className="mb-1 text-sm font-semibold text-foreground">Overview</h4>
          <p className="whitespace-pre-wrap text-sm text-muted-foreground">{article.content}</p>
        </section>
      )}

      <ListSection title="Symptoms" items={article.symptoms} />
      <ListSection title="Probable Causes" items={article.probable_causes} />
      <ListSection title="Prerequisites" items={article.prerequisites} />
      <StepSection title="Troubleshooting Steps" steps={article.troubleshooting_steps} />
      <StepSection title="Resolution Steps" steps={article.resolution_steps} />
      <StepSection title="Validation Steps" steps={article.validation_steps} />

      {(article.escalation_criteria || article.escalation_target_team) && (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-3">
          <h4 className="mb-1 text-sm font-semibold text-amber-800">Escalation</h4>
          {article.escalation_criteria && (
            <p className="text-sm text-amber-800">{article.escalation_criteria}</p>
          )}
          {article.escalation_target_team && (
            <p className="mt-1 text-xs text-amber-700">
              Target team: {article.escalation_target_team}
            </p>
          )}
        </section>
      )}

      {article.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {article.tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
            >
              #{tag}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}
