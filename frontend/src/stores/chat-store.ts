/** Chat state management with Zustand. */

import { create } from 'zustand';
import type { ChatMessage } from '../types';
import { chatApi } from '../lib/api';

interface ChatState {
  messages: ChatMessage[];
  sessionId: string | null;
  isLoading: boolean;
  error: string | null;
  escalationStatus: 'idle' | 'sending' | 'sent' | 'failed';

  sendMessage: (content: string) => Promise<void>;
  requestLiveAgent: () => Promise<void>;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [
    {
      id: 'welcome',
      role: 'assistant',
      content:
        "Hello! I'm Aditi IT Assist — your AI-powered IT support agent. Describe any IT issue and I'll guide you to a resolution.",
      timestamp: new Date(),
    },
  ],
  sessionId: null,
  isLoading: false,
  error: null,
  escalationStatus: 'idle',

  sendMessage: async (content: string) => {
    // Guard: ignore empty input or a send already in flight. This prevents the
    // double-submit that caused duplicate user/assistant bubbles in the transcript.
    if (!content.trim() || get().isLoading) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage],
      isLoading: true,
      error: null,
    }));

    try {
      const response = await chatApi.sendMessage(content, get().sessionId ?? undefined);

      const assistantMessage: ChatMessage = {
        // message_id is unique per backend response; fall back defensively.
        id: response.message_id || `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.content,
        confidence: response.confidence_score,
        category: response.issue_category ?? undefined,
        subtype: response.issue_subtype ?? undefined,
        steps: response.resolution_steps,
        requiresEscalation: response.requires_escalation,
        followUpQuestion: response.follow_up_question ?? undefined,
        quickReplies: response.quick_replies ?? undefined,
        conversationPhase: response.conversation_phase ?? undefined,
        resolved: response.resolved ?? undefined,
        debug: (response.debug as ChatMessage['debug']) ?? undefined,
        timestamp: new Date(),
      };

      set((state) => {
        // Idempotency guard: never append an assistant message whose id already
        // exists in the transcript (e.g. a retried request echoing the same id).
        if (state.messages.some((m) => m.id === assistantMessage.id)) {
          return { sessionId: response.session_id, isLoading: false };
        }
        return {
          messages: [...state.messages, assistantMessage],
          sessionId: response.session_id,
          isLoading: false,
        };
      });
    } catch (err) {
      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: 'I encountered an issue connecting to the server. Please try again.',
        timestamp: new Date(),
      };

      set((state) => ({
        messages: [...state.messages, errorMessage],
        isLoading: false,
        error: err instanceof Error ? err.message : 'Unknown error',
      }));
    }
  },

  requestLiveAgent: async () => {
    const sessionId = get().sessionId;
    if (!sessionId) return;
    set({ escalationStatus: 'sending' });
    try {
      const res = await chatApi.requestLiveAgent(sessionId);
      const ticketMsg: ChatMessage = {
        id: `escalation-${Date.now()}`,
        role: 'assistant',
        content: res.message,
        timestamp: new Date(),
      };
      set((state) => ({
        messages: [...state.messages, ticketMsg],
        escalationStatus: 'sent',
      }));
    } catch {
      set({ escalationStatus: 'failed' });
    }
  },

  reset: () =>
    set({
      messages: [
        {
          id: 'welcome',
          role: 'assistant',
          content:
            "Hello! I'm Aditi IT Assist — your AI-powered IT support agent. Describe any IT issue and I'll guide you to a resolution.",
          timestamp: new Date(),
        },
      ],
      sessionId: null,
      isLoading: false,
      error: null,
      escalationStatus: 'idle',
    }),
}));
