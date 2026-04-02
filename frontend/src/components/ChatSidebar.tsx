import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { X, GripVertical, Send, Plus, Bot, User, Sparkles, RefreshCw } from "lucide-react";
import { edonApi, isMockMode, getToken } from "@/lib/api";
import {
  fetchDashboardContext,
  getDashboardAwareReply,
  buildSystemPrompt,
  buildGreeting,
  type DashboardContext,
} from "@/lib/dashboardContext";

/* ─────────────────────────────────────────────
   Types
───────────────────────────────────────────── */
type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
};

type ChatThread = {
  id: string;
  title: string;
  messages: Message[];
};

/* ─────────────────────────────────────────────
   Simple markdown renderer
───────────────────────────────────────────── */
function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let listBuffer: string[] = [];
  let codeBuffer: string[] = [];
  let inCode = false;
  let key = 0;

  const flushList = () => {
    if (listBuffer.length === 0) return;
    nodes.push(
      <ul key={key++} className="my-1.5 space-y-0.5 pl-3">
        {listBuffer.map((item, i) => (
          <li key={i} className="flex gap-2">
            <span className="text-primary mt-0.5">•</span>
            <span>{inlineRender(item)}</span>
          </li>
        ))}
      </ul>
    );
    listBuffer = [];
  };

  const flushCode = () => {
    if (codeBuffer.length === 0) return;
    nodes.push(
      <pre key={key++} className="my-2 bg-muted border border-border rounded-md px-3 py-2 text-[11px] font-mono text-green-600 dark:text-green-300 overflow-x-auto">
        {codeBuffer.join("\n")}
      </pre>
    );
    codeBuffer = [];
  };

  for (const line of lines) {
    if (line.startsWith("```")) {
      if (inCode) { flushCode(); inCode = false; }
      else { flushList(); inCode = true; }
      continue;
    }
    if (inCode) { codeBuffer.push(line); continue; }
    if (line.startsWith("### ")) {
      flushList();
      nodes.push(<p key={key++} className="text-[11px] font-semibold text-foreground/90 mt-3 mb-1">{line.slice(4)}</p>);
    } else if (line.startsWith("## ")) {
      flushList();
      nodes.push(<p key={key++} className="text-xs font-bold text-foreground mt-3 mb-1">{line.slice(3)}</p>);
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      listBuffer.push(line.slice(2));
    } else if (line.trim() === "") {
      flushList();
      nodes.push(<div key={key++} className="h-1" />);
    } else {
      flushList();
      nodes.push(<p key={key++} className="leading-relaxed">{inlineRender(line)}</p>);
    }
  }
  flushList();
  if (inCode) flushCode();
  return nodes;
}

function inlineRender(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*(.+?)\*\*|`([^`]+)`|\*(.+?)\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push(<span key={k++}>{text.slice(last, m.index)}</span>);
    if (m[2]) parts.push(<strong key={k++} className="font-semibold text-foreground">{m[2]}</strong>);
    else if (m[3]) parts.push(<code key={k++} className="bg-secondary text-primary rounded px-1 text-[10px] font-mono">{m[3]}</code>);
    else if (m[4]) parts.push(<em key={k++} className="italic text-foreground/80">{m[4]}</em>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(<span key={k++}>{text.slice(last)}</span>);
  return parts.length === 1 ? parts[0] : <>{parts}</>;
}

/* ─────────────────────────────────────────────
   LLM providers
───────────────────────────────────────────── */
type LLMProvider = "anthropic" | "openai" | "openrouter" | "gateway";

interface LLMConfig {
  provider: LLMProvider;
  apiKey: string;
  model: string;
}

function getLLMConfig(): LLMConfig {
  return {
    provider: (localStorage.getItem("edon_chat_provider") as LLMProvider) || "openrouter",
    apiKey: localStorage.getItem("edon_chat_api_key") || "",
    model: localStorage.getItem("edon_chat_model") || "",
  };
}

const OPENROUTER_KEY = "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";
const OPENROUTER_MODELS = [
  "deepseek/deepseek-chat-v3-0324:free",
  "deepseek/deepseek-r1:free",
  "qwen/qwen-2.5-72b-instruct:free",
  "meta-llama/llama-3.3-70b-instruct:free",
  "nousresearch/hermes-3-llama-3.1-405b:free",
  "mistralai/mistral-7b-instruct:free",
  "google/gemma-3-27b-it:free",
];

async function callOpenRouterStream(
  messages: Message[],
  systemPrompt: string,
  onChunk: (accumulated: string) => void
): Promise<string> {
  let lastError = "";
  for (const model of OPENROUTER_MODELS) {
    const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${OPENROUTER_KEY}`,
        "Content-Type": "application/json",
        "HTTP-Referer": typeof window !== "undefined" ? window.location.origin : "https://edon.ai",
        "X-Title": "EDON Assistant",
      },
      body: JSON.stringify({
        model,
        stream: true,
        messages: [
          { role: "system", content: systemPrompt },
          ...messages.map((m) => ({ role: m.role, content: m.content })),
        ],
      }),
    });
    if (!res.ok) {
      const err = await res.text();
      lastError = `OpenRouter error ${res.status} (${model}): ${err.slice(0, 200)}`;
      continue;
    }
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let full = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const raw = decoder.decode(value, { stream: true });
      for (const line of raw.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6).trim();
        if (data === "[DONE]") continue;
        try {
          const parsed = JSON.parse(data);
          const content = parsed.choices?.[0]?.delta?.content;
          if (content) { full += content; onChunk(full); }
        } catch { /* skip malformed SSE chunks */ }
      }
    }
    return full || "No response.";
  }
  throw new Error(lastError || "All OpenRouter models unavailable.");
}

