import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { Breadcrumbs } from './Breadcrumbs';

function renderCrumbs(ui: React.ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe('Breadcrumbs', () => {
  it('renders every crumb label', () => {
    renderCrumbs(
      <Breadcrumbs
        items={[
          { label: 'User Management', to: '/dashboard/users' },
          { label: 'Jane Doe' },
        ]}
      />,
    );
    expect(screen.getByText('User Management')).toBeInTheDocument();
    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
  });

  it('links parent crumbs but not the current (last) crumb', () => {
    renderCrumbs(
      <Breadcrumbs
        items={[
          { label: 'User Management', to: '/dashboard/users' },
          { label: 'Jane Doe' },
        ]}
      />,
    );
    const parent = screen.getByText('User Management');
    expect(parent.closest('a')).toHaveAttribute('href', '/dashboard/users');

    const current = screen.getByText('Jane Doe');
    expect(current.closest('a')).toBeNull();
    expect(current).toHaveAttribute('aria-current', 'page');
  });

  it('points the home icon at the provided homeTo', () => {
    const { container } = renderCrumbs(
      <Breadcrumbs homeTo="/audit" items={[{ label: 'Audit Logs' }]} />,
    );
    const homeLink = container.querySelector('a[href="/audit"]');
    expect(homeLink).not.toBeNull();
  });
});
