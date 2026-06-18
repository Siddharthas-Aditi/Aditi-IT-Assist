/** Employee support chat page — AI-powered professional IT help desk.
 *
 * Hybrid UX: guided category tiles on the welcome screen that each trigger
 * a real backend API call, so users get a familiar click-to-start experience
 * while still getting KB-grounded AI responses.
 * Teams webhook fires automatically when the backend signals escalation.
 */

import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Bot, CheckCircle2, ChevronRight, Send, Ticket, User } from 'lucide-react';
import { useAuthStore } from '@/stores/auth-store';
import { WelcomeCategories } from '@/features/chat/WelcomeCategories';

// Teams Webhook
// Set VITE_TEAMS_WEBHOOK_URL in your .env to enable Teams notifications on
// escalation. Leave blank to skip — the banner still shows.
const TEAMS_WEBHOOK_URL = import.meta.env.VITE_TEAMS_WEBHOOK_URL as string | undefined;

async function notifyTeams(
  userName: string,
  userEmail: string,
  transcript: { role: string; content: string }[],
): Promise<void> {
  if (!TEAMS_WEBHOOK_URL) throw new Error('VITE_TEAMS_WEBHOOK_URL not configured');

  const summary = transcript
    .filter((m) => m.role === 'user')
    .map((m) => `* ${m.content}`)
    .join('\n') || 'No user messages recorded';

  const fullLog = transcript
    .map((m) => `[${m.role === 'assistant' ? 'Bot' : 'User'}] ${m.content}`)
    .join('\n\n');

  const body = {
    type: 'message',
    attachments: [
      {
        contentType: 'application/vnd.microsoft.card.adaptive',
        contentUrl: null,
        content: {
          $schema: 'http://adaptivecards.io/schemas/adaptive-card.json',
          type: 'AdaptiveCard',
          version: '1.4',
          body: [
            { type: 'TextBlock', text: 'IT Support Escalation', weight: 'Bolder', size: 'Large', color: 'Attention' },
            {
              type: 'FactSet', facts: [
                { title: 'User', value: userName || 'Unknown' },
                { title: 'Email', value: userEmail || 'Not provided' },
                { title: 'Time', value: new Date().toLocaleString() },
              ],
            },
            { type: 'TextBlock', text: 'User reported:', weight: 'Bolder', wrap: true },
            { type: 'TextBlock', text: summary, wrap: true, color: 'Warning' },
            { type: 'TextBlock', text: 'Full transcript:', weight: 'Bolder', wrap: true, spacing: 'Medium' },
            { type: 'TextBlock', text: fullLog, wrap: true, fontType: 'Monospace', size: 'Small' },
          ],
          actions: [
            { type: 'Action.OpenUrl', title: 'Open Freshservice', url: 'https://aditiconsulting.freshservice.com' },
          ],
        },
      },
    ],
  };

  const res = await fetch(TEAMS_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Teams webhook responded ${res.status}`);
}

// ── Types ────────────────────────────────────────────────────────────────────

interface ResolutionStep {
  step_number: number;
  instruction: string;
  details?: string;
}

interface TicketRef {
  ticket_id: string;
  ticket_number: string;
  status: string;
  priority: string;
  live_agent_requested: boolean;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  requiresEscalation?: boolean;
  /** Agent offered to raise a ticket + connect a human, awaiting confirmation. */
  escalationOffered?: boolean;
  /** A real ticket was created/queued for this message. */
  ticket?: TicketRef;
  resolutionSteps?: ResolutionStep[];
  followUpQuestion?: string;
  category?: string;
  confidence?: number;
  isError?: boolean;
}

/** Render **bold** markdown and newlines without a full MD library. */
function FormattedText({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={i}>{part.slice(2, -2)}</strong>;
        }
        return part.split('\n').map((line, j, arr) => (
          <span key={`${i}-${j}`}>
            {line}
            {j < arr.length - 1 && <br />}
          </span>
        ));
      })}
    </>
  );
}

const CATEGORY_LABELS: Record<string, string> = {
  'email/outlook': 'Outlook / Email',
  'video-conferencing/zoom': 'Video Conferencing',
  'video-conferencing/teams': 'Microsoft Teams',
  'device-management/intune': 'Device Management',
  'hardware/camera': 'Camera',
  'hardware/audio': 'Audio / Headset',
  'hardware/other': 'Hardware',
  'software/other': 'Software',
  'network/connectivity': 'Network / VPN',
  'access/permissions': 'Access & Permissions',
  'access/sixth_sense': 'Sixth Sense',
  'access/ruddr': 'Ruddr',
  'other': 'General IT',
};

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

// ── Component ────────────────────────────────────────────────────────────────

export function SupportChatPage() {
  const { user, token } = useAuthStore();
  const firstName = user?.full_name?.split(' ')[0] ?? 'there';

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        `Welcome, ${firstName}! I'm your Aditi IT Support Assistant.\n\n` +
        `Select a topic below to get started, or type your issue directly.`,
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [teamsNotified, setTeamsNotified] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Show category tiles only on the welcome screen (no real conversation yet)
  const isWelcomeScreen = messages.length === 1 && messages[0].id === 'welcome';

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  /** Core send — accepts an overrideText so category tiles can fire without typing. */
  const sendMessage = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || isLoading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    if (!overrideText) setInput('');
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chat/message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });

      let data: {
        session_id?: string;
        message_id?: string;
        content?: string;
        requires_escalation?: boolean;
        escalation_offered?: boolean;
        ticket?: TicketRef;
        resolution_steps?: ResolutionStep[];
        follow_up_question?: string;
        issue_category?: string;
        confidence_score?: number;
        detail?: string | { msg?: string; loc?: unknown[] }[];
      } = {};

      try {
        data = await res.json();
      } catch { /* non-JSON error body */ }

      if (!res.ok) {
        const errText =
          typeof data.detail === 'string'
            ? data.detail
            : Array.isArray(data.detail) && data.detail.length > 0
              ? (data.detail[0]?.msg ??
                `Your message couldn't be processed (${res.status}). Please rephrase and try again.`)
              : `Service unavailable (${res.status}). Please try again or contact IT support directly.`;
        setMessages((prev) => [
          ...prev,
          { id: `err-${Date.now()}`, role: 'assistant', content: errText, timestamp: new Date(), isError: true },
        ]);
        return;
      }

      if (data.session_id) setSessionId(data.session_id);

      const assistantMsg: ChatMessage = {
        id: data.message_id ?? `ai-${Date.now()}`,
        role: 'assistant',
        content: data.content ?? 'I received your message and am looking into it.',
        timestamp: new Date(),
        requiresEscalation: data.requires_escalation ?? false,
        escalationOffered: data.escalation_offered ?? false,
        ticket: data.ticket ?? undefined,
        resolutionSteps: data.resolution_steps ?? [],
        followUpQuestion: data.follow_up_question ?? undefined,
        category: data.issue_category ?? undefined,
        confidence: data.confidence_score,
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // Auto-fire Teams webhook on first escalation signal (fire-and-forget)
      if (data.requires_escalation && TEAMS_WEBHOOK_URL && !teamsNotified) {
        setTeamsNotified(true);
        const allMessages = [...messages, userMsg, assistantMsg];
        notifyTeams(
          user?.full_name ?? '',
          user?.email ?? '',
          allMessages.map((m) => ({ role: m.role, content: m.content })),
        ).catch(() => { /* non-critical — ticket flow is the primary escalation path */ });
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content:
            'I was unable to reach the support service. Please check your connection and try again, ' +
            'or contact IT support directly at it-support@aditiconsulting.com.',
          timestamp: new Date(),
          isError: true,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Explicit "Connect with a specialist" action. Creates (if needed) and
   * queues a support ticket for a live IT agent, then shows the confirmation
   * with the real ticket number. Ticket-before-handoff is enforced server-side.
   */
  const connectToAgent = async () => {
    if (connecting || !sessionId) return;
    setConnecting(true);
    try {
      const res = await fetch(`${API_BASE}/chat/request-live-agent`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ session_id: sessionId }),
      });

      let data: { message?: string; ticket?: TicketRef; detail?: string } = {};
      try {
        data = await res.json();
      } catch { /* non-JSON error body */ }

      if (!res.ok) {
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: 'assistant',
            content:
              typeof data.detail === 'string'
                ? data.detail
                : 'I could not reach the IT queue just now. Please try again in a moment.',
            timestamp: new Date(),
            isError: true,
          },
        ]);
        return;
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `agent-${Date.now()}`,
          role: 'assistant',
          content: data.message ?? 'A support ticket has been created and queued for our IT team.',
          timestamp: new Date(),
          ticket: data.ticket,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content:
            'I was unable to reach the support service to connect you. Please try again, or email ' +
            'it-support@aditiconsulting.com.',
          timestamp: new Date(),
          isError: true,
        },
      ]);
    } finally {
      setConnecting(false);
    }
  };

  return (
    <div className="flex h-full flex-col bg-gray-50">
      {/* ── Header ─────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-6 py-4 shadow-sm">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-100">
          <Bot size={18} className="text-indigo-600" />
        </div>
        <div>
          <h1 className="text-base font-semibold text-gray-900">Aditi IT Support Assistant</h1>
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-green-400" />
            <span className="text-xs text-gray-500">Online · AI-powered</span>
          </div>
        </div>
      </div>

      {/* ── Message thread ──────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
        <div className="mx-auto max-w-3xl space-y-5">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
            >
              {/* Avatar */}
              <div
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                  msg.role === 'user'
                    ? 'bg-indigo-600'
                    : msg.isError
                      ? 'bg-red-100'
                      : 'border border-gray-200 bg-white'
                }`}
              >
                {msg.role === 'user' ? (
                  <User size={15} className="text-white" />
                ) : (
                  <Bot size={15} className={msg.isError ? 'text-red-500' : 'text-indigo-600'} />
                )}
              </div>

              {/* Content column */}
              <div
                className={`flex max-w-[78%] flex-col space-y-2 ${
                  msg.role === 'user' ? 'items-end' : 'items-start'
                }`}
              >
                {/* Category chip */}
                {msg.role === 'assistant' && msg.category && (
                  <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
                    {CATEGORY_LABELS[msg.category] ?? msg.category}
                  </span>
                )}

                {/* Main bubble */}
                <div
                  className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                    msg.role === 'user'
                      ? 'rounded-tr-sm bg-indigo-600 text-white'
                      : msg.isError
                        ? 'rounded-tl-sm border border-red-200 bg-red-50 text-red-700'
                        : 'rounded-tl-sm border border-gray-200 bg-white text-gray-800'
                  }`}
                >
                  <FormattedText text={msg.content} />
                </div>

                {/* Category tiles on welcome message only */}
                {msg.id === 'welcome' && isWelcomeScreen && (
                  <WelcomeCategories
                    onSelect={(query) => sendMessage(query)}
                    disabled={isLoading}
                  />
                )}

                {/* Numbered resolution steps */}
                {msg.resolutionSteps && msg.resolutionSteps.length > 0 && (
                  <div className="w-full rounded-xl border border-indigo-100 bg-indigo-50 p-4">
                    <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-indigo-700">
                      Troubleshooting Steps
                    </p>
                    <ol className="space-y-3">
                      {msg.resolutionSteps.map((step) => (
                        <li key={step.step_number} className="flex gap-2.5 text-sm text-gray-700">
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
                            {step.step_number}
                          </span>
                          <div>
                            <FormattedText text={step.instruction} />
                            {step.details && (
                              <p className="mt-0.5 text-xs text-gray-500">
                                <FormattedText text={step.details} />
                              </p>
                            )}
                          </div>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}

                {/* Follow-up question */}
                {msg.followUpQuestion && (
                  <div className="flex items-start gap-2 rounded-xl border border-blue-100 bg-blue-50 px-3 py-2">
                    <ChevronRight size={14} className="mt-0.5 shrink-0 text-blue-600" />
                    <p className="text-xs text-blue-700">
                      <FormattedText text={msg.followUpQuestion} />
                    </p>
                  </div>
                )}

                {/* Escalation banner — offer to create a ticket + connect a human.
                    No ticket exists yet; clicking Connect creates and queues one. */}
                {msg.requiresEscalation && !msg.ticket && (
                  <div className="flex w-full items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5">
                    <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-600" />
                    <div className="flex-1">
                      <p className="text-xs font-semibold text-amber-700">
                        This issue may require specialist assistance
                      </p>
                      <p className="mt-0.5 text-xs text-amber-600">
                        I'll raise a support ticket and connect you with an IT specialist.
                      </p>
                    </div>
                    <button
                      onClick={connectToAgent}
                      disabled={connecting || !sessionId}
                      className="ml-2 shrink-0 rounded-lg bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {connecting ? 'Connecting…' : 'Connect with a specialist'}
                    </button>
                  </div>
                )}

                {/* Ticket created + queued for a human */}
                {msg.ticket && (
                  <div className="flex w-full items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2.5">
                    <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-emerald-600" />
                    <div className="flex-1">
                      <p className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700">
                        <Ticket size={13} /> Ticket {msg.ticket.ticket_number} created
                      </p>
                      <p className="mt-0.5 text-xs text-emerald-600">
                        {msg.ticket.live_agent_requested
                          ? 'Queued for a live IT specialist — they have your full conversation context.'
                          : `Priority: ${msg.ticket.priority} · Status: ${msg.ticket.status}`}
                      </p>
                    </div>
                  </div>
                )}

                {/* Timestamp */}
                <span className="px-1 text-xs text-gray-400">
                  {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            </div>
          ))}

          {/* Typing indicator */}
          {isLoading && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-gray-200 bg-white">
                <Bot size={15} className="text-indigo-600" />
              </div>
              <div className="rounded-2xl rounded-tl-sm border border-gray-200 bg-white px-4 py-3 shadow-sm">
                <div className="flex gap-1.5">
                  <div className="h-2 w-2 animate-bounce rounded-full bg-indigo-400" />
                  <div className="h-2 w-2 animate-bounce rounded-full bg-indigo-400 [animation-delay:0.15s]" />
                  <div className="h-2 w-2 animate-bounce rounded-full bg-indigo-400 [animation-delay:0.3s]" />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* ── Input bar ───────────────────────────────────────────── */}
      <div className="border-t border-gray-200 bg-white px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-3xl gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
            placeholder={isWelcomeScreen ? 'Or type your issue directly…' : 'Describe your IT issue…'}
            maxLength={5000}
            disabled={isLoading}
            className="flex-1 rounded-xl border border-gray-300 px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:opacity-60"
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || isLoading}
            aria-label="Send message"
            className="flex items-center justify-center rounded-xl bg-indigo-600 px-4 py-2.5 text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Send size={17} />
          </button>
        </div>
        <p className="mx-auto mt-2 max-w-3xl text-center text-xs text-gray-400">
          Responses are AI-generated and grounded in Aditi's internal IT knowledge base.
        </p>
      </div>
    </div>
  );
}
