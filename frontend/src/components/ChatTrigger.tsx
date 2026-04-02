import { motion } from "framer-motion";
import { MessageCircle } from "lucide-react";

interface ChatTriggerProps {
  onOpen: () => void;
  /** When true, hide the trigger (e.g. on settings/quickstart). */
  visible?: boolean;
}

export function ChatTrigger({ onOpen, visible = true }: ChatTriggerProps) {
  if (!visible) return null;

  return (
    <>
      {/* Floating chat button icon — top-right */}
      <motion.button
        type="button"
        onClick={onOpen}
        aria-label="Open help and chat"
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2, duration: 0.25 }}
        className="fixed top-20 right-6 z-40 flex h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-background/90 shadow-lg backdrop-blur-sm transition-colors hover:bg-primary hover:text-primary-foreground hover:border-primary/30 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background"
      >
        <MessageCircle className="h-5 w-5" />
      </motion.button>

      {/* Floating chat bar — bottom center, animated "ask questions..." */}
      <motion.button
        type="button"
        onClick={onOpen}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4, duration: 0.3 }}
        whileHover={{ scale: 1.02 }}
        className="fixed bottom-6 left-1/2 z-40 flex -translate-x-1/2 items-center gap-2 rounded-full border border-white/15 bg-background/90 px-5 py-3 shadow-lg backdrop-blur-sm transition-colors hover:border-primary/30 hover:bg-primary/5 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background"
      >
        <span className="inline-flex text-sm font-medium text-muted-foreground">
          <span
            className="animate-shimmer bg-[length:200%_auto] bg-clip-text text-transparent"
            style={{
              backgroundImage:
                "linear-gradient(90deg, hsl(var(--muted-foreground)) 0%, hsl(var(--foreground)) 50%, hsl(var(--muted-foreground)) 100%)",
            }}
          >
            ask questions…
          </span>
        </span>
      </motion.button>
    </>
  );
}
