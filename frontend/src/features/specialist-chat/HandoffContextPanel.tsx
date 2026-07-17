/**
 * Specialist handoff context panel — the "warm handoff" the specialist reads
 * the moment they pick up an escalated chat.
 *
 * Renders the persisted escalation context (GET
 * `/specialist-queue/{ticketId}/handoff-view`) in the order a triaging
 * specialist needs it: Overview → AI Handoff Summary → Troubleshooting Already
 * Attempted → KB Signals / Knowledge Gaps → Full Conversation Transcript.
 *
 * The full transcript is **secondary** (collapsed by default in a `<details>`)
 * so the specialist can triage in seconds but still inspect every turn. We never
 * dump raw JSON — every section is structured + themed with Aditi tokens.
 */

import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  FileSearch,
  Globe,
  MessageSquareText,
  User,
  Wrench,
  XCircle,
} from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import {
  type SpecialistHandoffView,
  type StepAttempted,
  type TranscriptMessage,
  type TranscriptRole,
  type WebResearchFinding,
  queueApi,
} from '@/features/specialist-chat/api';

interface Props {
  ticketId: string;
}

const KB_GAP_LABELS: Record<string, string> = {
  no_matching_article: 'No matching article',
  article_suggested_but_unresolved: 'Article suggested but unresolved',
  specialist_only_resolution_needed: 'Specialist-only resolution',
  unclear_problem_statement: 'Unclear problem statement',
  repeated_escalation_pattern: 'Repeated escalation',
  missing_runbook: 'Missing runbook',
  policy_or_access_exception: 'Policy / access exception',
};

