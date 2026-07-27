import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ticketCategoriesApi, ticketsApi } from '@/lib/api';

import { CloseTicketModal } from './CloseTicketModal';

vi.mock('@/lib/api', () => ({
  ticketCategoriesApi: {
    tree: vi.fn(),
  },
  ticketsApi: {
    close: vi.fn(),
  },
}));

const mockTree = vi.mocked(ticketCategoriesApi.tree);
const mockClose = vi.mocked(ticketsApi.close);

const CATEGORY_TREE = {
  categories: [
    {
      id: 'l1-a',
      name: 'Incident',
      level: 1,
      parent_id: null,
      is_active: true,
      sort_order: 0,
      children: [
        {
          id: 'l2-a',
          name: 'Network Connectivity',
          level: 2,
          parent_id: 'l1-a',
          is_active: true,
          sort_order: 0,
          children: [
            {
              id: 'l3-a',
              name: 'VPN',
              level: 3,
              parent_id: 'l2-a',
              is_active: true,
              sort_order: 0,
            },
            {
              id: 'l3-b',
              name: 'Wi-Fi',
              level: 3,
              parent_id: 'l2-a',
              is_active: true,
              sort_order: 1,
            },
          ],
        },
        {
          id: 'l2-b',
          name: 'System Login Issue',
          level: 2,
          parent_id: 'l1-a',
          is_active: true,
          sort_order: 1,
          children: [
            {
              id: 'l3-c',
              name: 'Password Reset',
              level: 3,
              parent_id: 'l2-b',
              is_active: true,
              sort_order: 0,
            },
          ],
        },
        {
          id: 'l2-empty',
          name: 'Unconfigured Area',
          level: 2,
          parent_id: 'l1-a',
          is_active: true,
          sort_order: 2,
          children: [],
        },
      ],
    },
    {
      id: 'l1-b',
      name: 'Service Requests',
      level: 1,
      parent_id: null,
      is_active: true,
      sort_order: 1,
      children: [
        {
          id: 'l2-c',
          name: 'Hardware Request',
          level: 2,
          parent_id: 'l1-b',
          is_active: true,
          sort_order: 0,
          children: [
            {
              id: 'l3-d',
              name: 'Laptop',
              level: 3,
              parent_id: 'l2-c',
              is_active: true,
              sort_order: 0,
            },
          ],
        },
      ],
    },
  ],
};

function renderModal(open = true) {
  const onClose = vi.fn();
  const onClosed = vi.fn();
  render(
    <CloseTicketModal
      ticketId="tkt-1"
      open={open}
      onClose={onClose}
      onClosed={onClosed}
    />,
  );
  return { onClose, onClosed };
}

describe('CloseTicketModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockTree.mockResolvedValue(CATEGORY_TREE);
    mockClose.mockResolvedValue({} as never);
  });

  it('renders required labels', async () => {
    renderModal();
    expect(await screen.findByText('Close ticket')).toBeInTheDocument();
    expect(screen.getByLabelText(/Resolution notes/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Category/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Sub-Category/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Item/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Close notes/i)).toBeInTheDocument();
  });

  it('Confirm disabled when required fields are empty', async () => {
    renderModal();
    await screen.findByLabelText(/^Category/i);
    expect(screen.getByRole('button', { name: /Confirm close/i })).toBeDisabled();
  });

  it('changing category clears subcategory and item', async () => {
    renderModal();
    await screen.findByLabelText(/^Category/i);

    fireEvent.change(screen.getByLabelText(/^Category/i), {
      target: { value: 'Incident' },
    });
    fireEvent.change(screen.getByLabelText(/Sub-Category/i), {
      target: { value: 'Network Connectivity' },
    });
    fireEvent.change(screen.getByLabelText(/^Item/i), {
      target: { value: 'VPN' },
    });

    expect(screen.getByLabelText(/Sub-Category/i)).toHaveValue('Network Connectivity');
    expect(screen.getByLabelText(/^Item/i)).toHaveValue('VPN');

    fireEvent.change(screen.getByLabelText(/^Category/i), {
      target: { value: 'Service Requests' },
    });

    await waitFor(() => {
      expect(screen.getByLabelText(/Sub-Category/i)).toHaveValue('');
      expect(screen.getByLabelText(/^Item/i)).toHaveValue('');
    });
  });

  it('shows empty-items helper and keeps Confirm disabled when subcategory has no items', async () => {
    renderModal();
    await screen.findByLabelText(/^Category/i);

    fireEvent.change(screen.getByLabelText(/^Category/i), {
      target: { value: 'Incident' },
    });
    fireEvent.change(screen.getByLabelText(/Sub-Category/i), {
      target: { value: 'Unconfigured Area' },
    });

    expect(
      screen.getByText(/No items configured — ask an IT admin to add items before closing/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm close/i })).toBeDisabled();
  });

  it('changing subcategory clears item selection', async () => {
    renderModal();
    await screen.findByLabelText(/^Category/i);

    fireEvent.change(screen.getByLabelText(/^Category/i), {
      target: { value: 'Incident' },
    });
    fireEvent.change(screen.getByLabelText(/Sub-Category/i), {
      target: { value: 'Network Connectivity' },
    });
    fireEvent.change(screen.getByLabelText(/^Item/i), {
      target: { value: 'VPN' },
    });

    expect(screen.getByLabelText(/^Item/i)).toHaveValue('VPN');

    fireEvent.change(screen.getByLabelText(/Sub-Category/i), {
      target: { value: 'System Login Issue' },
    });

    await waitFor(() => {
      expect(screen.getByLabelText(/^Item/i)).toHaveValue('');
    });
  });

  it('enables Confirm when all required fields are filled and submits on confirm', async () => {
    const { onClosed } = renderModal();
    await screen.findByLabelText(/^Category/i);

    fireEvent.change(screen.getByLabelText(/Resolution notes/i), {
      target: { value: 'Reset VPN profile and verified connectivity.' },
    });
    fireEvent.change(screen.getByLabelText(/^Category/i), {
      target: { value: 'Incident' },
    });
    fireEvent.change(screen.getByLabelText(/Sub-Category/i), {
      target: { value: 'Network Connectivity' },
    });
    fireEvent.change(screen.getByLabelText(/^Item/i), {
      target: { value: 'VPN' },
    });

    const confirm = screen.getByRole('button', { name: /Confirm close/i });
    expect(confirm).toBeEnabled();

    fireEvent.click(confirm);

    await waitFor(() => {
      expect(mockClose).toHaveBeenCalledWith('tkt-1', {
        resolution_notes: 'Reset VPN profile and verified connectivity.',
        category: 'Incident',
        subcategory: 'Network Connectivity',
        item: 'VPN',
        close_notes: undefined,
      });
      expect(onClosed).toHaveBeenCalled();
    });
  });
});