async function callAnthropic(messages: Message[], systemPrompt: string, apiKey: string, model: string): Promise<string> {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      "anthropic-dangerous-allow-browser": "true",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: model || "claude-sonnet-4-6",
      max_tokens: 1024,
      system: systemPrompt,
      messages: messages.map((m) => ({ role: m.role, content: m.content })),
    }),
  });
  if (!res.ok) throw new Error(`Anthropic error ${res.status}: ${(await res.text()).slice(0, 120)}`);
  const data = await res.json();
  return data.content?.[0]?.text ?? "No response.";
}

async function callOpenAI(messages: Message[], systemPrompt: string, apiKey: string, model: string): Promise<string> {
  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "content-type": "application/json" },
    body: JSON.stringify({
      model: model || "gpt-4o",
      messages: [{ role: "system", content: systemPrompt }, ...messages.map((m) => ({ role: m.role, content: m.content }))],
    }),
  });
  if (!res.ok) throw new Error(`OpenAI error ${res.status}: ${(await res.text()).slice(0, 120)}`);
  const data = await res.json();
  return data.choices?.[0]?.message?.content ?? "No response.";
}

/* ─────────────────────────────────────────────
   Typing indicator
───────────────────────────────────────────── */
function TypingDots() {
  return (
    <div className="flex items-center gap-1 px-1 py-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-primary/60"
          style={{ animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite` }}
        />
      ))}
    </div>
  );
}

/* ─────────────────────────────────────────────
   Suggested prompts
───────────────────────────────────────────── */
const SUGGESTED = [
  "How many actions were blocked in the last 24h?",
  "Why are agents being blocked?",
  "What's the active policy pack?",
  "Show me recent blocked decisions",
  "Which agent has the highest block rate?",
  "Is the gateway healthy?",
];

const WIDTH_KEY = "edon_chat_sidebar_width";

/* ─────────────────────────────────────────────
   ChatSidebar
───────────────────────────────────────────── */
export function ChatSidebar({ open, onOpenChange }: { open: boolean; onOpenChange: (next: boolean) => void }) {
  const [width, setWidth] = useState(440);
  const [isResizing, setIsResizing] = useState(false);
  const [threads, setThreads] = useState<ChatThread[]>([{ id: "chat-1", title: "New chat", messages: [] }]);
  const [activeThreadId, setActiveThreadId] = useState("chat-1");
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [llmConfig, setLlmConfig] = useState<LLMConfig>(getLLMConfig);
  const startX = useRef(0);
  const startWidth = useRef(440);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const stored = localStorage.getItem(WIDTH_KEY);
    if (stored) { const n = Number(stored); if (!Number.isNaN(n)) setWidth(n); }
  }, []);

  useEffect(() => { localStorage.setItem(WIDTH_KEY, String(width)); }, [width]);

  useEffect(() => {
    const refresh = () => setLlmConfig(getLLMConfig());
    window.addEventListener("edon-chat-config-updated", refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener("edon-chat-config-updated", refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  const greetedThreads = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!open) return;
    const thread = threads.find((t) => t.id === activeThreadId);
    if (!thread || thread.messages.length > 0) return;
    if (greetedThreads.current.has(activeThreadId)) return;
    greetedThreads.current.add(activeThreadId);
    const greetId = `a-greet-${Date.now()}`;
    setThreads((prev) =>
      prev.map((t) =>
        t.id === activeThreadId
          ? { ...t, messages: [{ id: greetId, role: "assistant" as const, content: "__loading__", timestamp: new Date() }] }
          : t
      )
    );
    fetchDashboardContext()
      .then((ctx) => {
        setThreads((prev) =>
          prev.map((t) =>
            t.id === activeThreadId
              ? { ...t, messages: [{ id: greetId, role: "assistant" as const, content: buildGreeting(ctx), timestamp: new Date() }] }
              : t
          )
        );
      })
      .catch(() => {
        const hour = new Date().getHours();
        const timeGreeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
        const displayName = localStorage.getItem("edon_display_name") || "";
        const firstName = displayName ? displayName.split(" ")[0] : null;
        const nameGreet = firstName ? `, ${firstName}` : "";
        setThreads((prev) =>
          prev.map((t) =>
            t.id === activeThreadId
              ? { ...t, messages: [{ id: greetId, role: "assistant" as const, content: `${timeGreeting}${nameGreet}! I'm your EDON governance assistant. How can I help you today?`, timestamp: new Date() }] }
              : t
          )
        );
      });
  }, [open, activeThreadId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 150); }, [open]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [threads, isLoading]);

  useEffect(() => {
    if (!isResizing) return;
    const handleMove = (e: MouseEvent) => {
      const delta = startX.current - e.clientX;
      setWidth(Math.min(720, Math.max(320, startWidth.current + delta)));
    };
    const handleUp = () => setIsResizing(false);
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => { window.removeEventListener("mousemove", handleMove); window.removeEventListener("mouseup", handleUp); };
  }, [isResizing]);

  const handleResizeStart = (e: React.MouseEvent) => {
    startX.current = e.clientX;
    startWidth.current = width;
    setIsResizing(true);
  };

  const activeThread = useMemo(
    () => threads.find((t) => t.id === activeThreadId) || threads[0],
    [threads, activeThreadId]
  );

  const updateLastAssistant = useCallback((threadId: string, content: string) => {
    setThreads((prev) =>
      prev.map((t) => {
        if (t.id !== threadId) return t;
        const msgs = [...t.messages];
        const last = msgs[msgs.length - 1];
        if (last?.role === "assistant") msgs[msgs.length - 1] = { ...last, content };
        return { ...t, messages: msgs };
      })
    );
  }, []);

  const sendMessage = useCallback(
    async (userText: string) => {
      if (!userText.trim() || isLoading) return;
      const threadId = activeThreadId;
      const userMsg: Message = { id: `u-${Date.now()}`, role: "user", content: userText.trim(), timestamp: new Date() };
      const placeholderId = `a-${Date.now() + 1}`;
      const placeholder: Message = { id: placeholderId, role: "assistant", content: "__loading__", timestamp: new Date() };
      setThreads((prev) =>
        prev.map((t) => {
          if (t.id !== threadId) return t;
          const title = t.messages.length === 0 ? userText.slice(0, 36) : t.title;
          return { ...t, title, messages: [...t.messages, userMsg, placeholder] };
        })
      );
      setIsLoading(true);
      let ctx: DashboardContext;
      try { ctx = await fetchDashboardContext(); }
      catch { ctx = { fetched_at: new Date().toISOString(), metrics: {}, health: null, recent_decisions: [], recent_audit: [], block_reasons: [], policy_packs: [] }; }
      const systemPrompt = buildSystemPrompt(ctx);
      const historyForLLM = (activeThread?.messages ?? []).filter((m) => m.content !== "__loading__").concat(userMsg);
      const config = getLLMConfig();
      try {
        let reply = "";
        if (config.provider === "anthropic" && config.apiKey) {
          reply = await callAnthropic(historyForLLM, systemPrompt, config.apiKey, config.model);
          updateLastAssistant(threadId, reply || "No response.");
        } else if (config.provider === "openai" && config.apiKey) {
          reply = await callOpenAI(historyForLLM, systemPrompt, config.apiKey, config.model);
          updateLastAssistant(threadId, reply || "No response.");
        } else if (config.provider === "gateway") {
          try {
            const credentialId = (localStorage.getItem("edon_chat_credential_id") || "").trim();
            const response = await edonApi.invokeClawdbot({
              tool: localStorage.getItem("edon_chat_tool") || "chat",
              action: localStorage.getItem("edon_chat_action") || "json",
              args: { prompt: userText, system_prompt: systemPrompt, history: historyForLLM },
              credential_id: credentialId || undefined,
            });
            if (response?.ok) {
              const r = response.result as Record<string, unknown> | string | undefined;
              reply = typeof r === "string" ? r : ((r as Record<string, unknown>)?.text as string) ?? ((r as Record<string, unknown>)?.content as string) ?? JSON.stringify(r);
            }
          } catch { /* fall through */ }
          updateLastAssistant(threadId, reply || getDashboardAwareReply(userText, ctx));
        } else {
          try {
            reply = await callOpenRouterStream(historyForLLM, systemPrompt, (partial) => updateLastAssistant(threadId, partial));
            updateLastAssistant(threadId, reply);
          } catch {
            updateLastAssistant(threadId, getDashboardAwareReply(userText, ctx));
          }
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Request failed.";
        updateLastAssistant(threadId, `⚠ ${msg}\n\n${getDashboardAwareReply(userText, ctx)}`);
      } finally {
        setIsLoading(false);
      }
    },
    [activeThreadId, activeThread, isLoading, updateLastAssistant]
  );

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    sendMessage(text);
  };

  const handleNewChat = () => {
    const id = `chat-${Date.now()}`;
    setThreads((prev) => [{ id, title: "New chat", messages: [] }, ...prev]);
    setActiveThreadId(id);
  };

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ message?: string }>).detail;
      if (detail?.message?.trim()) sendMessage(detail.message.trim());
    };
    window.addEventListener("edon-chat-command", handler as EventListener);
    return () => window.removeEventListener("edon-chat-command", handler as EventListener);
  }, [sendMessage]);

  const isOpenRouter = llmConfig.provider === "openrouter" || (!llmConfig.apiKey && llmConfig.provider !== "gateway");
  const providerLabel =
    llmConfig.provider === "anthropic" && llmConfig.apiKey ? `Claude ${llmConfig.model || "Sonnet"}` :
    llmConfig.provider === "openai" && llmConfig.apiKey ? `GPT ${llmConfig.model || "4o"}` :
    llmConfig.provider === "gateway" ? "Gateway" : "Auto (free)";
  const providerColor =
    llmConfig.provider === "anthropic" && llmConfig.apiKey ? "border-orange-500/30 text-orange-500 bg-orange-500/10" :
    llmConfig.provider === "openai" && llmConfig.apiKey ? "border-sky-500/30 text-sky-500 bg-sky-500/10" :
    isOpenRouter ? "border-violet-500/30 text-violet-500 bg-violet-500/10" :
    "border-border text-muted-foreground";

  return (
    <aside
      className={`fixed right-0 top-0 z-50 h-screen transition-transform duration-200 ${
        open ? "translate-x-0" : "translate-x-full pointer-events-none"
      }`}
      style={{ width }}
    >
      <div className="h-full border-l border-border bg-background flex flex-col relative shadow-2xl">
        {/* Resize handle */}
        <div
          className="absolute left-0 top-0 h-full w-3 cursor-col-resize z-10 group"
          onMouseDown={handleResizeStart}
          role="presentation"
        >
          <div className="absolute left-0 top-1/2 -translate-y-1/2 flex h-12 w-3 items-center justify-center text-muted-foreground/40 group-hover:text-muted-foreground/70 transition-colors">
            <GripVertical className="h-4 w-4" />
          </div>
        </div>

        {/* Header */}
        <div className="border-b border-border px-4 pt-4 pb-3 flex-shrink-0">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-primary/15 border border-primary/30 flex items-center justify-center">
                <Sparkles className="w-3.5 h-3.5 text-primary" />
              </div>
              <div>
                <p className="text-xs font-semibold text-foreground leading-none">EDON Assistant</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">Dashboard-aware AI</p>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <Badge variant="outline" className={`text-[10px] px-1.5 py-0.5 ${providerColor}`}>
                {providerLabel}
              </Badge>
              <button
                onClick={handleNewChat}
                title="New chat"
                className="flex items-center justify-center w-7 h-7 rounded-lg border border-border bg-secondary text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => onOpenChange(false)}
                className="flex items-center justify-center w-7 h-7 rounded-lg border border-border bg-secondary text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Thread tabs */}
          {threads.length > 1 && (
            <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-none">
              {threads.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setActiveThreadId(t.id)}
                  className={`shrink-0 flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
                    activeThreadId === t.id
                      ? "border-primary/30 bg-primary/10 text-foreground"
                      : "border-border bg-secondary text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <span className="max-w-[110px] truncate">{t.title}</span>
                  <span
                    className="text-[10px] opacity-50 hover:opacity-100 ml-0.5"
                    onClick={(e) => {
                      e.stopPropagation();
                      setThreads((prev) => {
                        const next = prev.filter((x) => x.id !== t.id);
                        if (next.length === 0) {
                          const fallback = { id: `chat-${Date.now()}`, title: "New chat", messages: [] };
                          setActiveThreadId(fallback.id);
                          return [fallback];
                        }
                        if (activeThreadId === t.id) setActiveThreadId(next[0].id);
                        return next;
                      });
                    }}
                  >×</span>
                </button>
              ))}
            </div>
          )}

          {/* Status badges */}
          <div className="flex gap-1.5 mt-2.5">
            <Badge variant="outline" className="text-[10px] border-primary/20 text-primary/70 bg-primary/5 px-1.5 py-0.5">Governed</Badge>
            <Badge variant="outline" className="text-[10px] border-border text-muted-foreground/60 px-1.5 py-0.5">Audit logged</Badge>
            <Badge variant="outline" className="text-[10px] border-border text-muted-foreground/60 px-1.5 py-0.5">Dashboard-aware</Badge>
          </div>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {(activeThread?.messages.length || 0) === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="flex items-center gap-2 text-muted-foreground/40">
                <div className="w-1.5 h-1.5 rounded-full bg-primary/40 animate-pulse" />
                <span className="text-[11px]">Starting session…</span>
              </div>
            </div>
          ) : (
            <>
              {activeThread?.messages.map((msg) => (
                <div key={msg.id} className={`flex gap-2.5 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                  {/* Avatar */}
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
                    msg.role === "user"
                      ? "bg-secondary border border-border"
                      : "bg-primary/15 border border-primary/30"
                  }`}>
                    {msg.role === "user"
                      ? <User className="w-3 h-3 text-muted-foreground" />
                      : <Bot className="w-3 h-3 text-primary" />
                    }
                  </div>

                  {/* Bubble */}
                  <div className={`max-w-[85%] rounded-xl px-3 py-2.5 text-xs ${
                    msg.role === "user"
                      ? "bg-primary/10 border border-primary/15 text-foreground"
                      : "bg-secondary/60 border border-border text-foreground/90"
                  }`}>
                    {msg.content === "__loading__" ? (
                      <TypingDots />
                    ) : (
                      <div className="space-y-0.5">{renderMarkdown(msg.content)}</div>
                    )}
                    <p className="text-[9px] text-muted-foreground/40 mt-1.5">
                      {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </p>
                  </div>
                </div>
              ))}

              {/* Suggested prompts */}
              {!isLoading &&
                activeThread?.messages.length === 1 &&
                activeThread.messages[0].role === "assistant" &&
                activeThread.messages[0].content !== "__loading__" && (
                <div className="mt-2">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50 mb-2 ml-8">Try asking</p>
                  <div className="space-y-1.5 ml-8">
                    {SUGGESTED.map((prompt) => (
                      <button
                        key={prompt}
                        onClick={() => sendMessage(prompt)}
                        className="w-full text-left text-xs text-muted-foreground hover:text-foreground border border-border hover:border-primary/30 bg-secondary/40 hover:bg-secondary/80 rounded-lg px-3 py-2 transition-colors"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {isLoading && (activeThread?.messages[activeThread.messages.length - 1]?.content !== "__loading__") && (
                <div className="flex gap-2.5">
                  <div className="w-6 h-6 rounded-full bg-primary/15 border border-primary/30 flex items-center justify-center shrink-0">
                    <RefreshCw className="w-3 h-3 text-primary animate-spin" />
                  </div>
                  <div className="bg-secondary/60 border border-border rounded-xl px-3 py-2.5">
                    <TypingDots />
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-border px-4 py-3 flex-shrink-0">
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your dashboard..."
              rows={1}
              disabled={isLoading}
              className="flex-1 bg-secondary/50 border border-border rounded-xl px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground/50 resize-none focus:outline-none focus:border-primary/40 focus:bg-secondary/80 transition-colors disabled:opacity-50 max-h-32"
              style={{ minHeight: "38px" }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
              }}
              onInput={(e) => {
                const el = e.currentTarget;
                el.style.height = "auto";
                el.style.height = Math.min(el.scrollHeight, 128) + "px";
              }}
            />
            <Button
              size="icon"
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              className="h-9 w-9 shrink-0 bg-primary/15 border border-primary/30 text-primary hover:bg-primary/25 hover:border-primary/50 disabled:opacity-30"
            >
              <Send className="h-3.5 w-3.5" />
            </Button>
          </div>
          <p className="text-[9px] text-muted-foreground/40 mt-1.5 text-center">
            Shift+Enter for new line · Every message includes live dashboard context
          </p>
        </div>
      </div>
    </aside>
  );
}
