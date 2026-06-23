/**
 * Live chat pane — the human-to-human leg after AI handoff.
 *
 * Polls ``GET /specialist-chat/{id}`` every 3s. Sends via
 * ``POST /specialist-chat/{id}/message``. Ends via
 * ``POST /specialist-chat/{id}/end`` with a typed reason.
 *
 * Idle warning is rendered as a top banner — the user/specialist seeing it
 * just needs to type something for the backend to flip status back to active.
 *
 * Phase 2 will swap the polling for a WebSocket push; this component's
 * shape (state + actions) is the same so the upgrade is additive.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useAuthStore } from '@/stores/auth-store';

import {
  type SpecialistChatEndReason,
  type SpecialistChatSessionOut,
  liveChatApi,
} from '@/features/specialist-chat/api';

const POLL_INTERVAL_MS = 3000;

export function LiveChatPage() {
  const { sessionId = '' } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const { user } = useAuthStore();

  const [session, setSession] = useState<SpecialistChatSessionOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [ending, setEnding] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Typing-indicator heartbeat: throttle "typing=true" pings and schedule a
  // "typing=false" once the user pauses, so we never spam the network.
  const lastTypingPingRef = useRef(0);
  const typingStopTimerRef = useRef<number | null>(null);

  const signalTyping = useCallback(
    (typing: boolean) => {
      if (!sessionId) return;
      if (typingStopTimerRef.current) {
        window.clearTimeout(typingStopTimerRef.current);
        typingStopTimerRef.current = null;
      }
      if (typing) {
        const now = Date.now();
        // At most one ping every 2.5s while composing.
        if (now - lastTypingPingRef.current > 2500) {
          lastTypingPingRef.current = now;
          void liveChatApi.typing(sessionId, true).catch(() => {});
        }
        // Auto-clear if the user stops typing for 3s.
        typingStopTimerRef.current = window.setTimeout(() => {
          lastTypingPingRef.current = 0;
          void liveChatApi.typing(sessionId, false).catch(() => {});
        }, 3000);
      } else {
        lastTypingPingRef.current = 0;
        void liveChatApi.typing(sessionId, false).catch(() => {});
      }
    },
    [sessionId],
  );

  const poll = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await liveChatApi.get(sessionId);
      setSession(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load chat');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  // Initial load + polling. Stops polling once the session ends.
  useEffect(() => {
    void poll();
    const t = window.setInterval(() => {
      if (session?.status.startsWith('ended')) return;
      void poll();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(t);
  }, [poll, session?.status]);

  // Auto-scroll on new messages.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [session?.messages.length]);

  const send = async () => {
    if (!sessionId || !input.trim() || !session) return;
    setSending(true);
    setError(null);
    try {
      signalTyping(false);
      await liveChatApi.send(sessionId, input.trim());
      setInput('');
      await poll();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send');
    } finally {
      setSending(false);
    }
  };

  const end = async (reason: SpecialistChatEndReason) => {
    if (!sessionId) return;
    setEnding(true);
    setError(null);
    try {
      await liveChatApi.end(sessionId, { reason });
      await poll();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to end chat');
    } finally {
      setEnding(false);
    }
  };

  if (loading || !session) {
    return (
      <div className="p-8 text-center text-gray-500 text-sm">
        Loading chat session…
        {error && <div className="mt-2 text-red-600">{error}</div>}
      </div>
    );
  }

  const isSpecialist = user?.id === session.specialist_id;
  const isEnded = session.status.startsWith('ended');

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <Header
        session={session}
        onBack={() => navigate(isSpecialist ? '/operations/assigned' : '/support')}
      />

      {session.status === 'idle_warning' && !isEnded && (
        <div className="mb-3 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          This chat has been quiet for a few minutes. A message keeps it open;
          otherwise it'll end automatically in about {graceMinutes(session)}.
        </div>
      )}

      {isEnded && (
        <div className="mb-3 p-3 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-700">
          This chat has ended ({session.end_reason || session.status.replace('ended_by_', '')}).
        </div>
      )}

      {error && (
        <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      <div
        ref={scrollRef}
        className="bg-white border rounded-lg h-[60vh] overflow-y-auto p-4 space-y-3"
      >
        {session.messages.length === 0 ? (
          <div className="text-center text-gray-400 text-sm pt-12">
            The chat starts when either side sends a message.
          </div>
        ) : (
          session.messages.map((m) => (
            <Bubble
              key={m.id}
              role={m.role}
              content={m.content}
              systemEvent={m.system_event}
              mine={
                (m.role === 'user' && !isSpecialist) ||
                (m.role === 'specialist' && isSpecialist)
              }
              timestamp={m.created_at}
            />
          ))
        )}
      </div>

      {!isEnded && session.typing && session.typing.length > 0 && (
        <div className="mt-2 h-4 text-xs text-gray-500 italic">
          {session.typing.includes('specialist')
            ? `${session.specialist_name || 'IT specialist'} is typing…`
            : `${session.user_name || 'User'} is typing…`}
        </div>
      )}

      {!isEnded && (
        <>
          <div className="mt-3 flex gap-2">
            <input
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                signalTyping(e.target.value.trim().length > 0);
              }}
              onBlur={() => signalTyping(false)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              placeholder="Type your message…"
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              disabled={sending}
            />
            <button
              onClick={() => void send()}
              disabled={sending || !input.trim()}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {sending ? 'Sending…' : 'Send'}
            </button>
          </div>

          <div className="mt-3 flex justify-end gap-2 text-xs">
            {isSpecialist ? (
              <>
                <button
                  onClick={() => void end('resolved')}
                  disabled={ending}
                  className="px-3 py-1.5 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  Resolve &amp; end
                </button>
                <button
                  onClick={() => void end('specialist_ended')}
                  disabled={ending}
                  className="px-3 py-1.5 rounded-md bg-gray-200 text-gray-700 hover:bg-gray-300 disabled:opacity-50"
                >
                  End chat
                </button>
              </>
            ) : (
              <button
                onClick={() => void end('user_left')}
                disabled={ending}
                className="px-3 py-1.5 rounded-md bg-gray-200 text-gray-700 hover:bg-gray-300 disabled:opacity-50"
              >
                End chat
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function Header({
  session,
  onBack,
}: {
  session: SpecialistChatSessionOut;
  onBack: () => void;
}) {
  return (
    <div className="mb-4 flex items-center justify-between">
      <div>
        <button onClick={onBack} className="text-xs text-indigo-600 hover:text-indigo-800 mb-1">
          ← Back
        </button>
        <h1 className="text-xl font-bold text-gray-900">
          {session.ticket_number || 'Live support chat'}
        </h1>
        <p className="text-sm text-gray-500">
          {session.user_name || 'User'} with {session.specialist_name || 'IT specialist'}
        </p>
      </div>
      <span
        className={`px-2 py-0.5 text-xs rounded-full font-medium ${
          session.status === 'active'
            ? 'bg-green-100 text-green-700'
            : session.status === 'idle_warning'
              ? 'bg-amber-100 text-amber-700'
              : 'bg-gray-100 text-gray-500'
        }`}
      >
        {session.status}
      </span>
    </div>
  );
}

function Bubble({
  role,
  content,
  systemEvent,
  mine,
  timestamp,
}: {
  role: 'user' | 'specialist' | 'system';
  content: string;
  systemEvent?: string | null;
  mine: boolean;
  timestamp: string;
}) {
  if (role === 'system') {
    return (
      <div className="text-center text-xs text-gray-400 italic py-1">
        {content}
        {systemEvent && <span className="ml-2 text-gray-300">[{systemEvent}]</span>}
      </div>
    );
  }
  return (
    <div className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[75%] px-3 py-2 rounded-lg text-sm ${
          mine ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-900'
        }`}
      >
        <div className="whitespace-pre-wrap">{content}</div>
        <div className={`mt-1 text-[10px] ${mine ? 'text-indigo-100' : 'text-gray-400'}`}>
          {formatTime(timestamp)}
        </div>
      </div>
    </div>
  );
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/** Human label for the grace window between the idle warning and auto-end. */
function graceMinutes(session: SpecialistChatSessionOut): string {
  const secs = Math.max(60, session.idle_end_seconds - session.idle_warning_seconds);
  const mins = Math.max(1, Math.round(secs / 60));
  return `${mins} minute${mins === 1 ? '' : 's'}`;
}
