import { useEffect, useMemo, useState } from "react";
import SEOHead from "@/components/SEOHead";

const Start = () => {
  const botUrl = (import.meta.env.VITE_TELEGRAM_BOT_URL || "https://t.me/edoncore_bot").replace(/\/+$/, "");
  const startParam = import.meta.env.VITE_TELEGRAM_START_PARAM || "edon";
  const telegramUrl = botUrl.includes("?") ? `${botUrl}&start=${startParam}` : `${botUrl}?start=${startParam}`;
  const whatsappUrl = (import.meta.env.VITE_WHATSAPP_URL || "https://wa.me/").trim();

  const headlines = useMemo(
    () => [
      "Experience the world’s first autonomous guardian",
      "Super powers in your pocket ;)",
    ],
    []
  );
  const [headlineIndex, setHeadlineIndex] = useState(0);
  const [typedCount, setTypedCount] = useState(0);
  const [isFading, setIsFading] = useState(false);
  const activeHeadline = headlines[headlineIndex] ?? "";

  useEffect(() => {
    if (!activeHeadline) return;
    let timeoutId: number | undefined;
    if (typedCount < activeHeadline.length) {
      timeoutId = window.setTimeout(() => {
        setTypedCount((count) => Math.min(activeHeadline.length, count + 1));
      }, 28);
    } else if (!isFading) {
      timeoutId = window.setTimeout(() => setIsFading(true), 1400);
    } else {
      timeoutId = window.setTimeout(() => {
        setIsFading(false);
        setTypedCount(0);
        setHeadlineIndex((index) => (index + 1) % headlines.length);
      }, 420);
    }
    return () => {
      if (timeoutId) window.clearTimeout(timeoutId);
    };
  }, [activeHeadline, typedCount, isFading, headlines.length]);

  return (
    <div className="min-h-screen bg-white font-sans flex items-center justify-center px-6">
      <SEOHead
        title="Start | EDON"
        description="Open EDON on Telegram"
        canonical="https://edoncore.com/start"
      />
      <div className="max-w-2xl text-center space-y-6">
        <div className="text-xs font-semibold uppercase tracking-[0.35em] text-[#6b6b6b]">EDON</div>
        <div className="min-h-[96px] sm:min-h-[116px]">
          <h1
            className={`text-3xl sm:text-4xl font-semibold text-black transition-opacity duration-400 ${isFading ? "opacity-0" : "opacity-100"}`}
          >
            {activeHeadline.slice(0, typedCount)}
            <span className="inline-block w-[2px] h-[1em] align-[-0.15em] bg-black ml-1 animate-pulse" />
          </h1>
        </div>
        <div className="text-sm font-medium uppercase tracking-[0.22em] text-gray-500">
          See live decisions • No account required
        </div>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href={telegramUrl}
            className="inline-flex items-center justify-center rounded-full bg-black px-6 py-2.5 text-sm font-semibold text-white hover:bg-gray-900 transition-colors"
          >
            Telegram
          </a>
          <a
            href={whatsappUrl}
            className="inline-flex items-center justify-center rounded-full border border-black px-6 py-2.5 text-sm font-semibold text-black hover:bg-black hover:text-white transition-colors"
          >
            WhatsApp
          </a>
        </div>
        <p className="text-xs text-gray-500">
          Choose your channel to continue.
        </p>
      </div>
    </div>
  );
};

export default Start;
