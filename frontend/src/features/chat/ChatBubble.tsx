import { Bot, User, AlertCircle, Shield } from 'lucide-react';
import { clsx } from 'clsx';
import type { ChatMessage } from '../../types';
import { StepTimeline, type TimelineStep } from '../../components/ui/StepTimeline';
import { Badge } from '../../components/ui/Badge';

interface ChatBubbleProps {
  message: ChatMessage;
  index: number;
}

export function ChatBubble({ message, index }: ChatBubbleProps) {
  const isUser = message.role === 'user';

  const timelineSteps: TimelineStep[] | undefined = message.steps?.map((step, idx) => ({
    stepNumber: step.step_number,
    instruction: step.instruction,
    details: step.details,
    status: idx === 0 ? 'active' : 'pending',
  }));

  return (
    <div
      className={clsx('flex gap-3 animate-slide-up', isUser ? 'justify-end' : 'justify-start')}
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {/* Avatar */}
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl gradient-brand shadow-sm">
          <Bot className="h-4 w-4 text-white" />
        </div>
      )}

      {/* Bubble */}
      <div
        className={clsx(
          'max-w-[75%] rounded-2xl px-4 py-3 shadow-sm',
          isUser
            ? 'rounded-br-md gradient-brand text-white'
            : 'rounded-bl-md bg-card border border-border text-card-foreground'
        )}
      >
        <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>

        {/* Metadata row */}
        {!isUser && message.confidence !== undefined && message.confidence > 0 && (
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            {message.category && (
              <Badge variant="primary">{message.category}</Badge>
            )}
            <Badge variant={message.confidence >= 0.8 ? 'success' : 'warning'}>
              <Shield className="mr-1 h-3 w-3" />
              {Math.round(message.confidence * 100)}% confidence
            </Badge>
          </div>
        )}

        {/* Step Timeline */}
        {timelineSteps && timelineSteps.length > 0 && (
          <div className="mt-4 rounded-xl bg-background/60 border border-border/50 p-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Troubleshooting Steps
            </p>
            <StepTimeline steps={timelineSteps} />
          </div>
        )}

        {/* Escalation indicator */}
        {message.requiresEscalation && (
          <div className="mt-3 flex items-center gap-1.5 text-xs text-amber-600">
            <AlertCircle className="h-3.5 w-3.5" />
            <span>This issue may require human support</span>
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
