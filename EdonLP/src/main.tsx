import { StrictMode, Component, ReactNode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

// Clerk is loaded only on auth/protected routes (see App.tsx) so the marketing site
// does not run Clerk or restore session until the user goes to login/signup/account/console/docs.
const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
if (import.meta.env.PROD && !PUBLISHABLE_KEY) {
  console.warn(
    "Missing VITE_CLERK_PUBLISHABLE_KEY. Set it in Vercel → Environment Variables for auth routes to work."
  );
}

class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "sans-serif", padding: "2rem", textAlign: "center" }}>
          <div>
            <p style={{ fontSize: "15px", color: "#374151", marginBottom: "12px" }}>Something went wrong. Please refresh the page.</p>
            <button
              onClick={() => window.location.reload()}
              style={{ fontSize: "13px", padding: "8px 20px", borderRadius: "9999px", border: "1px solid #d1d5db", background: "#fff", cursor: "pointer" }}
            >
              Refresh
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
);
