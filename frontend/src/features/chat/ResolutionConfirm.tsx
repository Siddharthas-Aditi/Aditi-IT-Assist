import { CheckCircle2, XCircle, ArrowRight } from 'lucide-react';

interface ResolutionConfirmProps {
  onResolved: () => void;
  onNotResolved: () => void;
  disabled?: boolean;
}

/**
 * Resolution confirmation buttons shown after troubleshooting steps.
 * Allows the user to indicate whether their issue was resolved or not.
 */
export function ResolutionConfirm({ onResolved, onNotResolved, disabled }: ResolutionConfirmProps) {
  return (
    <div className="flex flex-col gap-2 mt-3 ml-12">
      <p className="text-xs text-muted-foreground font-medium">Did this resolve your issue?</p>
      <div className="flex gap-2">
        <button
          onClick={onResolved}
          disabled={disabled}
          className="flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700 transition-all hover:bg-emerald-100 hover:border-emerald-300 active:scale-95 disabled:opacity-40 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400 dark:hover:bg-emerald-900/50"
        >
          <CheckCircle2 className="h-3.5 w-3.5" />
          Yes, it's fixed!
        </button>
        <button
          onClick={onNotResolved}
          disabled={disabled}
          className="flex items-center gap-1.5 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-xs font-medium text-orange-700 transition-all hover:bg-orange-100 hover:border-orange-300 active:scale-95 disabled:opacity-40 dark:border-orange-800 dark:bg-orange-950/50 dark:text-orange-400 dark:hover:bg-orange-900/50"
        >
          <XCircle className="h-3.5 w-3.5" />
          Still having issues
        </button>
        <button
          onClick={onNotResolved}
          disabled={disabled}
          className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-xs font-medium text-muted-foreground transition-all hover:bg-accent hover:text-foreground active:scale-95 disabled:opacity-40"
        >
          <ArrowRight className="h-3.5 w-3.5" />
          Talk to live agent
        </button>
      </div>
    </div>
  );
}
