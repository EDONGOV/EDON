import { Navigate, useLocation } from "react-router-dom";
import { useAuth, useUser } from "@clerk/clerk-react";
import { useEffect, useState } from "react";
import { fetchWithTimeout } from "@/lib/fetcher";
import { getGatewayUrl, getGatewayAuthHeaders } from "@/lib/gatewayClient";

interface ProtectedRouteProps {
  children: React.ReactNode;
  requireSubscription?: boolean;
}

const ProtectedRoute = ({ children, requireSubscription = false }: ProtectedRouteProps) => {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const location = useLocation();
  const [timedOut, setTimedOut] = useState(false);
  const [checkingSubscription, setCheckingSubscription] = useState(false);
  const [subscriptionValid, setSubscriptionValid] = useState<boolean | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setTimedOut(true), 6000);
    return () => clearTimeout(timer);
  }, []);

  const shouldCheckSubscription = requireSubscription && isLoaded && isSignedIn;

  useEffect(() => {
    if (!shouldCheckSubscription) {
      return;
    }
    let isMounted = true;
    const check = async () => {
      setCheckingSubscription(true);
      try {
        const token = await getToken();
        const response = await fetchWithTimeout(getGatewayUrl("/billing/status"), {
          headers: getGatewayAuthHeaders(token || ""),
          timeoutMs: 8000,
          retries: 2,
        });
        if (!isMounted) return;
        if (response.ok) {
          const data = await response.json();
          const isActive = data.status === "active" || data.status === "trial";
          setSubscriptionValid(isActive);
          return;
        }
      } catch (error) {
        // fall through to Clerk metadata
      }

      const hasActiveSubscription =
        user?.publicMetadata?.subscriptionStatus === "active" ||
        user?.publicMetadata?.subscriptionStatus === "trial";
      if (!isMounted) return;
      setSubscriptionValid(hasActiveSubscription);
    };
    check().finally(() => {
      if (isMounted) setCheckingSubscription(false);
    });
    return () => {
      isMounted = false;
    };
  }, [shouldCheckSubscription, getToken, user]);

  if (!isLoaded) {
    if (timedOut) {
      return <Navigate to="/" replace />;
    }
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-600">Loading...</div>
      </div>
    );
  }

  if (!isSignedIn) {
    // Redirect to home - Clerk will show sign-in modal
    return <Navigate to="/" state={{ from: location }} replace />;
  }

  if (requireSubscription) {
    if (checkingSubscription || subscriptionValid === null) {
      return (
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-gray-600">Checking subscription...</div>
        </div>
      );
    }
    if (!subscriptionValid) {
      return <Navigate to="/account" replace />;
    }
  }

  return <>{children}</>;
};

export default ProtectedRoute;
