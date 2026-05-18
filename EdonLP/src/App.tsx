import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { ClerkProvider } from "@clerk/clerk-react";
import ScrollToTopOnRoute from "./components/ScrollToTopOnRoute";
import ProtectedRoute from "./components/ProtectedRoute";
import Index from "./pages/Index";
import Contact from "./pages/Contact";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Account from "./pages/Account";
import OEMApply from "./pages/OEMApply";
import Download from "./pages/Download";
import OEMConfirmation from "./pages/OEMConfirmation";
import OnboardingSuccess from "./pages/OnboardingSuccess";
import ThankYou from "./pages/ThankYou";
import AgentUiRedirect from "./pages/AgentUiRedirect";
import Start from "./pages/Start";
import NotFound from "./pages/NotFound";
import Optimize from "./pages/Optimize";
import Overview from "./pages/Overview";
import About from "./pages/About";
import Careers from "./pages/Careers";
import Press from "./pages/Press";
import Demo from "./pages/Demo";
import SalesPlaybook from "./pages/SalesPlaybook";

const queryClient = new QueryClient();

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

/** Paths that need Clerk (auth/protected). ClerkProvider wraps the whole app so the nav can show Sign In vs Dashboard/Account; protected routes still use ProtectedRoute. */
function pathNeedsClerk(pathname: string): boolean {
  return /^\/(login|signup|account|console|docs|onboarding|thank-you)/.test(pathname);
}

function AppRoutes() {
  const location = useLocation();
  const needsClerk = pathNeedsClerk(location.pathname);
  const routes = (
    <>
      <ScrollToTopOnRoute />
      <Routes>
            {/* Public Routes */}
            <Route path="/" element={<Index />} />
            <Route path="/overview" element={<Overview />} />
            <Route path="/news" element={<Navigate to="/" replace />} />
            <Route path="/standards" element={<Navigate to="/" replace />} />
            <Route path="/about" element={<About />} />
            <Route path="/platforms" element={<Navigate to="/" replace />} />
            <Route path="/contact" element={<Contact />} />
            <Route path="/product" element={<Navigate to="/" replace />} />
            <Route path="/pricing" element={<Navigate to="/contact" replace />} />
            <Route path="/agent-ui" element={<AgentUiRedirect />} />
            <Route path="/monitor" element={<Navigate to="/" replace />} />
            <Route path="/build" element={<Navigate to="/" replace />} />
            <Route path="/optimize" element={<Optimize />} />
            <Route path="/industries/*" element={<Navigate to="/" replace />} />
            <Route path="/careers" element={<Careers />} />
            <Route path="/press" element={<Press />} />
            <Route path="/demo" element={<Demo />} />
            <Route path="/sales" element={<SalesPlaybook />} />
            <Route path="/start" element={<Start />} />
            <Route path="/oem/apply" element={<OEMApply />} />
            <Route path="/request-access" element={<OEMApply />} />
            <Route path="/download" element={<Download />} />
            <Route path="/oem/confirmation" element={<OEMConfirmation />} />
            
            {/* Auth Routes — wildcard required for Clerk path-based routing sub-paths */}
            <Route path="/signup" element={<Signup />} />
            <Route path="/signup/*" element={<Signup />} />
            <Route path="/login" element={<Login />} />
            <Route path="/login/*" element={<Login />} />
            <Route path="/onboarding/success" element={<OnboardingSuccess />} />
            <Route path="/thank-you" element={<ThankYou />} />
            
            {/* Dev platform disabled: redirect to home */}
            <Route path="/docs/*" element={<Navigate to="/" replace />} />
            <Route path="/console" element={<Navigate to="/" replace />} />
            <Route
              path="/account"
              element={
                <ProtectedRoute>
                  <Account />
                </ProtectedRoute>
              }
            />
            <Route
              path="/account/quick-start"
              element={
                <ProtectedRoute>
                  <Account />
                </ProtectedRoute>
              }
            />
            <Route
              path="/account/overview"
              element={
                <ProtectedRoute>
                  <Account />
                </ProtectedRoute>
              }
            />
            <Route
              path="/account/billing"
              element={
                <ProtectedRoute>
                  <Account />
                </ProtectedRoute>
              }
            />
            <Route
              path="/account/tokens"
              element={
                <ProtectedRoute>
                  <Account />
                </ProtectedRoute>
              }
            />
            <Route
              path="/account/integrations"
              element={
                <ProtectedRoute>
                  <Account />
                </ProtectedRoute>
              }
            />
            <Route
              path="/account/agents"
              element={
                <ProtectedRoute>
                  <Account />
                </ProtectedRoute>
              }
            />
            <Route
              path="/account/usage"
              element={
                <ProtectedRoute>
                  <Account />
                </ProtectedRoute>
              }
            />
            <Route
              path="/account/console"
              element={
                <ProtectedRoute>
                  <Account />
                </ProtectedRoute>
              }
            />
            
        {/* Catch-all */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </>
  );
  if (PUBLISHABLE_KEY) {
    return (
      <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">
        {routes}
      </ClerkProvider>
    );
  }
  return routes;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
