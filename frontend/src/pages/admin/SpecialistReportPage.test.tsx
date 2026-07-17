import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SpecialistReport } from '@/features/admin/types';

const useSpecialistReportMock = vi.fn();
const downloadSpecialistReportMock = vi.fn().mockResolvedValue(undefined);

vi.mock('@/features/admin/api', () => ({
  useSpecialistReport: (...args: unknown[]) => useSpecialistReportMock(...args),
  downloadSpecialistReport: (...args: unknown[]) => downloadSpecialistReportMock(...args),
}));

import { SpecialistReportPage } from './SpecialistReportPage';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const REPORT: SpecialistReport = {
  period_start: '2026-07-01',
  period_end: '2026-07-31',
  rows: [
    {
      agent_id: 'a1',
      agent_name: 'Alice Agent',
      agent_email: 'alice@aditi.com',
      total_tickets: 42,
      reopened: 2,
      avg_resolution_hours: 3.5,
      sla_violations: 1,
      csat_avg: 4.6,
      dsat: 0,
      feedback_responses: 10,
    },
    {
      agent_id: 'a2',
      agent_name: 'Bob Agent',
      agent_email: 'bob@aditi.com',
      total_tickets: 30,
      reopened: 0,
      avg_resolution_hours: 5.1,
      sla_violations: 3,
      csat_avg: null,
      dsat: 2,
      feedback_responses: 0,
    },
  ],
  totals: {
    agent_id: null,
    agent_name: 'Team totals',
    agent_email: null,
    total_tickets: 72,
    reopened: 2,
    avg_resolution_hours: 4.2,
    sla_violations: 4,
    csat_avg: 4.6,
    dsat: 2,
    feedback_responses: 10,
  },
};

describe('SpecialistReportPage', () => {
  beforeEach(() => {
    useSpecialistReportMock.mockReset();
    downloadSpecialistReportMock.mockClear();
    useSpecialistReportMock.mockReturnValue({
      data: REPORT,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
      isFetching: false,
    });
  });

  it('renders both agent rows and the team totals row', () => {
    render(<SpecialistReportPage />, { wrapper });
    expect(screen.getByText('Alice Agent')).toBeInTheDocument();
    expect(screen.getByText('Bob Agent')).toBeInTheDocument();
    expect(screen.getByText('Team totals')).toBeInTheDocument();
  });

  it('renders a null CSAT as the empty-data token', () => {
    render(<SpecialistReportPage />, { wrapper });
    // Bob Agent has csat_avg: null — rendered as an em-dash.
    const bobRow = screen.getByText('Bob Agent').closest('tr');
    expect(bobRow).not.toBeNull();
    expect(bobRow!.textContent).toContain('—');
  });

  it('renders all three charts (tickets, avg resolution, SLA violations)', () => {
    render(<SpecialistReportPage />, { wrapper });
    expect(screen.getByText('Tickets per agent')).toBeInTheDocument();
    expect(screen.getByText('Avg resolution time per agent (hrs)')).toBeInTheDocument();
    expect(screen.getByText('SLA violations per agent')).toBeInTheDocument();
  });

  it('does not crash when an agent has a null avg_resolution_hours', () => {
    useSpecialistReportMock.mockReturnValue({
      data: {
        ...REPORT,
        rows: REPORT.rows.map((r) => ({ ...r, avg_resolution_hours: null })),
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
      isFetching: false,
    });
    render(<SpecialistReportPage />, { wrapper });
    expect(screen.getByText('Avg resolution time per agent (hrs)')).toBeInTheDocument();
    expect(screen.getByText(/no data/i)).toBeInTheDocument();
  });

  it('renders the three download buttons', () => {
    render(<SpecialistReportPage />, { wrapper });
    expect(screen.getByRole('button', { name: /csv/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /excel/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /pdf/i })).toBeInTheDocument();
  });

  it('clicking the CSV button calls downloadSpecialistReport with "csv"', async () => {
    render(<SpecialistReportPage />, { wrapper });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /csv/i }));
      await Promise.resolve();
    });
    expect(downloadSpecialistReportMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      'csv',
    );
  });

  it('shows a loading state', () => {
    useSpecialistReportMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
      isFetching: true,
    });
    render(<SpecialistReportPage />, { wrapper });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('shows an error state', () => {
    useSpecialistReportMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
      isFetching: false,
    });
    render(<SpecialistReportPage />, { wrapper });
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
  });

  it('shows an empty state when there is no row data', () => {
    useSpecialistReportMock.mockReturnValue({
      data: { ...REPORT, rows: [], totals: { ...REPORT.totals, total_tickets: 0 } },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
      isFetching: false,
    });
    render(<SpecialistReportPage />, { wrapper });
    expect(screen.getByText(/no specialist activity/i)).toBeInTheDocument();
  });
});
