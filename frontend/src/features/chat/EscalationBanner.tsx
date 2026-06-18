import { PhoneCall, ArrowRight, CheckCircle, AlertTriangle, Loader2 } from 'lucide-react';

export type TeamsStatus = 'idle' | 'sending' | 'sent' | 'failed';

interface EscalationBannerProps {
  onEscalate?: () => void;
  onContinue?: () => void;
  teamsStatus?: TeamsStatus;
}

export function EscalationBanner({
  onEscalate,
  onContinue,
  teamsStatus = 'idle',
}: EscalationBannerProps) {
  return (
    <div className="animate-scale-in rounded-xl border border-amber-200 bg-amber-50/80 p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-100">
          <PhoneCall className="h-4 w-4 text-amber-700" />
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-amber-900">Escalation Available</h4>
          <p className="mt-0.5 text-xs text-amber-700 leading-relaxed">
            This issue may need human assistance. Would you like me to notify
            the IT team on Microsoft Teams and create a support ticket?
          </p>

          {teamsStatus === 'sending' && (
            <div className="mt-2 flex items-center gap-1.5 text-xs text-blue-600">
              <Loader2 className="h-3 w-3 animate-spin" />
              Alerting IT team on Microsoft Teams...
            </div>
          )}
          {teamsStatus === 'sent' && (
            <div className="mt-2 flex items-center gap-1.5 text-xs text-green-700">
              <CheckCircle className="h-3 w-3" />
              IT team notified on Teams -- an agent will follow up shortly.
            </div>
          )}
          {teamsStatus === 'failed' && (
            <div className="mt-2 flex items-center gap-1.5 text-xs text-red-600">
              <AlertTriangle className="h-3 w-3" />
              Teams alert failed. Email it-support@aditiconsulting.com directly.
            </div>
          )}

          <div className="mt-3 flex gap-2">
            <button
              onClick={onEscalate}
              disabled={teamsStatus === 'sending' || teamsStatus === 'sent'}
              className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {teamsStatus === 'sent' ? 'IT Notified' : 'Notify IT & Create Ticket'}
              {teamsStatus !== 'sent' && <ArrowRight className="h-3 w-3" />}
            </button>
            {onContinue && teamsStatus !== 'sent' && (
              <button
                onClick={onContinue}
                className="inline-flex items-center rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-50"
              >
                Continue with AI
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
