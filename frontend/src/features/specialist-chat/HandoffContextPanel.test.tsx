import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { HandoffContextPanel } from './HandoffContextPanel';
import { queueApi, type SpecialistHandoffView } from './api';

const VIEW: SpecialistHandoffView = {
  ticket_id: 't1',
  ticket_number: 'ITA-000042',
  issue_summary: 'Mailbox is full and cannot send mail',
  category: 'email/outlook',
  subcategory: 'mailbox-full',
  affected_system: 'outlook',
  urgency: 'high',
  ai_confidence: 0.2,
  ai_resolution_status: 'unresolved',
  escalation_reason: 'AI exhausted grounded steps',
  user_problem_statement: 'Cannot send email, mailbox full',
  detected_intent: 'troubleshoot',
  steps_attempted: [
    { instruction: 'Archive old mail', outcome: 'failed', source_kb_title: 'Mailbox quota' },
  ],
  kb_articles_referenced: [{ article_id: 'kb1', title: 'Mailbox quota', relevance: 0.7 }],
  kb_gap_tags: ['article_suggested_but_unresolved'],
  transcript: {
    id: 's1',
    chat_session_id: 'sess-1',
    captured_at: '2026-06-27T10:00:00Z',
    message_count: 2,
    context_version: '1.0',
    messages: [
      { seq: 0, role: 'employee', content: 'Outlook will not send' },
      { seq: 1, role: 'assistant', content: 'Let us check your quota' },
    ],
  },
  has_structured_context: true,
};

describe('HandoffContextPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the summary, attempted steps and KB gap tags first', async () => {
    vi.spyOn(queueApi, 'getHandoffView').mockResolvedValue(VIEW);
    render(<HandoffContextPanel ticketId="t1" />);

    await waitFor(() =>
      expect(screen.getByText('Mailbox is full and cannot send mail')).toBeInTheDocument(),
    );
    expect(screen.getByText('Archive old mail')).toBeInTheDocument();
    expect(screen.getByText('Article suggested but unresolved')).toBeInTheDocument();
    expect(screen.getByText('AI Handoff Summary')).toBeInTheDocument();
  });

  it('renders the transcript inside a collapsible details element (secondary)', async () => {
    vi.spyOn(queueApi, 'getHandoffView').mockResolvedValue(VIEW);
    const { container } = render(<HandoffContextPanel ticketId="t1" />);

    await waitFor(() =>
      expect(screen.getByText(/Full conversation transcript/)).toBeInTheDocument(),
    );
    const details = container.querySelector('details');
    expect(details).not.toBeNull();
    // Collapsed by default — the summary line lives inside <summary>.
    expect(details?.querySelector('summary')?.textContent).toMatch(/2 messages/);
    expect(screen.getByText('Outlook will not send')).toBeInTheDocument();
  });

  it('shows a degraded note when no structured context exists', async () => {
    vi.spyOn(queueApi, 'getHandoffView').mockResolvedValue({
      ...VIEW,
      has_structured_context: false,
      transcript: null,
    });
    render(<HandoffContextPanel ticketId="t1" />);
    await waitFor(() =>
      expect(
        screen.getByText(/No structured escalation context was captured/),
      ).toBeInTheDocument(),
    );
  });
});
