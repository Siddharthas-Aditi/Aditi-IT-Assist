/**
 * ConsentModal — shown to the employee when an IT agent requests remote access.
 *
 * Features:
 *  - Displays verbatim legal consent notice from the backend
 *  - Countdown timer to the consent deadline (auto-expires)
 *  - Grant and Deny buttons with confirmation step for control sessions
 *  - Loading / error states
 */

import { useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  Clock,
  Eye,
  Monitor,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react';
import type { ConsentNotification } from '@/types/remote-support';

interface Props {
  notification: ConsentNotification;
  onGrant: () => Promise<void>;
  onDeny: (reason?: string) => Promise<void>;
  onClose?: () => void;
}

function useCountdown(deadline: string) {
  const [secondsLeft, setSecondsLeft] = useState(() => {
    const ms = new Date(deadline).getTime() - Date.now();
    return Math.max(0, Math.floor(ms / 1000));
  });

  useEffect(() => {
    if (secondsLeft <= 0) return;
    const id = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          clearInterval(id);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, []);           // intentionally run once; deadline won't change mid-display

  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;
  const isUrgent = secondsLeft < 60;
  const isExpired = secondsLeft === 0;

  return { minutes, seconds, isUrgent, isExpired, secondsLeft };
}

export function ConsentModal({ notification, onGrant, onDeny, onClose: _onClose }: Props) {
  const isControlSession = notification.session_type === 'screen_control';
  const { minutes, seconds, isUrgent, isExpired } = useCountdown(notification.consent_deadline);

  const [step, setStep] = useState<'review' | 'confirm-deny'>('review');
  const [denialReason, setDenialReason] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const consentTextRef = useRef<HTMLDivElement>(null);
  const [hasScrolled, setHasScrolled] = useState(false);

  // Require the employee to scroll to the bottom of the consent notice
  const handleScroll = () => {
    const el = consentTextRef.current;
    if (el && el.scrollHeight - el.scrollTop <= el.clientHeight + 4) {
      setHasScrolled(true);
    }
  };

  const handleGrant = async () => {
    setLoading(true);
    setError(null);
    try {
      await onGrant();
    } catch {
      setError('Could not submit consent. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleDeny = async () => {
    setLoading(true);
    setError(null);
    try {
      await onDeny(denialReason || undefined);
    } catch {
      setError('Could not submit response. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        className="w-full max-w-lg bg-white rounded-2xl shadow-2xl overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="consent-modal-title"
      >
        {/* Header */}
        <div
          className={`px-6 py-4 flex items-start justify-between ${
            isControlSession ? 'bg-amber-50 border-b border-amber-200' : 'bg-blue-50 border-b border-blue-200'
          }`}
        >
          <div className="flex items-center gap-3">
            {isControlSession ? (
              <ShieldAlert className="w-6 h-6 text-amber-600 shrink-0" />
            ) : (
              <Eye className="w-6 h-6 text-blue-600 shrink-0" />
            )}
            <div>
              <h2
                id="consent-modal-title"
                className={`text-base font-semibold ${isControlSession ? 'text-amber-900' : 'text-blue-900'}`}
              >
                Remote {notification.session_type_label} Request
              </h2>
              <p className={`text-xs mt-0.5 ${isControlSession ? 'text-amber-700' : 'text-blue-700'}`}>
                From {notification.agent_name} · {notification.agent_email}
              </p>
            </div>
          </div>

          {/* Countdown */}
          <div
            className={`flex items-center gap-1.5 text-sm font-medium px-2.5 py-1 rounded-full ${
              isExpired
                ? 'bg-red-100 text-red-700'
                : isUrgent
                ? 'bg-orange-100 text-orange-700'
                : 'bg-gray-100 text-gray-600'
            }`}
          >
            <Clock size={13} />
            {isExpired ? 'Expired' : `${minutes}:${String(seconds).padStart(2, '0')}`}
          </div>
        </div>

        {step === 'review' ? (
          <>
            {/* Body */}
            <div className="px-6 pt-4 pb-2 space-y-4">
              {/* Session info */}
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-0.5">Session Type</p>
                  <div className="flex items-center gap-1.5 font-medium text-gray-800">
                    <Monitor size={14} />
                    {notification.session_type_label}
                  </div>
                </div>
                {notification.ticket_reference && (
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-xs text-gray-500 mb-0.5">Related Ticket</p>
                    <p className="font-medium text-gray-800 truncate">
                      #{notification.ticket_reference.slice(0, 8)}…
                    </p>
                  </div>
                )}
              </div>

              {/* Justification */}
              {notification.justification && (
                <div className="bg-gray-50 rounded-lg p-3 text-sm">
                  <p className="text-xs text-gray-500 mb-1">Reason given by agent</p>
                  <p className="text-gray-800 italic">"{notification.justification}"</p>
                </div>
              )}

              {/* High-risk warning for screen_control */}
              {isControlSession && (
                <div className="flex gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
                  <AlertTriangle size={16} className="shrink-0 mt-0.5 text-amber-600" />
                  <span>
                    <strong>Full control</strong> means the agent can move your mouse, type, and
                    open applications. Only proceed if you recognise this request.
                  </span>
                </div>
              )}

              {/* Consent notice — scrollable */}
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wide">
                  Consent Notice — please read in full
                </p>
                <div
                  ref={consentTextRef}
                  onScroll={handleScroll}
                  className="max-h-32 overflow-y-auto border rounded-lg p-3 text-xs text-gray-700 leading-relaxed bg-gray-50"
                >
                  {notification.consent_text}
                </div>
                {!hasScrolled && (
                  <p className="text-xs text-gray-400 mt-1 flex items-center gap-1">
                    <span>↓ Scroll to read the full notice before accepting</span>
                  </p>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 pb-5 pt-2 space-y-3">
              {error && (
                <p className="text-sm text-red-600 flex items-center gap-1.5">
                  <AlertTriangle size={14} /> {error}
                </p>
              )}
              {isExpired ? (
                <div className="text-center text-sm text-gray-500 py-2">
                  This request has expired. The IT agent can resend if still needed.
                </div>
              ) : (
                <div className="flex gap-3">
                  <button
                    onClick={() => setStep('confirm-deny')}
                    disabled={loading}
                    className="flex-1 px-4 py-2.5 border border-gray-300 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    <X size={15} /> Deny
                  </button>
                  <button
                    onClick={handleGrant}
                    disabled={loading || !hasScrolled}
                    title={!hasScrolled ? 'Please scroll through the consent notice first' : undefined}
                    className={`flex-1 px-4 py-2.5 text-white text-sm font-medium rounded-lg disabled:opacity-50 flex items-center justify-center gap-2 ${
                      isControlSession
                        ? 'bg-amber-600 hover:bg-amber-700'
                        : 'bg-emerald-600 hover:bg-emerald-700'
                    }`}
                  >
                    {loading ? (
                      <span className="animate-spin w-4 h-4 border-2 border-white/40 border-t-white rounded-full" />
                    ) : (
                      <ShieldCheck size={15} />
                    )}
                    {loading ? 'Submitting…' : 'Grant Access'}
                  </button>
                </div>
              )}
            </div>
          </>
        ) : (
          /* Deny confirmation step */
          <div className="px-6 py-5 space-y-4">
            <p className="text-sm text-gray-700">
              You&rsquo;re about to <strong>deny</strong> this remote session request. The IT agent
              will be notified. This cannot be undone.
            </p>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">
                Reason (optional)
              </label>
              <textarea
                className="w-full px-3 py-2 border rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-red-300"
                rows={3}
                placeholder="e.g. Not my session, did not request support…"
                value={denialReason}
                onChange={(e) => setDenialReason(e.target.value)}
              />
            </div>
            {error && (
              <p className="text-sm text-red-600 flex items-center gap-1.5">
                <AlertTriangle size={14} /> {error}
              </p>
            )}
            <div className="flex gap-3">
              <button
                onClick={() => setStep('review')}
                disabled={loading}
                className="flex-1 px-4 py-2.5 border border-gray-300 text-gray-700 text-sm rounded-lg hover:bg-gray-50 disabled:opacity-50"
              >
                Back
              </button>
              <button
                onClick={handleDeny}
                disabled={loading}
                className="flex-1 px-4 py-2.5 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading ? (
                  <span className="animate-spin w-4 h-4 border-2 border-white/40 border-t-white rounded-full" />
                ) : null}
                {loading ? 'Submitting…' : 'Confirm Deny'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
