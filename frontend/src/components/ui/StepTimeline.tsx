import { clsx } from 'clsx';
import { CheckCircle2, Circle, Loader2 } from 'lucide-react';

export interface TimelineStep {
  stepNumber: number;
  instruction: string;
  details?: string;
  status: 'completed' | 'active' | 'pending';
}

interface StepTimelineProps {
  steps: TimelineStep[];
  className?: string;
}

export function StepTimeline({ steps, className }: StepTimelineProps) {
  return (
    <div className={clsx('space-y-0', className)}>
      {steps.map((step, index) => {
        const isLast = index === steps.length - 1;
        return (
          <div key={step.stepNumber} className="flex gap-3 animate-slide-up" style={{ animationDelay: `${index * 80}ms` }}>
            {/* Timeline connector */}
            <div className="flex flex-col items-center">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 transition-colors duration-300"
                style={
                  step.status === 'completed'
                    ? { borderColor: 'hsl(var(--success))', backgroundColor: 'hsl(var(--success) / 0.1)' }
                    : step.status === 'active'
                    ? { borderColor: 'hsl(var(--primary))', backgroundColor: 'hsl(var(--primary) / 0.1)' }
                    : { borderColor: 'hsl(var(--border))' }
                }
              >
                {step.status === 'completed' && <CheckCircle2 className="h-4 w-4 text-[hsl(var(--success))]" />}
                {step.status === 'active' && <Loader2 className="h-4 w-4 text-primary animate-spin" />}
                {step.status === 'pending' && <Circle className="h-3 w-3 text-muted-foreground/50" />}
              </div>
              {!isLast && (
                <div className={clsx(
                  'w-0.5 flex-1 min-h-[24px] transition-colors',
                  step.status === 'completed' ? 'bg-[hsl(var(--success)/0.4)]' : 'bg-border'
                )} />
              )}
            </div>

            {/* Step content */}
            <div className={clsx('pb-5', isLast && 'pb-0')}>
              <p className={clsx(
                'text-sm font-medium leading-tight',
                step.status === 'completed' && 'text-[hsl(var(--success))]',
                step.status === 'active' && 'text-primary',
                step.status === 'pending' && 'text-muted-foreground'
              )}>
                Step {step.stepNumber}: {step.instruction}
              </p>
              {step.details && (
                <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                  {step.details}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
