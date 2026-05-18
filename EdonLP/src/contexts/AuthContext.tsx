import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { fetchWithTimeout } from "@/lib/fetcher";
import { getGatewayUrl, getGatewayAuthHeaders } from "@/lib/gatewayClient";

type Dict<T = unknown> = Record<string, T>;

interface User {
  id: string;
  email: string;
  tenant_id: string;
  plan: string;
  status: "active" | "trial" | "past_due" | "canceled" | "inactive";
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password?: string) => Promise<void>;
  loginWithMagicLink: (email: string) => Promise<void>;
  logout: () => void;
  signup: (email: string, plan: string) => Promise<{ checkoutUrl: string; tenantId: string }>;
  checkSession: () => Promise<void>;
  isAuthenticated: boolean;
  hasActiveSubscription: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);


export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const navigate = useNavigate();

  // Check for existing session on mount
  useEffect(() => {
    checkSession();
  }, []);

  const checkSession = async () => {
    try {
      const sessionToken = localStorage.getItem("edon_session_token");
      if (!sessionToken) {
        setIsLoading(false);
        return;
      }

      // Validate session with backend - this returns user + subscription status
      // Note: This will fail until backend is running, but that's OK - we'll just show logged out state
      try {
        const response = await fetchWithTimeout(getGatewayUrl("/auth/session"), {
          headers: {
            ...getGatewayAuthHeaders(sessionToken),
          },
          timeoutMs: 8000,
          retries: 2,
        });

        if (response.ok) {
          const userData = await response.json();
          // Backend returns: { id, email, tenant_id, plan, status }
          // status must come from Stripe webhook (source of truth)
          setUser(userData);
        } else {
          localStorage.removeItem("edon_session_token");
          setUser(null);
        }
      } catch (fetchError) {
        // Backend not available - that's OK for local dev
        if (import.meta.env.DEV) {
          console.log("Backend not available, showing logged out state");
        }
        localStorage.removeItem("edon_session_token");
        setUser(null);
      }
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error("Session check failed:", error);
      }
      localStorage.removeItem("edon_session_token");
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  const login = async (email: string, password?: string) => {
    try {
      const response = await fetchWithTimeout(getGatewayUrl("/auth/login"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
        timeoutMs: 8000,
        retries: 2,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Login failed");
      }

      const data = await response.json();
      localStorage.setItem("edon_session_token", data.session_token);
      setUser(data.user);
    } catch (error) {
      console.error("Login error:", error);
      throw error;
    }
  };

  const loginWithMagicLink = async (email: string) => {
    try {
      const response = await fetchWithTimeout(getGatewayUrl("/auth/magic-link"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
        timeoutMs: 8000,
        retries: 2,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Magic link request failed");
      }

      // Magic link sent - show success message
      return;
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error("Magic link error:", error);
      }
      throw error;
    }
  };

  const signup = async (email: string, plan: string, password?: string) => {
    try {
      // Step 1: Create user account and tenant
      const signupResponse = await fetchWithTimeout(getGatewayUrl("/auth/signup"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
        timeoutMs: 10000,
        retries: 2,
      });

      if (!signupResponse.ok) {
        const error = await signupResponse.json();
        throw new Error(error.detail || "Account creation failed");
      }

      const signupData = await signupResponse.json();
      const { tenant_id, session_token } = signupData;

      // Store session token temporarily (will be set after payment)
      localStorage.setItem("edon_session_token", session_token);

      // Step 2: Create Stripe Checkout session
      const checkoutResponse = await fetchWithTimeout(getGatewayUrl("/billing/checkout"), {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          ...getGatewayAuthHeaders(session_token),
        },
        body: JSON.stringify({ 
          tenant_id,
          plan,
          success_url: `${window.location.origin}/onboarding/success`,
          cancel_url: `${window.location.origin}/signup?plan=${plan}`
        }),
        timeoutMs: 10000,
        retries: 2,
      });

      if (!checkoutResponse.ok) {
        const error = await checkoutResponse.json();
        throw new Error(error.detail || "Checkout creation failed");
      }

      const checkoutData = await checkoutResponse.json();
      // Free plan returns checkout_url: null — redirect to onboarding success instead of Stripe
      const checkoutUrl =
        checkoutData.checkout_url ?? (plan === "free" ? `${window.location.origin}/onboarding/success?plan=free` : null);
      return {
        checkoutUrl: checkoutUrl ?? `${window.location.origin}/onboarding/success`,
        tenantId: tenant_id,
      };
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error("Signup error:", error);
      }
      throw error;
    }
  };

  const logout = () => {
    localStorage.removeItem("edon_session_token");
    localStorage.removeItem("edon_api_key_temp");
    localStorage.removeItem("edon_tenant_id_temp");
    setUser(null);
    navigate("/");
  };

  const isAuthenticated = !!user;
  const hasActiveSubscription = user?.status === "active" || user?.status === "trial";

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        login,
        loginWithMagicLink,
        logout,
        signup,
        checkSession,
        isAuthenticated,
        hasActiveSubscription,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
