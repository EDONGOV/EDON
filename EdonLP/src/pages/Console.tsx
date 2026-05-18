import { useEffect, useState } from "react";
import { useAuth, useUser } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";
import SEOHead from "@/components/SEOHead";
import { getDisplayGatewayUrl } from "@/lib/gatewayClient";

const Console = () => {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const GATEWAY_URL = getDisplayGatewayUrl();
  const CONSOLE_URL =
    import.meta.env.VITE_CONSOLE_URL ||
    import.meta.env.VITE_AGENT_UI_URL ||
    "https://console.edoncore.com";

  useEffect(() => {
    if (!isLoaded) return;

    if (!isSignedIn) {
      navigate("/login");
      return;
    }

    const doRedirect = async () => {
      try {
        const edonKey = localStorage.getItem("edon_api_key");
        const clerkToken = await getToken();
        const token = edonKey || clerkToken || "";

        const email = user?.emailAddresses?.[0]?.emailAddress || "";
        const targetUrl = new URL(CONSOLE_URL);
        targetUrl.searchParams.set("base", GATEWAY_URL);
        if (token) {
          // Fragment is never sent to servers or captured in access logs
          const hashQuery = new URLSearchParams();
          hashQuery.set("token", token);
          if (email) hashQuery.set("email", email);
          targetUrl.hash = hashQuery.toString();
        }
        window.location.href = targetUrl.toString();
      } catch {
        setError("Failed to open console. Please try again.");
      }
    };

    doRedirect();
  }, [isLoaded, isSignedIn, getToken, navigate, GATEWAY_URL, CONSOLE_URL, user]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <SEOHead title="Console | EDON" description="Access your EDON Console" canonical="https://edoncore.com/console" />
        <div className="text-center max-w-md px-4 space-y-4">
          <p className="text-red-600 text-sm">{error}</p>
          <button
            onClick={() => { setError(null); window.location.reload(); }}
            className="bg-black text-white text-sm font-medium px-6 py-2 rounded-full hover:bg-neutral-800 transition-colors"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <SEOHead title="Console | EDON" description="Access your EDON Console" canonical="https://edoncore.com/console" />
      <div className="text-center space-y-3">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-black mx-auto" />
        <p className="text-gray-500 text-sm">Opening Console…</p>
      </div>
    </div>
  );
};

export default Console;
