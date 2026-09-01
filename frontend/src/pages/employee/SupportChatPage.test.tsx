/** Tests for the employee support chat page's single-step vs multi-step
 * resolution-steps rendering. This is the LIVE component mounted at
 * `/support` and `/support/chat` (confirmed via `src/app/App.tsx` routing) —
 * `src/pages/ChatPage.tsx` / `ChatPanel` / `ChatBubble` are not wired into
 * any route and are not exercised by real users.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '@/stores/auth-store';
import { liveChatApi } from '@/features/specialist-chat/api';
import type { AuthUser } from '@/types/auth';

import { SupportChatPage } from './SupportChatPage';

const USER_ID = 'user-1';

const FAKE_USER: AuthUser = {
  id: USER_ID,
  email: 'employee@aditi.com',
  full_name: 'Test Employee',
  role: 'employee',
  roles: ['employee'],
};

function seedChatSession(messages: unknown[]): void {
  localStorage.setItem(
    `aditi-chat-session:${USER_ID}`,
    JSON.stringify({
      sessionId: 'sess-1',
      messages,
      waitingForSpecialist: false,
      teamsNotified: false,
      savedAt: Date.now(),
    }),
  );
}

describe('SupportChatPage resolution-steps rendering', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    // jsdom does not implement scrollIntoView — the component calls it on
    // every message-list update to auto-scroll to the latest message.
    Element.prototype.scrollIntoView = vi.fn();
    vi.spyOn(liveChatApi, 'active').mockResolvedValue({ session_id: null });
    useAuthStore.setState({
      user: FAKE_USER,
      token: 'test-token',
      isAuthenticated: true,
    });
  });

  it('renders a one-step reply as prose without a Troubleshooting Steps card', () => {
    seedChatSession([
      {
        id: 'ai-1',
        role: 'assistant',
        content:
          "Let's start simple — open Settings > Accessibility > Keyboard and turn on the " +
          'On-Screen Keyboard to check whether it types. Give that a try and tell me how it goes.',
        timestamp: new Date().toISOString(),
        resolutionSteps: [
          { step_number: 1, instruction: 'Test with the On-Screen Keyboard' },
        ],
      },
    ]);

    render(
      <MemoryRouter>
        <SupportChatPage />
      </MemoryRouter>,
    );

    expect(screen.queryByText(/Troubleshooting Steps/i)).toBeNull();
    expect(screen.getAllByText(/On-Screen Keyboard/i).length).toBeGreaterThan(0);
  });

  it('still renders the Troubleshooting Steps card for a multi-step reply', () => {
    seedChatSession([
      {
        id: 'ai-2',
        role: 'assistant',
        content: "Let's try a couple of things.",
        timestamp: new Date().toISOString(),
        resolutionSteps: [
          { step_number: 1, instruction: 'Restart the app' },
          { step_number: 2, instruction: 'Restart your computer' },
        ],
      },
    ]);

    render(
      <MemoryRouter>
        <SupportChatPage />
      </MemoryRouter>,
    );

    expect(screen.getByText(/Troubleshooting Steps/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Restart the app/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Restart your computer/i).length).toBeGreaterThan(0);
  });

  it('renders KB citations visibly beneath a grounded response', () => {
    seedChatSession([
      {
        id: 'ai-citation',
        role: 'assistant',
        content: 'Archive old mail to free space.',
        timestamp: new Date().toISOString(),
        citations: [
          {
            article_id: 'kb-outlook-42',
            title: 'Mailbox quota management',
            version: '4',
            citation_label: 'KB-OUTLOOK-42',
          },
        ],
      },
    ]);

    render(
      <MemoryRouter>
        <SupportChatPage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Sources')).toBeInTheDocument();
    expect(screen.getByText(/Mailbox quota management · v4/)).toBeInTheDocument();
    expect(screen.getByText('kb-outlook-42')).toBeInTheDocument();
  });

  it('shows suggested and failed troubleshooting steps for the current conversation', () => {
    seedChatSession([
      {
        id: 'ai-history',
        role: 'assistant',
        content: 'Try restarting the app.',
        timestamp: new Date().toISOString(),
        resolutionSteps: [{ step_number: 1, instruction: 'Restart the app' }],
      },
      {
        id: 'user-history',
        role: 'user',
        content: 'Still not working',
        timestamp: new Date().toISOString(),
      },
    ]);

    render(
      <MemoryRouter>
        <SupportChatPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('region', { name: 'Troubleshooting history' })).toBeInTheDocument();
    expect(screen.getByText('Restart the app')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });
});

describe('SupportChatPage quick-reply chips', () => {
  const QUICK_REPLIES = [
    { label: 'That worked', value: 'that worked' },
    { label: 'Still not working', value: 'still not working' },
    { label: 'Talk to a specialist', value: 'talk to a specialist' },
  ];

  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    Element.prototype.scrollIntoView = vi.fn();
    vi.spyOn(liveChatApi, 'active').mockResolvedValue({ session_id: null });
    useAuthStore.setState({
      user: FAKE_USER,
      token: 'test-token',
      isAuthenticated: true,
    });
  });

  it('renders the three quick-reply chips for the last assistant message', () => {
    seedChatSession([
      {
        id: 'ai-1',
        role: 'assistant',
        content: 'Try restarting the app and let me know how it goes.',
        timestamp: new Date().toISOString(),
        resolutionSteps: [{ step_number: 1, instruction: 'Restart the app' }],
        quickReplies: QUICK_REPLIES,
      },
    ]);

    render(
      <MemoryRouter>
        <SupportChatPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('button', { name: 'That worked' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Still not working' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Talk to a specialist' })).toBeInTheDocument();
  });

  it('clicking "That worked" sends that text as the next message', async () => {
    seedChatSession([
      {
        id: 'ai-1',
        role: 'assistant',
        content: 'Try restarting the app and let me know how it goes.',
        timestamp: new Date().toISOString(),
        resolutionSteps: [{ step_number: 1, instruction: 'Restart the app' }],
        quickReplies: QUICK_REPLIES,
      },
    ]);

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-1',
        message_id: 'ai-2',
        content: 'Glad that worked!',
        resolution_steps: [],
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter>
        <SupportChatPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'That worked' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/chat/message'),
        expect.objectContaining({
          body: JSON.stringify({ message: 'that worked', session_id: 'sess-1' }),
        }),
      );
    });

    vi.unstubAllGlobals();
  });

  it('clicking "Still not working" sends that text as the next message', async () => {
    seedChatSession([
      {
        id: 'ai-1',
        role: 'assistant',
        content: 'Try restarting the app and let me know how it goes.',
        timestamp: new Date().toISOString(),
        resolutionSteps: [{ step_number: 1, instruction: 'Restart the app' }],
        quickReplies: QUICK_REPLIES,
      },
    ]);

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-1',
        message_id: 'ai-2',
        content: "Let's try the next step.",
        resolution_steps: [],
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter>
        <SupportChatPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Still not working' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/chat/message'),
        expect.objectContaining({
          body: JSON.stringify({ message: 'still not working', session_id: 'sess-1' }),
        }),
      );
    });

    vi.unstubAllGlobals();
  });

  it('clicking "Talk to a specialist" calls the request-live-agent endpoint', async () => {
    seedChatSession([
      {
        id: 'ai-1',
        role: 'assistant',
        content: 'Try restarting the app and let me know how it goes.',
        timestamp: new Date().toISOString(),
        resolutionSteps: [{ step_number: 1, instruction: 'Restart the app' }],
        quickReplies: QUICK_REPLIES,
      },
    ]);

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        message: 'A support ticket has been created and queued for our IT team.',
        ticket: {
          ticket_id: 't-1',
          ticket_number: 'TCK-1',
          status: 'open',
          priority: 'medium',
          live_agent_requested: true,
        },
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter>
        <SupportChatPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Talk to a specialist' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/chat/request-live-agent'),
        expect.objectContaining({
          body: JSON.stringify({ session_id: 'sess-1' }),
        }),
      );
    });

    vi.unstubAllGlobals();
  });
});
