/**
 * RemoteAssistPage — IT agent interface for remote support session management.
 *
 * Sections:
 *  1. Active / pending sessions (real-time poll every 5s)
 *  2. Request new session modal (form with validation)
 *  3. Launch info sheet (join URL + instructions after consent granted)
 *  4. Session history table with resolution notes
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle,
  ChevronRight,
  Clock,
  ExternalLink,
  Eye,
  Loader2,
  Monitor,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { remoteApi } from '@/lib/api';
import type {
  RemoteSessionDetail,
  RemoteSessionSummary,
  SessionLaunchInfo,
} from '@/types/remote-support';


// ── Helpers ───────────────────────────────────────────────────────────

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  requested:       { label: 'Requested',        color: 'bg-gray-100 text-gray-700' },
  consent_pending: { label: 'Awaiting Consent',  color: 'bg-yellow-100 text-yellow-700' },
  consent_granted: { label: 'Consent Granted',   color: 'bg-emerald-100 text-emerald-700' },
  consent_denied:  { label: 'Denied',            color: 'bg-red-100 text-red-700' },
  connecting:      { label: 'Connecting',         color: 'bg-blue-100 text-blue-700' },
  active:          { label: 'Active',             color: 'bg-emerald-100 text-emerald-800' },
  paused:          { label: 'Paused',             color: 'bg-orange-100 text-orange-700' },
  completed:       { label: 'Completed',          color: 'bg-gray-100 text-gray-600' },
  terminated:      { label: 'Terminated',         color: 'bg-red-100 text-red-600' },
  expired:         { label: 'Expired',            color: 'bg-gray-100 text-gray-500' },
};

const ACTIVE_STATUSES = new Set([
  'requested', 'consent_pending', 'consent_granted', 'connecting', 'active', 'paused',
]);

function StatusBadge({ status }: { status: string }) {
  const { label, color } = STATUS_LABELS[status] ?? { label: status, color: 'bg-gray-100 text-gray-600' };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}

function formatDuration(secs: number | null): string {
  if (!secs) return '—';
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(iso).toLocaleDateString();
}

// ── Request Modal ─────────────────────────────────────────────────────

interface RequestModalProps {
  onClose: () => void;
  onSuccess: (sessionId: string) => void;
}

function RequestModal({ onClose, onSuccess }: RequestModalProps) {
  const [employeeId, setEmployeeId] = useState('');
  const [sessionType, setSessionType] = useState<'screen_view' | 'screen_control'>('screen_view');
  const [ticketId, setTicketId] = useState('');
  const [justification, setJustification] = useState('');
  const [maxDuration, setMaxDuration] = useState(30);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isControl = sessionType === 'screen_control';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!employeeId.trim()) { setError('Employee ID is required'); return; }
    if (isControl && !justification.trim()) { setError('Justification is required for screen control'); return; }
    setLoading(true);
    setError(null);
    try {
      const resp = await remoteApi.requestSession({
        employee_id: employeeId.trim(),
        session_type: sessionType,
        ticket_id: ticketId.trim() || undefined,
        justification: justification.trim() || undefined,
        max_duration_minutes: maxDuration,
      });
      onSuccess(resp.session_id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create session');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <h3 className="text-base font-semibold text-gray-900">Request Remote Session</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <XCircle size={20} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">
              Employee ID <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              placeholder="UUID of the employee"
              className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">Session Type</label>
            <div className="grid grid-cols-2 gap-2">
              {(['screen_view', 'screen_control'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setSessionType(t)}
                  className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm transition-colors ${
                    sessionType === t
                      ? t === 'screen_view'
                        ? 'border-emerald-500 bg-emerald-50 text-emerald-700 font-medium'
                        : 'border-amber-500 bg-amber-50 text-amber-700 font-medium'
                      : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  {t === 'screen_view' ? <Eye size={15} /> : <ShieldAlert size={15} />}
                  {t === 'screen_view' ? 'View Only' : 'Full Control'}
                </button>
              ))}
            </div>
            {isControl && (
              <p className="text-xs text-amber-700 mt-1.5 flex items-center gap-1">
                <AlertTriangle size={12} /> Requires IT Lead / Admin + justification
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">Linked Ticket (optional)</label>
            <input
              type="text"
              value={ticketId}
              onChange={(e) => setTicketId(e.target.value)}
              placeholder="Ticket UUID"
              className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">
              Justification {isControl && <span className="text-red-500">*</span>}
            </label>
            <textarea
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              placeholder={isControl ? 'Required — describe why control access is needed' : 'Optional'}
              rows={3}
              className="w-full px-3 py-2 border rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-emerald-300"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">
              Max Duration: <strong>{maxDuration} minutes</strong>
            </label>
            <input
              type="range" min={5} max={120} step={5} value={maxDuration}
              onChange={(e) => setMaxDuration(Number(e.target.value))}
              className="w-full accent-emerald-600"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-0.5">
              <span>5 min</span><span>2 hours</span>
            </div>
          </div>
          {error && (
            <div className="flex gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <AlertTriangle size={14} className="shrink-0 mt-0.5" /> {error}
            </div>
          )}
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose} disabled={loading}
              className="flex-1 px-4 py-2.5 border rounded-lg text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">
              Cancel
            </button>
            <button type="submit" disabled={loading}
              className="flex-1 px-4 py-2.5 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 disabled:opacity-50 flex items-center justify-center gap-2">
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Monitor size={14} />}
              {loading ? 'Sending…' : 'Send Request'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Launch Info Sheet ─────────────────────────────────────────────────

function LaunchSheet({
  info,
  onConnected,
  onClose,
}: {
  info: SessionLaunchInfo;
  onConnected: () => void;
  onClose: () => void;
}) {
  const [marking, setMarking] = useState(false);

  const handleConnected = async () => {
    setMarking(true);
    try { await remoteApi.markConnected(info.session_id); onConnected(); }
    finally { setMarking(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b flex items-center gap-3">
          <ShieldCheck className="text-emerald-600" size={20} />
          <h3 className="text-base font-semibold text-gray-900">Session Ready</h3>
        </div>
        <div className="px-6 py-5 space-y-4">
          <p className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg p-3">
            {info.instructions}
          </p>
          {info.join_code && (
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <p className="text-xs text-gray-500 mb-1">Session Code</p>
              <p className="text-2xl font-mono font-bold text-gray-900 tracking-widest">{info.join_code}</p>
            </div>
          )}
          <a href={info.join_url} target="_blank" rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 w-full px-4 py-3 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700">
            <ExternalLink size={15} /> Open in {info.provider_display_name}
          </a>
          <div className="flex gap-3">
            <button onClick={onClose} className="flex-1 px-4 py-2 border rounded-lg text-sm text-gray-700 hover:bg-gray-50">
              Close
            </button>
            <button onClick={handleConnected} disabled={marking}
              className="flex-1 px-4 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 disabled:opacity-50 flex items-center justify-center gap-2">
              {marking && <Loader2 size={13} className="animate-spin" />}
              {marking ? 'Saving…' : 'Mark as Connected'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Session Detail Side Panel ─────────────────────────────────────────

function DetailPanel({
  sessionId,
  onClose,
  onRefresh,
}: {
  sessionId: string;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const [detail, setDetail] = useState<RemoteSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [resolutionNotes, setResolutionNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [ending, setEnding] = useState(false);

  useEffect(() => {
    remoteApi.getSession(sessionId).then((d) => {
      setDetail(d);
      setResolutionNotes(d.resolution_notes ?? '');
    }).finally(() => setLoading(false));
  }, [sessionId]);

  const handleEnd = async () => {
    if (!detail) return;
    setEnding(true);
    try {
      await remoteApi.endSession(sessionId, { resolution_notes: resolutionNotes || undefined });
      onRefresh();
      onClose();
    } finally { setEnding(false); }
  };

  const handleSaveNotes = async () => {
    setSaving(true);
    try { await remoteApi.updateResolution(sessionId, { resolution_notes: resolutionNotes }); onRefresh(); }
    finally { setSaving(false); }
  };

  const isActive = detail && ACTIVE_STATUSES.has(detail.status);
  const isEnded = detail && !ACTIVE_STATUSES.has(detail.status);

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-96 bg-white shadow-2xl flex flex-col">
      <div className="px-5 py-4 border-b flex items-center justify-between shrink-0">
        <h3 className="font-semibold text-gray-900 text-sm">Session Detail</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><XCircle size={18} /></button>
      </div>
      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="animate-spin text-gray-400" size={24} />
        </div>
      ) : detail ? (
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          <div className="flex items-center justify-between">
            <StatusBadge status={detail.status} />
            <span className="text-xs text-gray-500">{formatRelative(detail.requested_at)}</span>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Type</span>
              <span className="font-medium capitalize">{detail.session_type.replace('_', ' ')}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Duration</span>
              <span className="font-medium">{formatDuration(detail.duration_seconds)}</span>
            </div>
            {detail.justification && (
              <div>
                <span className="text-gray-500 block mb-1">Justification</span>
                <p className="text-gray-700 bg-gray-50 rounded p-2 text-xs leading-relaxed italic">
                  "{detail.justification}"
                </p>
              </div>
            )}
          </div>
          {detail.status === 'consent_granted' && (
            <button
              className="w-full px-4 py-2.5 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 flex items-center justify-center gap-2"
              onClick={async () => {
                const info = await remoteApi.launchSession(sessionId);
                window.open(info.join_url, '_blank');
                onRefresh();
              }}
            >
              <Monitor size={15} /> Launch Session
            </button>
          )}
          {detail.events.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Timeline</h4>
              <ol className="relative border-l border-gray-200 ml-2 space-y-3">
                {detail.events.map((ev) => (
                  <li key={ev.id} className="ml-4">
                    <span className="absolute -left-1.5 w-3 h-3 bg-gray-300 rounded-full border border-white" />
                    <p className="text-xs text-gray-700">{ev.description ?? ev.event_type}</p>
                    <p className="text-xs text-gray-400">{formatRelative(ev.occurred_at)}</p>
                  </li>
                ))}
              </ol>
            </div>
          )}
          <div>
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Resolution Notes
            </h4>
            <textarea value={resolutionNotes} onChange={(e) => setResolutionNotes(e.target.value)}
              rows={4} placeholder="Describe what was resolved…"
              className="w-full px-3 py-2 border rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-emerald-300"
            />
            {isEnded && (
              <button onClick={handleSaveNotes} disabled={saving}
                className="mt-2 w-full px-3 py-2 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200 disabled:opacity-50 flex items-center justify-center gap-2">
                {saving && <Loader2 size={13} className="animate-spin" />}
                {saving ? 'Saving…' : 'Save Notes'}
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-sm text-gray-500">Session not found.</div>
      )}
      {detail && isActive && (
        <div className="px-5 py-4 border-t shrink-0">
          <button onClick={handleEnd} disabled={ending}
            className="w-full px-4 py-2.5 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-50 flex items-center justify-center gap-2">
            {ending ? <Loader2 size={14} className="animate-spin" /> : <XCircle size={15} />}
            {ending ? 'Ending…' : 'End Session'}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────

export function RemoteAssistPage() {
  const [sessions, setSessions] = useState<RemoteSessionSummary[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [showRequestModal, setShowRequestModal] = useState(false);
  const [launchInfo, setLaunchInfo] = useState<SessionLaunchInfo | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadSessions = useCallback(async () => {
    try {
      const data = await remoteApi.listSessions({ limit: 50 });
      setSessions(data);
      setListError(null);
    } catch {
      setListError('Could not load sessions.');
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    loadSessions();
    pollRef.current = setInterval(loadSessions, 5000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [loadSessions]);

  const activeSessions = sessions.filter((s) => ACTIVE_STATUSES.has(s.status));
  const historySessions = sessions.filter((s) => !ACTIVE_STATUSES.has(s.status));

  const handleLaunch = async (sessionId: string) => {
    try {
      const info = await remoteApi.launchSession(sessionId);
      setLaunchInfo(info);
      await loadSessions();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to launch session');
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Remote Assistance</h1>
          <p className="text-sm text-gray-500 mt-1">Request and manage remote support sessions</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadSessions} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg" title="Refresh">
            <RefreshCw size={16} />
          </button>
          <button onClick={() => setShowRequestModal(true)}
            className="px-4 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 flex items-center gap-2">
            <Monitor size={15} /> New Session
          </button>
        </div>
      </div>

      {listError && (
        <div className="flex gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" /> {listError}
        </div>
      )}

      {/* Active sessions */}
      <section>
        <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          Active Sessions
          {activeSessions.length > 0 && (
            <span className="text-xs font-normal text-gray-400">({activeSessions.length})</span>
          )}
        </h2>
        {loadingList ? (
          <div className="bg-white rounded-xl border p-6 flex items-center justify-center gap-2 text-sm text-gray-500">
            <Loader2 size={16} className="animate-spin" /> Loading…
          </div>
        ) : activeSessions.length === 0 ? (
          <div className="bg-white rounded-xl border p-6 text-center">
            <ShieldCheck className="mx-auto h-8 w-8 text-gray-300 mb-2" />
            <p className="text-sm text-gray-500">No active remote sessions</p>
          </div>
        ) : (
          <div className="space-y-2">
            {activeSessions.map((s) => (
              <div key={s.id}
                className="bg-white rounded-xl border px-4 py-3 flex items-center justify-between hover:border-gray-300 cursor-pointer"
                onClick={() => setSelectedSessionId(s.id)}
              >
                <div className="flex items-center gap-3">
                  {s.session_type === 'screen_control'
                    ? <ShieldAlert className="text-amber-500" size={18} />
                    : <Eye className="text-blue-500" size={18} />}
                  <div>
                    <p className="text-sm font-medium text-gray-800">
                      {s.session_type === 'screen_control' ? 'Full Control' : 'View Only'}
                    </p>
                    <p className="text-xs text-gray-500 flex items-center gap-1">
                      <Clock size={11} /> {formatRelative(s.requested_at)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge status={s.status} />
                  {s.status === 'consent_granted' && (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleLaunch(s.id); }}
                      className="px-3 py-1.5 bg-emerald-600 text-white text-xs font-medium rounded-lg hover:bg-emerald-700 flex items-center gap-1"
                    >
                      <Monitor size={12} /> Launch
                    </button>
                  )}
                  <ChevronRight size={16} className="text-gray-400" />
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* History */}
      <section>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Session History</h2>
        {!loadingList && historySessions.length === 0 ? (
          <div className="bg-white rounded-xl border p-6 text-center text-sm text-gray-500">
            No completed sessions yet.
          </div>
        ) : !loadingList ? (
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-gray-50 text-xs text-gray-500">
                  <th className="px-4 py-2.5 text-left font-medium">ID</th>
                  <th className="px-4 py-2.5 text-left font-medium">Type</th>
                  <th className="px-4 py-2.5 text-left font-medium">Status</th>
                  <th className="px-4 py-2.5 text-left font-medium">Requested</th>
                  <th className="px-4 py-2.5 text-left font-medium">Duration</th>
                  <th className="px-4 py-2.5 text-right font-medium" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {historySessions.map((s) => (
                  <tr key={s.id} className="hover:bg-gray-50 cursor-pointer" onClick={() => setSelectedSessionId(s.id)}>
                    <td className="px-4 py-3 text-xs font-mono text-gray-500">{s.id.slice(0, 8)}…</td>
                    <td className="px-4 py-3 text-xs text-gray-600 capitalize">{s.session_type.replace('_', ' ')}</td>
                    <td className="px-4 py-3"><StatusBadge status={s.status} /></td>
                    <td className="px-4 py-3 text-xs text-gray-500">{formatRelative(s.requested_at)}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">{formatDuration(s.duration_seconds)}</td>
                    <td className="px-4 py-3 text-right"><ChevronRight size={14} className="text-gray-400 ml-auto" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <div className="flex items-center gap-4 text-xs text-gray-400 pt-1">
        <span className="flex items-center gap-1"><CheckCircle size={12} className="text-emerald-500" /> Completed</span>
        <span className="flex items-center gap-1"><XCircle size={12} className="text-red-400" /> Terminated / Denied</span>
        <span className="flex items-center gap-1"><Clock size={12} /> Expired</span>
      </div>

      {showRequestModal && (
        <RequestModal
          onClose={() => setShowRequestModal(false)}
          onSuccess={(id) => { setShowRequestModal(false); setSelectedSessionId(id); loadSessions(); }}
        />
      )}
      {launchInfo && (
        <LaunchSheet
          info={launchInfo}
          onConnected={() => { setLaunchInfo(null); loadSessions(); }}
          onClose={() => setLaunchInfo(null)}
        />
      )}
      {selectedSessionId && (
        <>
          <div className="fixed inset-0 z-30 bg-transparent lg:hidden" onClick={() => setSelectedSessionId(null)} />
          <DetailPanel
            sessionId={selectedSessionId}
            onClose={() => setSelectedSessionId(null)}
            onRefresh={loadSessions}
          />
        </>
      )}
    </div>
  );
}
