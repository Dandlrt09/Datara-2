import { Component, type ErrorInfo, type ReactNode } from "react";

export interface ErrorCardProps {
  title: string;
  message?: string;
  error?: unknown;
  onRetry?: () => void;
}

export function ErrorCard({ title, message, error, onRetry }: ErrorCardProps) {
  const displayMessage =
    message ?? (error instanceof Error ? error.message : undefined);

  return (
    <div
      role="alert"
      style={{
        border: "1px solid #e74c3c",
        borderRadius: 8,
        padding: 16,
        background: "#fdf0ef",
        marginBottom: 16,
      }}
    >
      <h3 style={{ margin: "0 0 8px", color: "#c0392b" }}>{title}</h3>
      {displayMessage && (
        <p style={{ margin: "0 0 12px", color: "#555" }}>{displayMessage}</p>
      )}
      {onRetry && (
        <button onClick={onRetry} style={{ padding: "6px 16px" }}>
          Retry
        </button>
      )}
    </div>
  );
}

export function QueryError<T>({
  error,
  onRetry,
  children,
}: {
  error: T | null;
  onRetry?: () => void;
  children: ReactNode;
}): JSX.Element {
  if (error) {
    const title =
      error instanceof Error ? "Something went wrong" : "An error occurred";
    return <ErrorCard title={title} error={error} onRetry={onRetry} />;
  }
  return <>{children}</>;
}

interface RouteErrorBoundaryProps {
  children: ReactNode;
  viewName: string;
}

interface RouteErrorBoundaryState {
  error: Error | null;
}

export class RouteErrorBoundary extends Component<
  RouteErrorBoundaryProps,
  RouteErrorBoundaryState
> {
  constructor(props: RouteErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): RouteErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`${this.props.viewName} render error:`, error, info);
  }

  handleRetry = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      return (
        <ErrorCard
          title={`${this.props.viewName} Error`}
          error={this.state.error}
          onRetry={this.handleRetry}
        />
      );
    }
    return this.props.children;
  }
}