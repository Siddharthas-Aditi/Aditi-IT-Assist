import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Optional custom fallback. Receives the error and a reset callback. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
  /** Label used in logs to identify which boundary caught the error. */
  boundaryName?: string;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Catches render-time errors in its subtree and shows a recoverable fallback
 * instead of unmounting the whole app to a blank white screen.
 *
 * React has no hook equivalent for `componentDidCatch`, so this stays a class
 * component by necessity. Wrap the app root and each feature/layout outlet so a
 * throw in one area degrades locally rather than taking down every route.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface to the console/observability; a real deployment would forward
    // this to an error-tracking sink. Kept dependency-free here.
    // eslint-disable-next-line no-console
    console.error(
      `[ErrorBoundary${this.props.boundaryName ? `: ${this.props.boundaryName}` : ''}]`,
      error,
      info.componentStack,
    );
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error === null) {
      return this.props.children;
    }

    if (this.props.fallback) {
      return this.props.fallback(error, this.reset);
    }

    return (
      <div
        role="alert"
        className="flex min-h-[50vh] flex-col items-center justify-center gap-4 p-8 text-center"
      >
        <div className="max-w-md space-y-2">
          <h1 className="text-lg font-semibold text-foreground">Something went wrong</h1>
          <p className="text-sm text-muted-foreground">
            An unexpected error occurred while rendering this page. You can try again, or reload
            the application.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={this.reset}
            className="rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-accent"
          >
            Try again
          </button>
          <button
            type="button"
            onClick={() => window.location.assign('/')}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Reload app
          </button>
        </div>
      </div>
    );
  }
}
