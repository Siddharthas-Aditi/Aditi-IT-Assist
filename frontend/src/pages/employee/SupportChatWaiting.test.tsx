import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { WaitingBanner } from './WaitingBanner';

describe('WaitingBanner', () => {
  it('shows connecting message when handoff_state=connecting', () => {
    render(<WaitingBanner handoffState="connecting" onCancel={() => {}} />);
    expect(screen.getByText(/connecting you/i)).toBeInTheDocument();
  });

  it('shows busy message when handoff_state=busy', () => {
    render(<WaitingBanner handoffState="busy" onCancel={() => {}} />);
    expect(screen.getByText(/busy at the moment/i)).toBeInTheDocument();
  });

  it('shows connected message when handoff_state=connected', () => {
    render(<WaitingBanner handoffState="connected" onCancel={() => {}} />);
    expect(screen.getByText(/specialist has joined/i)).toBeInTheDocument();
  });

  it('shows fallback message when handoff_state=fallback', () => {
    render(<WaitingBanner handoffState="fallback" onCancel={() => {}} />);
    expect(screen.getByText(/logged|follow up/i)).toBeInTheDocument();
  });

  it('invokes onCancel when the cancel button is clicked (non-terminal states)', async () => {
    const onCancel = vi.fn();
    render(<WaitingBanner handoffState="connecting" onCancel={onCancel} />);
    screen.getByRole('button', { name: /cancel/i }).click();
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('hides the cancel button once handoff_state=fallback (terminal state)', () => {
    render(<WaitingBanner handoffState="fallback" onCancel={() => {}} />);
    expect(screen.queryByRole('button', { name: /cancel/i })).not.toBeInTheDocument();
  });
});
