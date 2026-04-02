import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    if (import.meta.env.DEV) {
      console.error("ErrorBoundary caught an error:", error, errorInfo);
    }
    const sentry = (window as Window & {
      Sentry?: { captureException?: (err: Error, ctx?: { extra?: ErrorInfo }) => void };
    }).Sentry;
    if (sentry?.captureException) {
      sentry.captureException(error, { extra: errorInfo });
    }
  }

  handleReload = (): void => {
    window.location.reload();
  };

  handleOpenSettings = (): void => {
    window.location.href = "/settings";
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "2rem",
            fontFamily: "system-ui, sans-serif",
            backgroundColor: "#0f0f0f",
            color: "#e5e5e5",
          }}
        >
          <h1 style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>
            Something went wrong
          </h1>
          <p style={{ marginBottom: "1.5rem", color: "#a3a3a3" }}>
            An unexpected error occurred. You can reload the page or open Settings.
          </p>
          <div style={{ display: "flex", gap: "0.75rem" }}>
            <button
              type="button"
              onClick={this.handleReload}
              style={{
                padding: "0.5rem 1rem",
                fontSize: "0.875rem",
                cursor: "pointer",
                backgroundColor: "#3b82f6",
                color: "white",
                border: "none",
                borderRadius: "6px",
              }}
            >
              Reload
            </button>
            <button
              type="button"
              onClick={this.handleOpenSettings}
              style={{
                padding: "0.5rem 1rem",
                fontSize: "0.875rem",
                cursor: "pointer",
                backgroundColor: "#404040",
                color: "white",
                border: "none",
                borderRadius: "6px",
              }}
            >
              Open Settings
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
