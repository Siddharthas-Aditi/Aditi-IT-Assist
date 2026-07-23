/** Pure presentational banner for the employee side of a live-agent handoff.
 *
 * Renders one of four messages driven by `handoff_state` (see
 * `GET /chat/waiting-status/{id}`). `connected` is included for completeness
 * / testability, but in practice `SupportChatPage` swaps to the emerald
 * "specialist has joined" banner (and hides this one) as soon as the
 * `/specialist-chat/active` poll reports a live session.
 */

export type HandoffState = 'connecting' | 'busy' | 'connected' | 'fallback';

const MESSAGES: Record<HandoffState, string> = {
  connecting: 'Connecting you to a live IT specialist…',
  busy:
    'Our IT specialists are busy at the moment — someone may join your chat shortly. Hang tight.',
  connected: 'An IT specialist has joined.',
  fallback:
    "No specialist is free right now — I've logged your ticket and the team will follow up. " +
    'You can keep chatting with me in the meantime.',
};

interface WaitingBannerProps {
  handoffState: HandoffState;
  onCancel: () => void;
}

export function WaitingBanner({ handoffState, onCancel }: WaitingBannerProps) {
  // `fallback` is terminal for the waiting flow — a ticket has already been
  // logged, so there's nothing left to cancel and no imminent connection to
  // imply with a spinner.
  const terminal = handoffState === 'fallback';

  return (
    <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      {!terminal && (
        <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
      )}
      <span className="flex-1 font-medium">{MESSAGES[handoffState]}</span>
      {!terminal && (
        <button
          type="button"
          onClick={onCancel}
          className="shrink-0 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-100"
        >
          Cancel
        </button>
      )}
    </div>
  );
}
