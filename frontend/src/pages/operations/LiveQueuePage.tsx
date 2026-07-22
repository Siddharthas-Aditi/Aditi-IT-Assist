/**
 * Live queue — IT-specialist view of pending handoffs.
 *
 * Polls `/specialist-queue` and renders the typed `QueueEntry` rows. Claim
 * is atomic on the backend; the UI surfaces HTTP 409 ("already claimed
 * by …") as an inline banner instead of a crash.
 *
 * Filter pills mirror the registry: `all` (default), `unclaimed`, `mine`.
 * The component is intentionally self-contained — no Zustand store — so
 * the queue can refresh independently of the rest of the operations UI.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { type QueueEntry, liveChatApi, queueApi } from '@/features/specialist-chat/api';
import { ApiError } from '@/lib/api';
import {
  notifyDesktop,
  playNotificationChime,
  requestNotificationPermission,
} from '@/lib/notification-sound';

type Filter = 'all' | 'unclaimed' | 'mine';

export function LiveQueuePage() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<Filter>('all');
  const [entries, setEntries] = useState<QueueEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [claimingId, setClaimingId] = useState<string | null>(null);
  const [soundOn, setSoundOn] = useState(true);
  // Unclaimed ticket IDs we've already seen — so the chime fires once per new
  // handoff, not on every 15s poll. `null` until the first load so we don't
  // chime for the queue that already existed when the page opened.
  const seenUnclaimedRef = useRef<Set<string> | null>(null);
  const soundOnRef = useRef(soundOn);
  soundOnRef.current = soundOn;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await queueApi.list({
        onlyUnclaimed: filter === 'unclaimed',
        includeMine: filter !== 'unclaimed',
        limit: 100,
      });
      setEntries(resp.entries);

      // Detect newly-arrived *fresh* handoffs (employee still waiting) and
      // alert once each. Stale "likely_left" entries don't ring — the employee
      // has already been shown the async-ticket fallback and is not at the
      // keyboard, so a chime would be misleading.
      const currentUnclaimed = resp.entries.filter(
        (e) => !e.claimed_at && e.waiting_state === 'waiting',
      );
      const currentIds = new Set(currentUnclaimed.map((e) => e.ticket_id));
      const seen = seenUnclaimedRef.current;
      if (seen === null) {
        // First load — prime the baseline silently.
        seenUnclaimedRef.current = currentIds;
      } else {
        const fresh = currentUnclaimed.filter((e) => !seen.has(e.ticket_id));
        if (fresh.length > 0 && soundOnRef.current) {
          playNotificationChime();
          notifyDesktop(
            'New live support request',
            fresh.length === 1
              ? `${fresh[0].ticket_number}: ${fresh[0].summary.issue_one_liner || fresh[0].title}`
              : `${fresh.length} new chat handoffs are waiting.`,
          );
        }
        seenUnclaimedRef.current = currentIds;
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load queue');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void load();
    const t = window.setInterval(load, 15000);
    return () => window.clearInterval(t);
  }, [load]);

  const onClaim = async (entry: QueueEntry) => {
    setClaimingId(entry.ticket_id);
    setError(null);
    setInfo(null);
    try {
      const claimed = await queueApi.claim(entry.ticket_id);

      if (claimed.waiting_state === 'likely_left') {
        // Employee waited past the live-chat timeout — open the ticket workspace
        // for async follow-up (matches the claim contract / API docs).
        setInfo(
          `${entry.ticket_number} claimed — employee may have left (waited ${Math.round(claimed.waited_seconds / 60)}m). ` +
            'Opening ticket workspace for async follow-up.',
        );
        navigate(`/operations/tickets/${entry.ticket_id}`);
      } else {
        // Employee is still actively waiting — start the live session immediately.
        const live = await liveChatApi.start(entry.ticket_id);
        navigate(`/operations/live-chat/${live.id}`, {
          state: { ticketNumber: entry.ticket_number },
        });
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setError(`${entry.ticket_number} was already claimed — refreshing.`);
        await load();
      } else {
        setError(e instanceof Error ? e.message : 'Claim failed');
      }
    } finally {
      setClaimingId(null);
    }
  };

  const unclaimed = entries.filter((e) => !e.claimed_at).length;
  const inProgress = entries.filter((e) => e.status === 'in_progress').length;

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Live Support Queue</h1>
          <p className="text-sm text-gray-500 mt-1">
            Incoming chat handoffs from the AI assistant.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              const next = !soundOn;
              setSoundOn(next);
              if (next) {
                requestNotificationPermission();
                playNotificationChime(); // also unlocks audio via the click gesture
              }
            }}
            title={soundOn ? 'Mute new-request sound' : 'Enable new-request sound'}
            className={`px-3 py-1.5 text-xs rounded-full font-medium ${
              soundOn
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
            }`}
          >
            {soundOn ? '🔔 Sound on' : '🔕 Muted'}
          </button>
          {(['all', 'unclaimed', 'mine'] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-xs rounded-full font-medium ${
                filter === f
                  ? 'bg-indigo-100 text-indigo-700'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {f === 'all' ? 'All' : f === 'unclaimed' ? 'Unclaimed' : 'Mine'}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6">
        <Stat label="Unclaimed" value={unclaimed} tone="red" />
        <Stat label="In Progress" value={inProgress} tone="yellow" />
        <Stat label="Total" value={entries.length} tone="indigo" />
      </div>

      {error && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          {error}
        </div>
      )}

      {info && (
        <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-800">
          {info}
        </div>
      )}

      <div className="bg-white rounded-lg border overflow-hidden">
        <div className="p-4 border-b bg-gray-50 flex items-center justify-between">
          <h2 className="text-sm font-medium text-gray-700">Queue ({entries.length})</h2>
          <button
            onClick={() => void load()}
            className="text-xs text-indigo-600 hover:text-indigo-800"
          >
            Refresh
          </button>
        </div>

        {loading && entries.length === 0 ? (
          <div className="p-8 text-center text-gray-400 text-sm">Loading queue…</div>
        ) : entries.length === 0 ? (
          <div className="p-8 text-center text-gray-500 text-sm">
            No queue entries match this filter.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
              <tr>
                <th className="px-4 py-2 text-left">Ticket</th>
                <th className="px-4 py-2 text-left">Issue</th>
                <th className="px-4 py-2 text-left">User</th>
                <th className="px-4 py-2 text-left">Priority</th>
                <th className="px-4 py-2 text-left">Age</th>
                <th className="px-4 py-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {entries.map((e) => (
                <tr
                  key={e.ticket_id}
                  className={`hover:bg-gray-50 ${e.waiting_state === 'likely_left' ? 'opacity-60' : ''}`}
                >
                  <td className="px-4 py-3 font-medium text-indigo-700">
                    <Link
                      to={`/operations/tickets/${e.ticket_id}`}
                      className="hover:underline"
                      onClick={(ev) => ev.stopPropagation()}
                    >
                      {e.ticket_number}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-700">
                    <div>{e.summary.issue_one_liner || e.title}</div>
                    <div className="text-xs text-gray-400">
                      {e.summary.issue_subtype || e.summary.issue_category || '—'}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {e.summary.user_name || e.requester_name || '—'}
                  </td>
                  <td className="px-4 py-3">
                    <PriorityBadge priority={e.priority} />
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    <div>{relativeAge(e.queued_at)}</div>
                    {e.waiting_state === 'likely_left' && (
                      <div className="mt-0.5 text-xs text-amber-600 font-medium">
                        May have left
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link
                        to={`/operations/tickets/${e.ticket_id}`}
                        className="px-2.5 py-1 text-xs rounded-md border border-gray-200 text-gray-700 hover:bg-gray-50"
                      >
                        View ticket
                      </Link>
                      {e.claimed_at ? (
                        <span className="text-xs text-gray-400">
                          Claimed{e.claimed_by_name ? ` by ${e.claimed_by_name}` : ''}
                        </span>
                      ) : (
                        <button
                          onClick={() => void onClaim(e)}
                          disabled={claimingId === e.ticket_id}
                          title={
                            e.waiting_state === 'likely_left'
                              ? 'Employee may have left — opens ticket workspace'
                              : 'Claim and open live chat'
                          }
                          className={`px-3 py-1 text-xs rounded-md disabled:opacity-50 ${
                            e.waiting_state === 'likely_left'
                              ? 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                              : 'bg-indigo-600 text-white hover:bg-indigo-700'
                          }`}
                        >
                          {claimingId === e.ticket_id
                            ? 'Claiming…'
                            : e.waiting_state === 'likely_left'
                              ? 'Claim (async)'
                              : 'Claim'}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: 'red' | 'yellow' | 'indigo';
}) {
  const colors = {
    red: 'text-red-600',
    yellow: 'text-yellow-600',
    indigo: 'text-indigo-600',
  }[tone];
  return (
    <div className="bg-white rounded-lg border p-4">
      <p className={`text-2xl font-bold ${colors}`}>{value}</p>
      <p className="text-xs text-gray-500 mt-1">{label}</p>
    </div>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const tone =
    priority === 'critical'
      ? 'bg-red-100 text-red-700'
      : priority === 'high'
        ? 'bg-orange-100 text-orange-700'
        : priority === 'medium'
          ? 'bg-yellow-100 text-yellow-700'
          : 'bg-gray-100 text-gray-700';
  return <span className={`px-2 py-0.5 text-xs rounded-full font-medium ${tone}`}>{priority}</span>;
}

function relativeAge(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h`;
  return `${Math.floor(hr / 24)}d`;
}
