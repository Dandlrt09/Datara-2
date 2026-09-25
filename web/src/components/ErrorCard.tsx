import { Component, type ErrorInfo, type ReactNode } from "react";
import { colors } from "../design/tokens";

/** Visual family of the card; selects the token triple from tokens.ts. */
export type ErrorCardVariant = "error" | "warning" | "info";

/** Per-variant color triple consumed from the design tokens. The error
 * family is seeded from the literals this component previously hardcoded,
 * so existing consumers (no variant passed) render pixel-identically. */
const VARIANT_COLORS: Record<
  ErrorCardVariant,
  { border: string; heading: string; surface: string }
> = {
  error: {
    border: colors.danger,
    heading: colors.dangerText,
    surface: colors.dangerSurface,
  },
  warning: {
    border: colors.warning,
    heading: colors.warningText,
    surface: colors.warningSurface,
  },
  info: {
    border: colors.info,
    heading: colors.infoText,
    surface: colors.infoSurface,
  },
};

export interface ErrorCardProps {
  title: string;
  message?: string;
  error?: unknown;
  onRetry?: () => void;
  /** Visual family; defaults to the original danger treatment. */
  variant?: ErrorCardVariant;
  /** Label for the retry button; defaults to the original "Retry". */
  actionLabel?: string;
  /** Optional content rendered between the message and the retry action. */
  children?: ReactNode;
}

export function ErrorCard({
  title,
  message,
  error,
  onRetry,
  variant = "error",
  actionLabel = "Retry",
  children,
}: ErrorCardProps) {
  const displayMessage =
    message ?? (error instanceof Error ? error.message : undefined);
  const variantColors = VARIANT_COLORS[variant];

  return (
    <div
      role="alert"
      style={{
        border: `1px solid ${variantColors.border}`,
        borderRadius: 8,
        padding: 16,
        background: variantColors.surface,
        marginBottom: 16,
      }}
    >
      <h3 style={{ margin: "0 0 8px", color: variantColors.heading }}>
        {title}
      </h3>
      {displayMessage && (
        <p style={{ margin: "0 0 12px", color: "#555" }}>{displayMessage}</p>
      )}
      {children}
      {onRetry && (
        <button onClick={onRetry} style={{ padding: "6px 16px" }}>
          {actionLabel}
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