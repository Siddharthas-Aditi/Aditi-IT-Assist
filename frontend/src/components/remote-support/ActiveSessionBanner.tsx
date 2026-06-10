/**
 * ActiveSessionBanner — persistent banner shown to employees during an active remote session.
 *
 * Displayed at the top of the employee workspace when a remote session
 * is in the `active` or `connecting` state. Allows the employee to
 * revoke consent and end the session at any time.
 */

import { useState } from 'react';
import { AlertTriangle, Monitor, X } from 'lucide-react';
import type { RemoteSessionSummary } from '@/types/remote-support';

interface Props {
  session: RemoteSessionSummary;
  onRevoke: (reason?: string) => Promise<void>;
}

export function ActiveSessionBanner({ session, onRevoke }: Props) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isControl = session.session_type === 'screen_control';

  const handleRevoke = async () => {
    setLoading(true);
    setError(null);
    try {
      await onRevoke(reason || undefined);
    } catch {
      setError('Could not end session. Please try again or close the remote tool manually.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Banner */}
      <div
        className={`w-full px-4 py-2.5 flex items-center justify-between text-sm ${
          isControl
            ? 'bg-amber-600 text-white'
            : 'bg-blue-600 text-white'
        }`}
        role="alert"
      >
        <div className="flex items-center gap-2">
          <Monitor size={16} className="shrink-0 animate-pulse" />
          <span>
            {session.status === 'connecting' ? (
              <span>An IT agent is connecting to your screen…</span>
            ) : (
              <span>
                An IT agent has {isControl ? 'control of' : 'view access to'} your screen.
                You can end this session at any time.
              </span>
            )}
          </span>
        </div>
        <button
          onClick={() => setShowConfirm(true)}
          className="ml-4 flex items-center gap-1.5 px-3 py-1 bg-white/20 hover:bg-white/30 rounded-md font-medium transition-colors shrink-0"
        >
          <X size={14} /> End Session
        </button>
      </div>

      {/* Confirmation dialog */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm p-6 space-y-4">
            <div className="flex items-center gap-3">
              <AlertTriangle className="text-red-500 shrink-0" size={22} />
              <h3 className="text-base font-semibold text-gray-900">End Remote Session?</h3>
            </div>
            <p className="text-sm text-gray-600">
              This will immediately revoke your consent and disconnect the IT agent.
              The session will be closed.
            </p>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">
                Reason (optional)
              </label>
              <input
                type="text"
                className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-300"
                placeholder="e.g. Issue resolved, I want to end now…"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </div>
            {error && (
              <p className="text-sm text-red-600 flex items-center gap-1.5">
                <AlertTriangle size={13} /> {error}
              </p>
            )}
            <div className="flex gap-3 pt-1">
              <button
                onClick={() => { setShowConfirm(false); setError(null); }}
                disabled={loading}
                className="flex-1 px-4 py-2 border rounded-lg text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Keep Active
              </button>
              <button
                onClick={handleRevoke}
                disabled={loading}
                className="flex-1 px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading && (
                  <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                )}
                {loading ? 'Ending…' : 'End Session'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
