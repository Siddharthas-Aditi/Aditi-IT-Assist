/** Chat state management with Zustand. */

import { create } from 'zustand';
import type { ChatMessage } from '../types';
import { chatApi } from '../lib/api';

interface ChatState {
  messages: ChatMessage[];
  sessionId: string | null;
  isLoading: boolean;
  error: string | null;

  sendMessage: (content: string) => Promise<void>;
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

  sendMessage: async (content: string) => {
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
        id: response.message_id,
        role: 'assistant',
        content: response.content,
        confidence: response.confidence_score,
        category: response.issue_category ?? undefined,
        steps: response.resolution_steps,
        requiresEscalation: response.requires_escalation,
        followUpQuestion: response.follow_up_question ?? undefined,
        timestamp: new Date(),
      };

      set((state) => ({
        messages: [...state.messages, assistantMessage],
        sessionId: response.session_id,
        isLoading: false,
      }));
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
    }),
}));
