import { useEffect, useRef, useState, ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Clock, AlertTriangle, X } from 'lucide-react';
import { SESSION_TIMEOUT_MS, SESSION_WARN_MS, signOut } from '@/lib/auth';

const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click'] as const;
const TICK_MS = 10_000; // check every 10s

function hasToken() {
  return Boolean(
    localStorage.getItem('edon_token') ||
    localStorage.getItem('edon_api_key') ||
    localStorage.getItem('edon_session_token')
  );
}

export function SessionGuard({ children }: { children: ReactNode }) {
  const lastActivity = useRef(Date.now());
  const [warning, setWarning] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(0);

  // Reset timer on any user activity
  useEffect(() => {
    const reset = () => {
      lastActivity.current = Date.now();
      setWarning(false);
    };
    ACTIVITY_EVENTS.forEach(ev => document.addEventListener(ev, reset, { passive: true }));
    return () => ACTIVITY_EVENTS.forEach(ev => document.removeEventListener(ev, reset));
  }, []);

  // Poll for timeout
  useEffect(() => {
    const iv = setInterval(() => {
      if (!hasToken()) return; // not logged in — nothing to timeout

      const idle = Date.now() - lastActivity.current;

      if (idle >= SESSION_TIMEOUT_MS) {
        clearInterval(iv);
        signOut();
        return;
      }

      if (idle >= SESSION_WARN_MS) {
        const remaining = Math.max(0, Math.ceil((SESSION_TIMEOUT_MS - idle) / 1000));
        setSecondsLeft(remaining);
        setWarning(true);
      } else {
        setWarning(false);
      }
    }, TICK_MS);

    return () => clearInterval(iv);
  }, []);

  const extend = () => {
    lastActivity.current = Date.now();
    setWarning(false);
  };

  const fmtSeconds = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m > 0 ? `${m}m ${String(sec).padStart(2, '0')}s` : `${s}s`;
  };

  return (
    <>
      {children}

      {/* Session expiry warning — fixed bottom-right */}
      <AnimatePresence>
        {warning && (
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.97 }}
            transition={{ duration: 0.2 }}
            className="fixed bottom-6 right-6 z-[200] w-72 rounded-2xl border border-amber-500/30 bg-background/95 backdrop-blur-xl shadow-2xl p-4 space-y-3"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-amber-500/15 border border-amber-500/25 flex items-center justify-center shrink-0">
                  <AlertTriangle size={14} className="text-amber-400" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground">Session expiring</p>
                  <p className="text-xs text-muted-foreground">Inactivity detected</p>
                </div>
              </div>
              <button onClick={extend} className="text-muted-foreground hover:text-foreground transition-colors mt-0.5">
                <X size={14} />
              </button>
            </div>

            <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-500/10 border border-amber-500/20">
              <Clock size={12} className="text-amber-400 shrink-0" />
              <span className="text-xs text-amber-400 font-mono font-semibold">
                {fmtSeconds(secondsLeft)} remaining
              </span>
            </div>

            <div className="flex gap-2">
              <button
                onClick={signOut}
                className="flex-1 py-1.5 rounded-xl border border-white/10 text-xs text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
              >
                Sign out now
              </button>
              <button
                onClick={extend}
                className="flex-1 py-1.5 rounded-xl bg-amber-500/20 border border-amber-500/30 text-amber-400 text-xs font-semibold hover:bg-amber-500/30 transition-colors"
              >
                Stay signed in
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