export function HandoffContextPanel({ ticketId }: Props) {
  const [view, setView] = useState<SpecialistHandoffView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    queueApi
      .getHandoffView(ticketId)
      .then((v) => active && setView(v))
      .catch((e) => active && setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [ticketId]);

  if (loading) {
    return (
      <Card className="mb-4">
        <p className="text-sm text-muted-foreground">Loading handoff context…</p>
      </Card>
    );
  }
  if (error || !view) {
    return (
      <Card className="mb-4">
        <p className="text-sm text-muted-foreground">
          Handoff context unavailable{error ? `: ${error}` : ''}.
        </p>
      </Card>
    );
  }

  return (
    <Card className="mb-4 p-0 overflow-hidden">
      {/* ── Overview ─────────────────────────────────────────────── */}
      <div className="gradient-brand-subtle border-b border-border px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              AI Handoff Summary
            </p>
            <h2 className="mt-1 text-base font-semibold text-foreground">
              {view.issue_summary}
            </h2>
          </div>
          <ResolutionStatusBadge status={view.ai_resolution_status} />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {view.category && <Badge variant="outline">{view.category}</Badge>}
          {view.subcategory && <Badge variant="outline">{view.subcategory}</Badge>}
          {view.affected_system && (
            <Badge variant="primary">{view.affected_system}</Badge>
          )}
          {view.urgency && <Badge variant="warning">{view.urgency} urgency</Badge>}
          {view.ai_confidence != null && (
            <Badge variant="default">
              AI confidence {Math.round(view.ai_confidence * 100)}%
            </Badge>
          )}
        </div>
        {!view.has_structured_context && (
          <p className="mt-3 text-xs text-muted-foreground">
            No structured escalation context was captured for this ticket — showing
            ticket fields only.
          </p>
        )}
      </div>

      <div className="space-y-5 px-5 py-4">
        {/* ── What the AI understood ─────────────────────────────── */}
        {(view.user_problem_statement || view.escalation_reason) && (
          <section>
            {view.user_problem_statement && (
              <div className="mb-2">
                <SectionLabel icon={<Bot size={14} />} text="What the employee asked" />
                <p className="mt-1 text-sm text-foreground">
                  {view.user_problem_statement}
                </p>
              </div>
            )}
            {view.escalation_reason && (
              <div>
                <SectionLabel
                  icon={<AlertTriangle size={14} />}
                  text="Why it was escalated"
                />
                <p className="mt-1 text-sm text-foreground">{view.escalation_reason}</p>
              </div>
            )}
          </section>
        )}

        {/* ── Troubleshooting already attempted ──────────────────── */}
        <section>
          <SectionLabel
            icon={<Wrench size={14} />}
            text={`Troubleshooting already attempted (${view.steps_attempted.length})`}
          />
          {view.steps_attempted.length === 0 ? (
            <p className="mt-1 text-sm text-muted-foreground">
              No AI troubleshooting steps were recorded.
            </p>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {view.steps_attempted.map((s, i) => (
                <StepRow key={i} step={s} />
              ))}
            </ul>
          )}
        </section>

        {/* ── KB signals / knowledge gaps ────────────────────────── */}
        <section>
          <SectionLabel
            icon={<FileSearch size={14} />}
            text="KB signals & knowledge gaps"
          />
          <div className="mt-2 space-y-2">
            {view.kb_gap_tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {view.kb_gap_tags.map((t) => (
                  <Badge key={t} variant="warning">
                    {KB_GAP_LABELS[t] ?? t}
                  </Badge>
                ))}
              </div>
            )}
            {view.kb_articles_referenced.length > 0 ? (
              <ul className="space-y-1 text-sm text-foreground">
                {view.kb_articles_referenced.map((a, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <span className="text-muted-foreground">•</span>
                    <span>{a.title}</span>
                    {a.relevance != null && (
                      <span className="text-xs text-muted-foreground">
                        ({Math.round(a.relevance * 100)}%)
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              view.kb_gap_tags.length === 0 && (
                <p className="text-sm text-muted-foreground">No KB signals recorded.</p>
              )
            )}
          </div>
        </section>

        {/* ── Web research (unverified, specialist-only review) ──── */}
        {view.web_research_findings && view.web_research_findings.length > 0 && (
          <details className="group rounded-lg border border-border">
            <summary className="flex cursor-pointer items-center justify-between px-3 py-2 text-sm font-medium text-foreground">
              <span className="flex items-center gap-2">
                <Globe size={14} />
                Web research (for your review) ({view.web_research_findings.length})
              </span>
              <ChevronDown
                size={16}
                className="text-muted-foreground transition-transform group-open:rotate-180"
              />
            </summary>
            <div className="space-y-2 border-t border-border px-3 py-3">
              <p className="text-xs text-muted-foreground">
                These are unverified external sources the AI found while researching this
                issue — not KB-approved guidance. Review before sharing with the employee.
              </p>
              <ul className="space-y-2">
                {view.web_research_findings.map((finding, i) => (
                  <WebResearchFindingRow key={`${finding.url}-${i}`} finding={finding} />
                ))}
              </ul>
            </div>
          </details>
        )}

        {/* ── Full transcript (secondary, collapsible) ───────────── */}
        {view.transcript && view.transcript.messages.length > 0 && (
          <details className="group rounded-lg border border-border">
            <summary className="flex cursor-pointer items-center justify-between px-3 py-2 text-sm font-medium text-foreground">
              <span className="flex items-center gap-2">
                <MessageSquareText size={14} />
                Full conversation transcript ({view.transcript.message_count} messages)
              </span>
              <ChevronDown
                size={16}
                className="text-muted-foreground transition-transform group-open:rotate-180"
              />
            </summary>
            <div className="max-h-80 space-y-2 overflow-y-auto border-t border-border px-3 py-3">
              {view.transcript.messages.map((m) => (
                <TranscriptBubble key={m.seq} message={m} />
              ))}
            </div>
          </details>
        )}
      </div>
    </Card>
  );
}

function SectionLabel({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
      {icon}
      {text}
    </div>
  );
}

function ResolutionStatusBadge({ status }: { status: string }) {
  const variant =
    status === 'user_requested_human'
      ? 'primary'
      : status === 'partially_resolved'
        ? 'warning'
        : 'destructive';
  const label = status.replace(/_/g, ' ');
  return <Badge variant={variant}>{label}</Badge>;
}

function StepRow({ step }: { step: StepAttempted }) {
  const { icon, color } = stepOutcomeStyle(step.outcome);
  return (
    <li className="flex items-start gap-2 text-sm text-foreground">
      <span className={`mt-0.5 ${color}`}>{icon}</span>
      <span>
        {step.instruction}
        {step.source_kb_title && (
          <span className="ml-1 text-xs text-muted-foreground">
            ({step.source_kb_title})
          </span>
        )}
      </span>
    </li>
  );
}

const TRUST_TIER_LABELS: Record<string, string> = {
  official: 'Official',
  vendor: 'Vendor',
  trusted_community: 'Community',
  general_blog: 'Blog',
};

function trustTierBadgeVariant(tier: string): 'success' | 'primary' | 'warning' | 'outline' {
  switch (tier) {
    case 'official':
      return 'success';
    case 'vendor':
      return 'primary';
    case 'trusted_community':
      return 'warning';
    default:
      return 'outline';
  }
}

/** Best-effort hostname for display; falls back to the raw URL if unparsable. */
function sourceDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/**
 * Returns the URL only if it is a safe, absolute http(s) URL — otherwise null.
 *
 * `finding.url` comes from external web-search results and is attacker-influenceable
 * (e.g. `javascript:`, `data:`, `vbscript:` schemes). Rendering it directly as an
 * anchor `href` would let a malicious search result execute script when a specialist
 * clicks the link. We only ever render a clickable link for a verified http(s) URL.
 */
function safeHttpUrl(raw: string): string | null {
  try {
    const u = new URL(raw);
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : null;
  } catch {
    return null;
  }
}

function WebResearchFindingRow({ finding }: { finding: WebResearchFinding }) {
  const safeUrl = safeHttpUrl(finding.url);
  return (
    <li className="rounded-md border border-border/60 px-3 py-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        {safeUrl ? (
          <a
            href={safeUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium text-primary underline-offset-2 hover:underline"
          >
            {finding.title}
          </a>
        ) : (
          <span className="text-sm font-medium text-foreground">{finding.title}</span>
        )}
        <Badge variant={trustTierBadgeVariant(finding.trust_tier)}>
          {TRUST_TIER_LABELS[finding.trust_tier] ?? finding.trust_tier}
        </Badge>
      </div>
      <p className="mt-0.5 text-xs text-muted-foreground">{sourceDomain(finding.url)}</p>
      {finding.snippet && (
        <p className="mt-1 text-xs text-foreground">{finding.snippet}</p>
      )}
    </li>
  );
}

function stepOutcomeStyle(outcome: StepAttempted['outcome']) {
  switch (outcome) {
    case 'worked':
      return { icon: <CheckCircle2 size={14} />, color: 'text-emerald-600' };
    case 'failed':
      return { icon: <XCircle size={14} />, color: 'text-red-600' };
    case 'skipped':
      return { icon: <CircleDashed size={14} />, color: 'text-muted-foreground' };
    default:
      return { icon: <CircleDashed size={14} />, color: 'text-muted-foreground' };
  }
}

/** Role-distinct transcript bubble: employee, AI, system, specialist. */
function TranscriptBubble({ message }: { message: TranscriptMessage }) {
  const { label, icon, bubble, align } = roleStyle(message.role);
  if (message.role === 'system') {
    return (
      <div className="py-1 text-center text-xs italic text-muted-foreground">
        {message.content}
      </div>
    );
  }
  return (
    <div className={`flex ${align}`}>
      <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${bubble}`}>
        <div className="mb-0.5 flex items-center gap-1 text-[11px] font-medium opacity-80">
          {icon}
          {label}
        </div>
        <div className="whitespace-pre-wrap">{message.content}</div>
      </div>
    </div>
  );
}

function roleStyle(role: TranscriptRole) {
  switch (role) {
    case 'employee':
      return {
        label: 'Employee',
        icon: <User size={11} />,
        bubble: 'bg-secondary text-secondary-foreground',
        align: 'justify-start',
      };
    case 'assistant':
      return {
        label: 'AI Assistant',
        icon: <Bot size={11} />,
        bubble: 'bg-primary/10 text-foreground border border-primary/20',
        align: 'justify-start',
      };
    case 'specialist':
      return {
        label: 'Specialist',
        icon: <User size={11} />,
        bubble: 'bg-primary text-primary-foreground',
        align: 'justify-end',
      };
    default:
      return {
        label: 'System',
        icon: <CircleDashed size={11} />,
        bubble: 'bg-muted text-muted-foreground',
        align: 'justify-center',
      };
  }
}
