import { useEffect } from "react";
import SEOHead from "@/components/SEOHead";
import { getDisplayGatewayUrl } from "@/lib/gatewayClient";

const AgentUiRedirect = () => {
  const agentUiUrl =
    import.meta.env.VITE_AGENT_UI_URL ||
    "https://agent.edoncore.com";
  const gatewayUrl = getDisplayGatewayUrl();

  useEffect(() => {
    try {
      const target = new URL(agentUiUrl);
      const token =
        localStorage.getItem("edon_session_token") ||
        localStorage.getItem("edon_api_key") ||
        "";
      if (gatewayUrl) {
        target.searchParams.set("base", gatewayUrl);
      }
      // Pass token in URL fragment — never sent to servers or in Referer headers.
      if (token) {
        const email = localStorage.getItem("edon_user_email") || "";
        const hashQuery = new URLSearchParams();
        hashQuery.set("token", token);
        if (email) hashQuery.set("email", email);
        target.hash = hashQuery.toString();
      }
      window.location.href = target.toString();
    } catch {
      window.location.href = agentUiUrl;
    }
  }, [agentUiUrl]);

  return (
    <div className="min-h-screen bg-[#0b0d10] text-[#e4e4e7] font-sans flex items-center justify-center">
      <SEOHead title="Opening Agent UI | EDON" description="Redirecting to Agent UI." />
      <div className="text-[13px] text-[#9ca3af]">Opening Agent UI…</div>
    </div>
  );
};

export default AgentUiRedirect;
