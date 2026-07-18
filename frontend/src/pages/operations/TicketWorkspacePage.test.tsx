/** Tests for the Reopen button on the IT-staff ticket workspace page.
 *
 * Gating mirrors the backend `POST /tickets/{id}/reopen` guard: only IT
 * staff (it_agent/it_lead/it_admin) may reopen, and only from a terminal
 * ticket status (`resolved`/`closed`).
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '@/stores/auth-store';
import type { AuthUser } from '@/types/auth';

import { TicketWorkspacePage } from './TicketWorkspacePage';

const TICKET_ID = 'tkt-1';

const IT_AGENT: AuthUser = {
  id: 'agent-1',
  email: 'agent@aditi.com',
  full_name: 'Test Agent',
  role: 'it_agent',
  roles: ['it_agent'],
};

const EMPLOYEE: AuthUser = {
  id: 'emp-1',
  email: 'employee@aditi.com',
  full_name: 'Test Employee',
  role: 'employee',
  roles: ['employee'],
};

function baseTicket(status: string) {
  return {
    id: TICKET_ID,
    ticket_number: 'TCK-1001',
    title: 'Mailbox full',
    description: 'Cannot receive email — mailbox over quota.',
    status,
    priority: 'medium',
    category: 'outlook',
    requester_id: 'emp-1',
    assigned_to: 'agent-1',
    created_at: new Date().toISOString(),
    sla_resolution_target: null,
    ai_summary: null,
    resolution_notes: null,
  };
}

function jsonResponse(body: unknown) {
  const text = JSON.stringify(body);
  return {
    ok: true,
    status: 200,
    text: async () => text,
    clone() {
      return this;
    },
  };
}

function mockTicketDetailFetch(status: string): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes(`/tickets/${TICKET_ID}/reopen`) && method === 'POST') {
      return Promise.resolve(
        jsonResponse({ id: TICKET_ID, ticket_number: 'TCK-1001', status: 'in_progress' }),
      );
    }
    if (url.includes(`/tickets/${TICKET_ID}`) && method === 'GET') {
      return Promise.resolve(
        jsonResponse({
          ticket: baseTicket(status),
          comments: [],
          events: [],
        }),
      );
    }
    return Promise.resolve(jsonResponse({}));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock as unknown as ReturnType<typeof vi.fn>;
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={[`/operations/tickets/${TICKET_ID}`]}>
      <Routes>
        <Route path="/operations/tickets/:id" element={<TicketWorkspacePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('TicketWorkspacePage — Reopen button', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders and calls the reopen API for a resolved ticket as IT staff', async () => {
    useAuthStore.setState({ user: IT_AGENT, token: 'test-token', isAuthenticated: true });
    const fetchMock = mockTicketDetailFetch('resolved');
    renderPage();

    const button = await screen.findByRole('button', { name: /reopen ticket/i });
    expect(button).toBeInTheDocument();

    fireEvent.click(button);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/tickets/${TICKET_ID}/reopen`),
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  it('does not render for a non-resolved ticket as IT staff', async () => {
    useAuthStore.setState({ user: IT_AGENT, token: 'test-token', isAuthenticated: true });
    mockTicketDetailFetch('in_progress');
    renderPage();

    await screen.findByText('Mailbox full');
    expect(screen.queryByRole('button', { name: /reopen ticket/i })).toBeNull();
  });

  it('does not render for a resolved ticket when the user is not IT staff', async () => {
    useAuthStore.setState({ user: EMPLOYEE, token: 'test-token', isAuthenticated: true });
    mockTicketDetailFetch('resolved');
    renderPage();

    await screen.findByText('Mailbox full');
    expect(screen.queryByRole('button', { name: /reopen ticket/i })).toBeNull();
  });
});
