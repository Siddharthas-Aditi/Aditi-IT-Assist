import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it } from 'vitest';

import { useAuthStore } from '@/stores/auth-store';
import type { ArticleDetail, LifecycleAction } from '@/types/knowledge';
import { LifecycleActions } from './LifecycleActions';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function setRole(role: string) {
  useAuthStore.setState({
    user: { id: '1', email: 'x@y.z', full_name: 'X', role: role as never, roles: [role as never] },
    token: 'tok',
    isAuthenticated: true,
  });
}

function article(actions: LifecycleAction[]): ArticleDetail {
  return { id: 'a1', title: 'T', available_actions: actions } as ArticleDetail;
}

afterEach(() => useAuthStore.setState({ user: null, token: null, isAuthenticated: false }));

describe('LifecycleActions role-based visibility', () => {
  it('agent sees submit_for_review but not publish', () => {
    setRole('it_agent');
    render(<LifecycleActions article={article(['submit_for_review', 'archive'])} />, { wrapper });
    expect(screen.getByText('Submit for Review')).toBeInTheDocument();
    // agent lacks knowledge:archive
    expect(screen.queryByText('Archive')).not.toBeInTheDocument();
  });

  it('lead can publish an approved article', () => {
    setRole('it_lead');
    render(<LifecycleActions article={article(['publish', 'archive'])} />, { wrapper });
    expect(screen.getByText('Publish')).toBeInTheDocument();
    expect(screen.getByText('Archive')).toBeInTheDocument();
  });

  it('employee sees no actions', () => {
    setRole('employee');
    render(<LifecycleActions article={article(['submit_for_review', 'publish'])} />, { wrapper });
    expect(screen.getByText(/No actions available/i)).toBeInTheDocument();
  });

  it('agent can approve only if available and permitted (cannot)', () => {
    setRole('it_agent');
    render(<LifecycleActions article={article(['approve'])} />, { wrapper });
    expect(screen.getByText(/No actions available/i)).toBeInTheDocument();
  });
});
