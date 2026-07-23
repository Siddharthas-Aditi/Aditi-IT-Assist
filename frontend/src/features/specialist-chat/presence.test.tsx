import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AvailabilityToggle } from './AvailabilityToggle';
import { queueApi } from './api';

describe('AvailabilityToggle', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows current status and flips on click', async () => {
    vi.spyOn(queueApi, 'getAvailability').mockResolvedValue({
      user_id: 'u1',
      status: 'away',
      last_heartbeat_at: null,
      is_available: false,
    });
    const setSpy = vi.spyOn(queueApi, 'setAvailability').mockResolvedValue({
      user_id: 'u1',
      status: 'available',
      last_heartbeat_at: 't',
      is_available: true,
    });
    render(<AvailabilityToggle />);
    await waitFor(() => expect(screen.getByText(/away/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /go available|available/i }));
    await waitFor(() => expect(setSpy).toHaveBeenCalledWith('available'));
  });
});
