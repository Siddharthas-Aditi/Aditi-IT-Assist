import { Bot, User, AlertCircle, Shield, ExternalLink, CheckCircle2 } from 'lucide-react';
import { clsx } from 'clsx';
import type { ChatMessage } from '../../types';
import { StepTimeline, type TimelineStep } from '../../components/ui/StepTimeline';
import { Badge } from '../../components/ui/Badge';

interface ChatBubbleProps {
  message: ChatMessage;
  index: number;
}

/** Format category slug into a readable label, e.g. "email/outlook" → "Email / Outlook" */
function formatCategory(category: string): string {
  return category
    .split('/')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(' / ');
}

/**
 * Render LLM prose content with basic markdown-style formatting.
 * Handles **bold**, numbered lists, and line breaks.
 */
function ProseContent({ text }: { text: string }) {
  const lines = text.split('\n');
  return (
    <div className="space-y-1.5">
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-1" />;

        // Detect numbered list items like "1. Step text" or "**Step 1**: text"
        const numberedMatch = line.match(/^\*?\*?(?:Step\s+)?(\d+)\*?\*?[:.]\s*(.+)/i);
        if (numberedMatch) {
          const [, num, content] = numberedMatch;
          return (
            <div key={i} className="flex gap-2.5 items-start">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-[10px] font-bold mt-0.5">
                {num}
              </span>
              <span className="text-sm leading-relaxed flex-1"
                dangerouslySetInnerHTML={{ __html: renderInlineBold(content) }}
              />
            </div>
          );
        }

        // Italic details (lines starting with _ or indented with _)
        if (line.trim().startsWith('_') && line.trim().endsWith('_')) {
          return (
            <p key={i} className="text-xs text-muted-foreground italic pl-7">
              {line.trim().slice(1, -1)}
            </p>
          );
        }

        return (
          <p key={i} className="text-sm leading-relaxed"
            dangerouslySetInnerHTML={{ __html: renderInlineBold(line) }}
          />
        );
      })}
    </div>
  );
}

function renderInlineBold(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

export function ChatBubble({ message, index }: ChatBubbleProps) {
  const isUser = message.role === 'user';

  // Only render the StepTimeline when there are multiple discrete steps
  // (LLM prose comes back as a single step — render as formatted prose instead)
  const hasMultipleSteps = (message.steps?.length ?? 0) > 1;
  const timelineSteps: TimelineStep[] | undefined = hasMultipleSteps
    ? message.steps?.map((step, idx) => ({
        stepNumber: step.step_number,
        instruction: step.instruction,
        details: step.details,
        status: idx === 0 ? 'active' : 'pending',
      }))
    : undefined;

  // Single-step LLM prose — render with formatting
  const proseSingleStep =
    !hasMultipleSteps && message.steps?.length === 1 ? message.steps[0].instruction : null;

  return (
    <div
      className={clsx('flex gap-3 animate-slide-up', isUser ? 'justify-end' : 'justify-start')}
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {/* Bot avatar */}
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl gradient-brand shadow-sm">
          <Bot className="h-4 w-4 text-white" />
        </div>
      )}

      {/* Bubble */}
      <div
        className={clsx(
          'max-w-[78%] rounded-2xl px-4 py-3 shadow-sm',
          isUser
            ? 'rounded-br-md gradient-brand text-white'
            : 'rounded-bl-md bg-card border border-border text-card-foreground'
        )}
      >
        {/* Message content — use prose formatter for bot, plain for user */}
        {isUser || !proseSingleStep ? (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
        ) : (
          <ProseContent text={proseSingleStep} />
        )}

        {/* Metadata row — category badge + confidence */}
        {!isUser && message.confidence !== undefined && message.confidence > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {message.category && (
              <Badge variant="primary" className="text-[10px]">
                {formatCategory(message.category)}
              </Badge>
            )}
            <Badge
              variant={message.confidence >= 0.8 ? 'success' : 'warning'}
              className="text-[10px]"
            >
              <Shield className="mr-1 h-2.5 w-2.5" />
              {Math.round(message.confidence * 100)}% confidence
            </Badge>
          </div>
        )}

        {/* Multi-step timeline (direct/fallback path) */}
        {timelineSteps && timelineSteps.length > 0 && (
          <div className="mt-4 rounded-xl bg-background/60 border border-border/50 p-4">
            <div className="mb-3 flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Resolution Steps
              </p>
            </div>
            <StepTimeline steps={timelineSteps} />
          </div>
        )}

        {/* Escalation indicator */}
        {!isUser && message.requiresEscalation && (
          <div className="mt-3 flex items-center gap-1.5 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 px-3 py-2">
            <AlertCircle className="h-3.5 w-3.5 shrink-0 text-amber-600" />
            <span className="text-xs text-amber-700 dark:text-amber-400">
              This issue may require a human IT specialist
            </span>
            <a
              href="#"
              className="ml-auto flex items-center gap-0.5 text-xs text-amber-600 underline hover:no-underline"
            >
              Raise ticket <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        )}
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-muted">
          <User className="h-4 w-4 text-muted-foreground" />
        </div>
      )}
    </div>
  );
}
