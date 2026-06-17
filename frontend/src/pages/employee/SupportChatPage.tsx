/** Employee support chat page — AI-powered professional IT help desk. */

import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Bot, ChevronRight, Send, User } from 'lucide-react';
import { useAuthStore } from '@/stores/auth-store';

interface ResolutionStep {
  step_number: number;
  instruction: string;
  details?: string;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  requiresEscalation?: boolean;
  resolutionSteps?: ResolutionStep[];
  followUpQuestion?: string;
  category?: string;
  confidence?: number;
  isError?: boolean;
}

/** Render text with **bold** markdown → <strong> and newlines → <br>. */
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
  'device-management/intune': 'Device Management',
  'hardware/camera': 'Camera',
  'hardware/other': 'Hardware',
  'software/other': 'Software',
  'network/connectivity': 'Network',
  'access/permissions': 'Access & Permissions',
  'other': 'General IT',
};

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

export function SupportChatPage() {
  const { user, token } = useAuthStore();
  const firstName = user?.full_name?.split(' ')[0] ?? 'there';

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        `Welcome, ${firstName}. I'm the Aditi IT Support Assistant — your dedicated ` +
        `AI-powered help desk agent.\n\n` +
        `I can assist you with a wide range of IT issues including:\n` +
        `• Email & Outlook problems\n` +
        `• VPN and network connectivity\n` +
        `• Video conferencing (Zoom / Teams)\n` +
        `• Hardware and device issues\n` +
        `• Access, permissions, and MFA\n\n` +
        `Please describe the issue you are experiencing and I will guide you through the resolution.`,
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
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
        resolution_steps?: ResolutionStep[];
        follow_up_question?: string;
        issue_category?: string;
        confidence_score?: number;
        detail?: string;
      } = {};

      try {
        data = await res.json();
      } catch { /* non-JSON error body */ }

      if (!res.ok) {
        const errText =
          typeof data.detail === 'string'
            ? data.detail
            : `Service unavailable (${res.status}). Please try again or contact IT support directly.`;
        setMessages((prev) => [
          ...prev,
          { id: `err-${Date.now()}`, role: 'assistant', content: errText, timestamp: new Date(), isError: true },
        ]);
        return;
      }

      if (data.session_id) setSessionId(data.session_id);

      setMessages((prev) => [
        ...prev,
        {
          id: data.message_id ?? `ai-${Date.now()}`,
          role: 'assistant',
          content: data.content ?? 'I received your message and am looking into it.',
          timestamp: new Date(),
          requiresEscalation: data.requires_escalation ?? false,
          resolutionSteps: data.resolution_steps ?? [],
          followUpQuestion: data.follow_up_question ?? undefined,
          category: data.issue_category ?? undefined,
          confidence: data.confidence_score,
        },
      ]);
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
                {/* Subtle "what I understand" chip (AI messages only).
                    The raw confidence % is intentionally NOT shown to employees —
                    it was misleading noise; it's available to IT/admin via the
                    debug trace instead. */}
                {msg.role === 'assistant' && msg.category && (
                  <div className="flex items-center gap-2">
                    <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
                      {CATEGORY_LABELS[msg.category] ?? msg.category}
                    </span>
                  </div>
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

                {/* Escalation banner */}
                {msg.requiresEscalation && (
                  <div className="flex w-full items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5">
                    <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-600" />
                    <div className="flex-1">
                      <p className="text-xs font-semibold text-amber-700">
                        This issue may require specialist assistance
                      </p>
                      <p className="mt-0.5 text-xs text-amber-600">
                        Would you like to be connected with an IT specialist?
                      </p>
                    </div>
                    <button className="ml-2 shrink-0 rounded-lg bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700">
                      Connect
                    </button>
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
            placeholder="Describe your IT issue…"
            disabled={isLoading}
            className="flex-1 rounded-xl border border-gray-300 px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:opacity-60"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isLoading}
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
