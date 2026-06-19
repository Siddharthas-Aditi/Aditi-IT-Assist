import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { RoleBadge, SeverityBadge, StatusBadge } from './badges';

describe('RoleBadge', () => {
  it.each([
    ['it_admin', 'IT Admin'],
    ['it_agent', 'IT Agent'],
    ['security_auditor', 'Security Auditor'],
    ['employee', 'Employee'],
  ])('renders %s as "%s"', (role, label) => {
    render(<RoleBadge role={role} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('falls back to the raw role name for unknown roles', () => {
    render(<RoleBadge role="custom_role" />);
    expect(screen.getByText('custom_role')).toBeInTheDocument();
  });
});

describe('StatusBadge', () => {
  it('shows Active / Suspended', () => {
    const { rerender } = render(<StatusBadge active />);
    expect(screen.getByText('Active')).toBeInTheDocument();
    rerender(<StatusBadge active={false} />);
    expect(screen.getByText('Suspended')).toBeInTheDocument();
  });
});

describe('SeverityBadge', () => {
  it.each(['info', 'warning', 'error', 'critical'])('renders %s', (sev) => {
    render(<SeverityBadge severity={sev} />);
    expect(screen.getByText(sev)).toBeInTheDocument();
  });
});
