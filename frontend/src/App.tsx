import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ChatShell } from "@/components/ChatShell";
import { edonApi } from "@/lib/api";
import Dashboard from "./pages/Dashboard";
import Decisions from "./pages/Decisions";
import Audit from "./pages/Audit";
import Agents from "./pages/Agents";
import Policies from "./pages/Policies";
import Settings from "./pages/Settings";
import Quickstart from "./pages/Quickstart";
import NotFound from "./pages/NotFound";
import Profile from "./pages/Profile";
import ApiKeys from "./pages/ApiKeys";
import Billing from "./pages/Billing";
import Team from "./pages/Team";
import { AccessGate } from "@/components/AccessGate";
import Capabilities from "./pages/Capabilities";
import AdminPanel from "./pages/AdminPanel";
import DemoMode from "./pages/DemoMode";
import PilotKit from "./pages/PilotKit";
import HGIPanel from "./pages/HGIPanel";

const queryClient = new QueryClient();

const AppRoutes = () => {
  const location = useLocation();
  const _hasAnyToken = () =>
    Boolean(
      localStorage.getItem("edon_token") ||
      localStorage.getItem("edon_api_key") ||
      localStorage.getItem("edon_session_token") ||
      (import.meta.env.MODE !== "production" && import.meta.env.VITE_EDON_API_TOKEN)
    );

  const [hasToken, setHasToken] = useState(() => {
    if (typeof window === "undefined") return false;
    return _hasAnyToken();
  });
  const [mockMode, setMockMode] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const refresh = () => {
      setHasToken(_hasAnyToken());
      setMockMode(false);
    };

    refresh();

    const handleStorage = () => refresh();
    const handleAuth = () => refresh();

    window.addEventListener("storage", handleStorage);
    window.addEventListener("edon-auth-updated", handleAuth as EventListener);
    return () => {
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener("edon-auth-updated", handleAuth as EventListener);
    };
  }, [location.pathname]);

  if (!hasToken && location.pathname !== "/settings" && location.pathname !== "/quickstart" && location.pathname !== "/demo" && location.pathname !== "/pilot") {
    return <AccessGate />;
  }

  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/decisions" element={<Decisions />} />
      <Route path="/audit" element={<Audit />} />
      <Route path="/agents" element={<Agents />} />
      <Route path="/policies" element={<Policies />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/quickstart" element={<Quickstart />} />
      <Route path="/profile" element={<Profile />} />
      <Route path="/api-keys" element={<ApiKeys />} />
      <Route path="/billing" element={<Billing />} />
      <Route path="/team" element={<Team />} />
      <Route path="/capabilities" element={<Capabilities />} />
      <Route path="/admin" element={<AdminPanel />} />
      <Route path="/demo" element={<DemoMode />} />
      <Route path="/pilot" element={<PilotKit />} />
      <Route path="/hgi" element={<HGIPanel />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
};

const App = () => {
  useEffect(() => {
    if (typeof window === "undefined") return;

    const params = new URLSearchParams(window.location.search);
    // Also read from URL fragment (#token=...) — sentinel-core passes token
    // in the hash so it is never sent to servers or captured in access logs.
    const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const baseUrl = (params.get("base") || params.get("gateway") || hashParams.get("base") || "").trim();
    const token = (params.get("token") || hashParams.get("token") || "").trim();
    const email = (params.get("email") || hashParams.get("email") || "").trim();
    localStorage.setItem("edon_mock_mode", "false");

    const sanitizeBaseUrl = (value: string) => {
      if (!value) return "";
      try {
        const url = new URL(value);
        if (!["http:", "https:"].includes(url.protocol)) return "";
        return url.origin;
      } catch {
        return "";
      }
    };

    const isLikelyToken = (value: string) => /^[A-Za-z0-9._-]{20,}$/.test(value);

    const safeBaseUrl = sanitizeBaseUrl(baseUrl);
    const safeToken = isLikelyToken(token) ? token : "";

    if (safeBaseUrl) {
      localStorage.setItem("edon_api_base", safeBaseUrl);
      localStorage.setItem("EDON_BASE_URL", safeBaseUrl);
      localStorage.setItem("edon_base_url", safeBaseUrl);
      localStorage.setItem("edon_mock_mode", "false");
    }

    if (email) {
      localStorage.setItem("edon_user_email", email);
    }

    if (safeToken) {
      const existingToken = localStorage.getItem("edon_token") || "";
      const tokenChanged = existingToken && existingToken !== safeToken;
      localStorage.setItem("edon_token", safeToken);
      localStorage.setItem("edon_session_token", safeToken);
      localStorage.setItem("edon_api_key", safeToken);
      localStorage.setItem("edon_mock_mode", "false");

      // Different account — hard reload so all components fetch fresh data
      if (tokenChanged) {
        params.delete("base");
        params.delete("gateway");
        params.delete("token");
        const cleaned = params.toString();
        window.location.replace(`${window.location.pathname}${cleaned ? `?${cleaned}` : ""}`);
        return;
      }
    }

    if (safeBaseUrl || safeToken) {
      params.delete("base");
      params.delete("gateway");
      params.delete("token");
      const cleaned = params.toString();
      // Clear the hash entirely — token has been consumed and stored
      const nextUrl = `${window.location.pathname}${cleaned ? `?${cleaned}` : ""}`;
      window.history.replaceState({}, "", nextUrl);
      window.dispatchEvent(new Event("edon-auth-updated"));
    }

    // Seed localStorage from env vars if no token is stored yet (local dev / demo)
    if (import.meta.env.MODE !== "production") {
      const envToken = (import.meta.env.VITE_EDON_API_TOKEN || "").trim();
      const envBase = (import.meta.env.VITE_EDON_GATEWAY_URL || "").trim();
      const storedToken = (
        localStorage.getItem("edon_token") ||
        localStorage.getItem("edon_api_key") ||
        localStorage.getItem("edon_session_token") ||
        ""
      ).trim();
      if (!storedToken && envToken) {
        localStorage.setItem("edon_token", envToken);
        localStorage.setItem("edon_api_key", envToken);
        localStorage.setItem("edon_session_token", envToken);
        localStorage.setItem("edon_mock_mode", "false");
        if (envBase) {
          localStorage.setItem("edon_api_base", envBase);
          localStorage.setItem("EDON_BASE_URL", envBase);
          localStorage.setItem("edon_base_url", envBase);
        }
        window.dispatchEvent(new Event("edon-auth-updated"));
      }
    }

    // Whenever we have a token, sync email/plan from gateway so agent UI matches marketing site
    const tokenForSync =
      safeToken ||
      (localStorage.getItem("edon_token") ||
        localStorage.getItem("edon_api_key") ||
        localStorage.getItem("edon_session_token") ||
        "").trim();
    if (tokenForSync && /^[A-Za-z0-9._-]{20,}$/.test(tokenForSync)) {
      edonApi
        .getSession()
        .then((session) => {
          if (session?.email) localStorage.setItem("edon_user_email", session.email);
          if (session?.plan) localStorage.setItem("edon_plan", session.plan);
          window.dispatchEvent(new Event("edon-auth-updated"));
        })
        .catch(() => {});

      // Sync active intent_id from gateway so demo panel and decision filters work
      edonApi
        .getHealth()
        .then((h) => {
          const intentId = (h as unknown as { governor?: { active_intent_id?: string } })
            ?.governor?.active_intent_id;
          if (intentId && !localStorage.getItem("edon_active_intent_id")) {
            localStorage.setItem("edon_active_intent_id", intentId);
          }
        })
        .catch(() => {});
    }
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter
          future={{
            v7_startTransition: true,
            v7_relativeSplatPath: true,
          }}
        >
          <ErrorBoundary>
            <AppRoutes />
            <ChatShell />
          </ErrorBoundary>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
};

export default App;
