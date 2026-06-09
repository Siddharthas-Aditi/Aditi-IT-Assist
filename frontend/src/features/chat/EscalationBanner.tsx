import { PhoneCall, ArrowRight } from 'lucide-react';

export function EscalationBanner() {
  return (
    <div className="animate-scale-in rounded-xl border border-amber-200 bg-amber-50/80 p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-100">
          <PhoneCall className="h-4 w-4 text-amber-700" />
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-amber-900">
            Escalation Available
          </h4>
          <p className="mt-0.5 text-xs text-amber-700 leading-relaxed">
            This issue may need human assistance. Would you like me to create a
            support ticket or connect you with an IT specialist?
          </p>
          <div className="mt-3 flex gap-2">
            <button className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-amber-700">
              Create Ticket
              <ArrowRight className="h-3 w-3" />
            </button>
            <button className="inline-flex items-center rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-50">
              Continue with AI
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
