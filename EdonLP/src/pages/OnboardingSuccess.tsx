import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Button } from "@/components/ui/button";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useEffect, useState, useRef } from "react";
import { Copy, Check, ExternalLink, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useUser, useAuth } from "@clerk/clerk-react";
import { fetchWithTimeout } from "@/lib/fetcher";
import { getGatewayUrl, getGatewayAuthHeaders, getDisplayGatewayUrl } from "@/lib/gatewayClient";

const OnboardingSuccess = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user, isLoaded: userLoaded } = useUser();
  const { getToken } = useAuth();
  const [copied, setCopied] = useState(false);
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRedirecting, setIsRedirecting] = useState(false);

  // Bug 3 fix: ref guard to prevent double-calls to initiateCheckout
  const checkoutStarted = useRef(false);

  const plan = searchParams.get("plan") || "free";

  useEffect(() => {
    // Stripe redirect return — tenant_id in URL
    const urlTenantId = searchParams.get("tenant_id");
    if (urlTenantId) {
      setTenantId(urlTenantId);
      setIsLoading(false);
      return;
    }

    // Check localStorage/state fallbacks first
    const state = location.state as { tenantId?: string } | null;
    const tempKey = localStorage.getItem("edon_api_key_temp");
    const tempTenant = localStorage.getItem("edon_tenant_id_temp");

    if (tempKey && tempTenant) {
      setApiKey(tempKey);
      setTenantId(tempTenant);
      localStorage.removeItem("edon_api_key_temp");
      localStorage.removeItem("edon_tenant_id_temp");
      setIsLoading(false);
      return;
    }

    if (state?.tenantId) {
      setTenantId(state.tenantId);
      setIsLoading(false);
      return;
    }

    // Wait for Clerk to finish loading
    if (!userLoaded) return;

    // Bug 2 fix: user not signed in after Clerk loaded → redirect to signup
    if (!user) {
      navigate(`/signup?plan=${plan}`, { replace: true });
      return;
    }

    // Bug 3 fix: prevent double-calls with ref guard
    if (!checkoutStarted.current) {
      checkoutStarted.current = true;
      initiateCheckout();
    }
  }, [user, userLoaded, plan, location, searchParams]);

  useEffect(() => {
    if (!isLoading && !isRedirecting && tenantId) {
      navigate("/account", { replace: true });
    }
  }, [isLoading, isRedirecting, tenantId, navigate]);

  const initiateCheckout = async () => {
    if (!user || !user.emailAddresses[0]?.emailAddress) {
      toast.error("User information not available");
      setIsLoading(false);
      return;
    }

    try {
      setIsRedirecting(true);
      const email = user.emailAddresses[0].emailAddress;
      const clerkUserId = user.id;

      // Bug 1 fix: wrap getToken() with 8s timeout
      const clerkToken = await Promise.race([
        getToken(),
        new Promise<null>((_, reject) =>
          setTimeout(() => reject(new Error("Session token timed out. Please refresh and try again.")), 8000)
        ),
      ]);
      if (!clerkToken) {
        throw new Error("Session not ready. Please refresh and try again.");
      }

      const signupResponse = await fetchWithTimeout(getGatewayUrl("/auth/signup"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getGatewayAuthHeaders(clerkToken),
        },
        body: JSON.stringify({
          auth_provider: "clerk",
          auth_subject: clerkUserId,
          email: email,
        }),
        timeoutMs: 10000,
        retries: 2,
      });

      if (!signupResponse.ok) {
        // Bug 5 fix: handle non-JSON error body
        let errorDetail = "Account creation failed";
        try {
          const errBody = await signupResponse.json();
          errorDetail = errBody.detail || errorDetail;
        } catch {
          // non-JSON body — use default message
        }
        throw new Error(errorDetail);
      }

      const signupData = await signupResponse.json();
      const { tenant_id, session_token, api_key } = signupData;

      if (api_key) {
        localStorage.setItem("edon_api_key", api_key);
      }
      localStorage.setItem("edon_session_token", session_token || clerkToken);
      setTenantId(tenant_id);

      // Bug 4 fix: set isLoading false on free plan success
      if (plan === "free") {
        setIsLoading(false);
        setIsRedirecting(false);
        navigate("/account", { replace: true });
        return;
      }

      const checkoutResponse = await fetchWithTimeout(getGatewayUrl("/billing/checkout"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getGatewayAuthHeaders(session_token),
        },
        body: JSON.stringify({
          tenant_id,
          plan,
          success_url: `${window.location.origin}/onboarding/success?tenant_id=${tenant_id}`,
          cancel_url: `${window.location.origin}/signup?plan=${plan}`,
        }),
        timeoutMs: 10000,
        retries: 2,
      });

      if (!checkoutResponse.ok) {
        // Bug 5 fix: handle non-JSON error body
        let errorDetail = "Checkout creation failed";
        try {
          const errBody = await checkoutResponse.json();
          errorDetail = errBody.detail || errorDetail;
        } catch {
          // non-JSON body — use default message
        }
        throw new Error(errorDetail);
      }

      const checkoutData = await checkoutResponse.json();

      if (checkoutData.checkout_url) {
        window.location.href = checkoutData.checkout_url;
      } else {
        throw new Error("No checkout URL returned");
      }
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error("Checkout initiation failed:", error);
      }
      const message = error instanceof Error ? error.message : "Failed to initiate payment. Please try again.";
      toast.error(message);
      setIsLoading(false);
      setIsRedirecting(false);
      checkoutStarted.current = false; // allow retry on error
    }
  };

  const endpoint = tenantId
    ? `${getDisplayGatewayUrl()}/v1/action`
    : "";

  const copyToClipboard = (text: string, type: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success(`${type} copied to clipboard`);
    setTimeout(() => setCopied(false), 2000);
  };

  // Show loading state while initiating checkout
  if (isLoading || isRedirecting) {
    return (
      <div className="min-h-screen bg-white font-sans flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-tactical-cyan" />
          <p className="font-sans text-lg text-gray-600">
            {isRedirecting && plan !== "free" ? "Redirecting to payment..." : "Setting up your account..."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Welcome to EDON | Onboarding"
        description="Your EDON account is ready"
        canonical="https://edoncore.com/onboarding/success"
      />
      <Navigation />

      <section className="bg-gray-50 py-24 px-8 pt-32">
        <div className="max-w-2xl mx-auto">
          <div className="text-center mb-8">
            <div className="w-16 h-16 bg-tactical-cyan rounded-full flex items-center justify-center mx-auto mb-4">
              <Check className="h-8 w-8 text-stealth-bg" />
            </div>
            <h1 className="font-sans text-4xl font-bold text-black mb-2">
              Welcome to EDON
            </h1>
            <p className="font-sans text-lg text-gray-600">
              Your account has been created successfully
            </p>
          </div>

          <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
            <h2 className="font-sans text-xl font-semibold text-black mb-4">
              Your Integration Details
            </h2>

            {tenantId && (
              <div className="mb-4">
                <label className="block font-sans text-sm text-gray-700 uppercase tracking-widest mb-2">
                  EDON Endpoint
                </label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 bg-gray-50 border border-gray-200 px-4 py-2 rounded text-sm text-black font-mono break-all">
                    {endpoint}
                  </code>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => copyToClipboard(endpoint, "Endpoint")}
                    className="flex-shrink-0 rounded-full"
                  >
                    {copied ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                <p className="mt-2 text-xs text-gray-600">
                  Use this endpoint to submit agent actions for governance evaluation
                </p>
              </div>
            )}

            {apiKey && (
              <div className="mb-4">
                <label className="block font-sans text-sm text-gray-700 uppercase tracking-widest mb-2">
                  API Token
                </label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 bg-gray-50 border border-gray-200 px-4 py-2 rounded text-sm text-black font-mono break-all">
                    {apiKey}
                  </code>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => copyToClipboard(apiKey, "API Token")}
                    className="flex-shrink-0 rounded-full"
                  >
                    {copied ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                <p className="mt-2 text-xs text-gray-600">
                  Save this token securely. You can regenerate it in Account → Tokens
                </p>
              </div>
            )}

            {!apiKey && (
              <p className="text-sm text-gray-600 mb-4">
                Your API token will be available in your Account page after payment confirmation.
              </p>
            )}
          </div>

          <div className="flex flex-col sm:flex-row gap-4">
            <Link to="/console" className="flex-1">
              <Button variant="tactical" size="lg" className="w-full font-sans tracking-wider rounded-full">
                Open Console
                <ExternalLink className="h-4 w-4 ml-2" />
              </Button>
            </Link>
            <Link to="/account" className="flex-1">
              <Button variant="outline" size="lg" className="w-full font-sans tracking-wider rounded-full">
                Go to Account
              </Button>
            </Link>
          </div>

          <div className="mt-8 text-center">
            <p className="font-sans text-sm text-gray-600">
              Need help?{" "}
              <Link to="/docs" className="text-tactical-cyan hover:underline">
                View Documentation
              </Link>
              {" or "}
              <Link to="/contact" className="text-tactical-cyan hover:underline">
                Contact Support
              </Link>
            </p>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default OnboardingSuccess;
