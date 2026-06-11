import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ArticleStatus } from '@/types/knowledge';
import { ArticleStatusBadge } from './ArticleStatusBadge';

describe('ArticleStatusBadge', () => {
  it.each<[ArticleStatus, string]>([
    ['draft', 'Draft'],
    ['in_review', 'In Review'],
    ['approved', 'Approved'],
    ['published', 'Published'],
    ['archived', 'Archived'],
  ])('renders %s as "%s"', (status, label) => {
    render(<ArticleStatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});
