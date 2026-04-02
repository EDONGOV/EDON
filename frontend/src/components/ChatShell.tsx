import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { ChatSidebar } from "@/components/ChatSidebar";
import { ChatTrigger } from "@/components/ChatTrigger";

/**
 * Renders the global chat sidebar and trigger (button + bottom bar).
 * Listens for "edon-chat-open" to open the panel from anywhere (e.g. Quickstart).
 * Hides trigger on /agents when agent detail sheet is open (edon-agent-sheet-open).
 */
export function ChatShell() {
  const location = useLocation();
  const [chatOpen, setChatOpen] = useState(false);
  const [agentSheetOpen, setAgentSheetOpen] = useState(false);

  useEffect(() => {
    const handleOpen = () => setChatOpen(true);
    window.addEventListener("edon-chat-open", handleOpen);
    return () => window.removeEventListener("edon-chat-open", handleOpen);
  }, []);

  useEffect(() => {
    const handleSheetOpen = () => setAgentSheetOpen(true);
    const handleSheetClose = () => setAgentSheetOpen(false);
    window.addEventListener("edon-agent-sheet-open", handleSheetOpen);
    window.addEventListener("edon-agent-sheet-close", handleSheetClose);
    return () => {
      window.removeEventListener("edon-agent-sheet-open", handleSheetOpen);
      window.removeEventListener("edon-agent-sheet-close", handleSheetClose);
    };
  }, []);

  const isDemo = location.pathname === "/demo";

  const showTrigger =
    !isDemo &&
    location.pathname !== "/settings" &&
    location.pathname !== "/quickstart" &&
    !chatOpen &&
    !(location.pathname === "/agents" && agentSheetOpen);

  if (isDemo) return null;

  return (
    <>
      <ChatSidebar open={chatOpen} onOpenChange={setChatOpen} />
      <ChatTrigger onOpen={() => setChatOpen(true)} visible={showTrigger} />
    </>
  );
}
