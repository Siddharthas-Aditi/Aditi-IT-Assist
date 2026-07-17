import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { ErrorBoundary } from './ErrorBoundary';

function Boom({ explode }: { explode: boolean }): JSX.Element {
  if (explode) {
    throw new Error('kaboom');
  }
  return <div>safe content</div>;
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    // Silence the expected componentDidCatch console.error noise.
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <div>hello world</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText('hello world')).toBeInTheDocument();
  });

  it('shows the fallback UI when a child throws', () => {
    render(
      <ErrorBoundary>
        <Boom explode />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('renders a custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={(error) => <div>custom: {error.message}</div>}>
        <Boom explode />
      </ErrorBoundary>,
    );
    expect(screen.getByText('custom: kaboom')).toBeInTheDocument();
  });

  it('recovers via reset once the child no longer throws', () => {
    // A mutable flag the child reads on each render. Flip it to false before
    // clicking "Try again"; reset() clears the boundary's error state and
    // re-renders the same child, which now returns safely.
    const flag = { explode: true };
    function Child(): JSX.Element {
      if (flag.explode) {
        throw new Error('kaboom');
      }
      return <div>safe content</div>;
    }
    render(
      <ErrorBoundary>
        <Child />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();

    flag.explode = false;
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(screen.getByText('safe content')).toBeInTheDocument();
  });
});
