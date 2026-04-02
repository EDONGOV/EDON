import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ShieldCheck, Gauge, ListChecks, FileSearch, Settings2,
  LogOut, User, CreditCard, Users, Key, ChevronDown, Bot,
  Bell, ShieldAlert, X, Menu, Crown, Puzzle, Radio, Layers,
  Eye, EyeOff, Lock, Sun, Moon, Power,
  type LucideIcon,
} from 'lucide-react';
import { useTheme } from '@/hooks/useTheme';
import { useEffect, useRef, useState } from 'react';
import { edonApi } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  getNavItems,
  isAdmin,
  isPreviewMode,
  setPreviewMode,
} from '@/lib/workspaceProfile';

// Map icon name strings → Lucide components
const ICON_MAP: Record<string, LucideIcon> = {
  Gauge, ListChecks, FileSearch, Bot, ShieldCheck, ShieldAlert, Settings2,
  Crown, Puzzle, Radio, Layers,
  Circle: Layers, // fallback for dynamic domain extras
};

function buildNavItems(forceCustomer = false) {
  return getNavItems(forceCustomer).map((item) => ({
    to: item.to,
    label: item.label,
    icon: ICON_MAP[item.iconName] ?? Layers,
  }));
}

interface Notif {
  id: string;
  verdict: string;
  tool: string;
  agent_id: string | null;
  reason_code: string | null;
  timestamp: string;
}

const LAST_SEEN_KEY = 'edon_notifs_last_seen';

export function TopNav() {
  const location = useLocation();
  const navigate = useNavigate();
  const [isConnected, setIsConnected] = useState(true);
  const [userEmail, setUserEmail] = useState(() => localStorage.getItem('edon_user_email') || '');
  const [userPlan, setUserPlan] = useState(() => localStorage.getItem('edon_plan') || 'Starter');
  const [adminMode] = useState(() => isAdmin());
  const [previewActive, setPreviewActive] = useState(() => isPreviewMode());
  const [navItems, setNavItems] = useState(() => buildNavItems(isPreviewMode()));
  const [displayName, setDisplayName] = useState(() => localStorage.getItem('edon_display_name') || '');
  const [mobileOpen, setMobileOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const [hgiHalt, setHgiHalt] = useState(() => localStorage.getItem('edon_hgi_halt') === 'true');

  const _hasAnyToken = () =>
    Boolean(
      localStorage.getItem('edon_token') ||
      localStorage.getItem('edon_api_key') ||
      localStorage.getItem('edon_session_token') ||
      (import.meta.env.MODE !== 'production' && import.meta.env.VITE_EDON_API_TOKEN)
    );
  const [hasToken, setHasToken] = useState(() => typeof window !== 'undefined' && _hasAnyToken());

  // ── Notifications ──────────────────────────────────────────────
  const [notifs, setNotifs] = useState<Notif[]>([]);
  const [unread, setUnread] = useState(0);
  const [notifsOpen, setNotifsOpen] = useState(false);
  const notifsRef = useRef<HTMLDivElement>(null);
  const lastSeenRef = useRef<string>(
    typeof window !== 'undefined' ? (localStorage.getItem(LAST_SEEN_KEY) || new Date(0).toISOString()) : new Date(0).toISOString()
  );

  const fetchNotifs = async () => {
    try {
      const result = await edonApi.getDecisions({ verdict: 'blocked', limit: 20 });
      const decisions = result?.decisions ?? [];
      const mapped: Notif[] = decisions.map((d: { id?: string; verdict?: string; tool?: { name?: string; op?: string } | string; agent_id?: string; reason_code?: string; timestamp?: string; created_at?: string }) => ({
        id: d.id ?? Math.random().toString(36).slice(2),
        verdict: d.verdict ?? 'blocked',
        tool: typeof d.tool === 'object' && d.tool
          ? [d.tool.name, d.tool.op].filter(Boolean).join('.')
          : (typeof d.tool === 'string' ? d.tool : '—'),
        agent_id: d.agent_id ?? null,
        reason_code: d.reason_code ?? null,
        timestamp: d.timestamp ?? d.created_at ?? new Date().toISOString(),
      }));

      setNotifs(mapped.slice(0, 10));

      const newCount = mapped.filter(
        (n) => new Date(n.timestamp) > new Date(lastSeenRef.current)
      ).length;
      setUnread(newCount);
    } catch {
      // silently ignore — don't surface notification errors in the nav
    }
  };

  const markAllRead = () => {
    const now = new Date().toISOString();
    lastSeenRef.current = now;
    localStorage.setItem(LAST_SEEN_KEY, now);
    setUnread(0);
  };

  // Close notifs dropdown on outside click
  useEffect(() => {
    if (!notifsOpen) return;
    const handler = (e: MouseEvent) => {
      if (notifsRef.current && !notifsRef.current.contains(e.target as Node)) {
        setNotifsOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [notifsOpen]);

  function relTime(iso: string) {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  // ── Connection + auth + preview polling ───────────────────────
  useEffect(() => {
    const checkConnection = async () => {
      try {
        await edonApi.getHealth();
        setIsConnected(true);
      } catch {
        setIsConnected(false);
      }
    };

    checkConnection();
    if (_hasAnyToken()) fetchNotifs();

    const handleStorageChange = () => {
      setHasToken(typeof window !== 'undefined' && _hasAnyToken());
      setUserEmail(localStorage.getItem('edon_user_email') || '');
      setUserPlan(localStorage.getItem('edon_plan') || 'Starter');
      setDisplayName(localStorage.getItem('edon_display_name') || '');
      const preview = isPreviewMode();
      setPreviewActive(preview);
      setNavItems(buildNavItems(preview));
    };

    const handlePreviewChange = () => {
      const preview = isPreviewMode();
      setPreviewActive(preview);
      setNavItems(buildNavItems(preview));
    };

    const handleHgiHalt = () => setHgiHalt(localStorage.getItem('edon_hgi_halt') === 'true');
    window.addEventListener('edon-profile-updated', handleStorageChange as EventListener);
    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('edon-auth-updated', handleStorageChange as EventListener);
    window.addEventListener('edon-preview-updated', handlePreviewChange as EventListener);
    window.addEventListener('edon-hgi-halt', handleHgiHalt);

    const interval = setInterval(() => {
      checkConnection();
      setHasToken(typeof window !== 'undefined' && _hasAnyToken());
      if (_hasAnyToken()) fetchNotifs();
    }, 30000);

    return () => {
      clearInterval(interval);
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('edon-auth-updated', handleStorageChange as EventListener);
      window.removeEventListener('edon-profile-updated', handleStorageChange as EventListener);
      window.removeEventListener('edon-preview-updated', handlePreviewChange as EventListener);
      window.removeEventListener('edon-hgi-halt', handleHgiHalt);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <motion.header
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        className="sticky top-0 z-50 border-b border-border backdrop-blur-xl bg-background/80"
      >
        {/* ── Customer preview banner ─────────────────────────── */}
        <AnimatePresence>
          {previewActive && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.18 }}
              className="flex items-center justify-between px-6 py-1.5 bg-amber-500/10 border-b border-amber-500/20 overflow-hidden"
            >
              <div className="flex items-center gap-2 text-amber-400 text-xs">
                <Eye className="w-3.5 h-3.5 shrink-0" />
                <span className="font-semibold">Customer Preview</span>
                <span className="text-amber-400/60 hidden sm:inline">— admin items hidden · viewing as Standard user</span>
              </div>
              <button
                onClick={() => setPreviewMode(false)}
                className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium text-amber-400 bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/25 transition-colors"
              >
                <EyeOff className="w-3 h-3" />
                Exit Preview
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex items-center gap-4 h-14">

            {/* EDON wordmark */}
            <NavLink to="/" className="flex items-center gap-2 shrink-0">
              <div className="w-7 h-7 rounded-lg bg-primary/20 border border-primary/30 flex items-center justify-center">
                <Lock className="w-3.5 h-3.5 text-primary" />
              </div>
              <span className="edon-brand font-bold text-foreground text-sm tracking-widest">EDON</span>
              <span className="text-muted-foreground text-xs hidden sm:block">· Governance Platform</span>
            </NavLink>

            {/* Desktop navigation */}
            <nav className="hidden md:flex items-center gap-1 bg-secondary/60 rounded-xl p-1">
              {navItems.map((item) => {
                const isActive = location.pathname === item.to;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={`relative flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                      isActive ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {isActive && (
                      <motion.div
                        layoutId="nav-indicator"
                        className="absolute inset-0 rounded-lg"
                        style={{ background: 'var(--nav-indicator-bg)' }}
                        transition={{ type: 'spring', bounce: 0.2, duration: 0.35 }}
                      />
                    )}
                    <span className="relative flex items-center gap-1.5">
                      <item.icon className="w-3.5 h-3.5" />
                      <span className="hidden lg:inline">{item.label}</span>
                    </span>
                  </NavLink>
                );
              })}
            </nav>

            {/* Right side */}
            <div className="ml-auto flex items-center gap-2 shrink-0">

              {/* Live / Offline badge */}
              <Badge
                variant="outline"
                className={`flex items-center gap-1.5 text-xs ${
                  isConnected
                    ? 'border-emerald-500/40 text-emerald-400 bg-emerald-500/10'
                    : 'border-red-500/40 text-red-400 bg-red-500/10'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'}`} />
                <span className="hidden sm:inline">{isConnected ? 'Live' : 'Offline'}</span>
              </Badge>

              {/* Theme toggle */}
              <button
                onClick={toggleTheme}
                className="flex items-center justify-center w-8 h-8 rounded-xl border border-border bg-secondary hover:bg-muted transition-colors"
                aria-label="Toggle theme"
              >
                {theme === 'dark'
                  ? <Sun className="w-3.5 h-3.5 text-muted-foreground" />
                  : <Moon className="w-3.5 h-3.5 text-muted-foreground" />}
              </button>

              {/* HGI halt indicator */}
              {hasToken && (
                <NavLink
                  to="/hgi"
                  title={hgiHalt ? 'Emergency halt active — click to manage' : 'HGI · Governance Intelligence'}
                  className={`flex items-center justify-center w-8 h-8 rounded-xl border transition-colors ${
                    hgiHalt
                      ? 'border-red-500/50 bg-red-500/15 text-red-400 animate-pulse'
                      : 'border-border bg-secondary hover:bg-muted text-muted-foreground'
                  }`}
                  aria-label="HGI panel"
                >
                  <Power className="w-3.5 h-3.5" />
                </NavLink>
              )}

              {/* Notifications bell */}
              {hasToken && (
                <div className="relative" ref={notifsRef}>
                  <button
                    onClick={() => { setNotifsOpen((v) => !v); }}
                    className="relative flex items-center justify-center w-8 h-8 rounded-xl border border-border bg-secondary hover:bg-muted transition-colors"
                    aria-label="Governance alerts"
                  >
                    <Bell className="w-4 h-4 text-muted-foreground" />
                    {unread > 0 && (
                      <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">
                        {unread > 9 ? '9+' : unread}
                      </span>
                    )}
                  </button>

                  <AnimatePresence>
                    {notifsOpen && (
                      <motion.div
                        initial={{ opacity: 0, y: 6, scale: 0.97 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 4, scale: 0.97 }}
                        transition={{ duration: 0.15 }}
                        className="absolute right-0 top-10 w-80 rounded-xl border border-border bg-popover shadow-2xl z-50 overflow-hidden"
                      >
                        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                          <div className="flex items-center gap-2">
                            <ShieldAlert className="w-4 h-4 text-red-400" />
                            <span className="text-sm font-semibold">Governance Alerts</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={markAllRead}
                              className="text-[10px] text-muted-foreground hover:text-foreground"
                            >
                              Mark all read
                            </button>
                            <button onClick={() => setNotifsOpen(false)}>
                              <X className="w-3.5 h-3.5 text-muted-foreground hover:text-foreground" />
                            </button>
                          </div>
                        </div>

                        <div className="max-h-72 overflow-y-auto">
                          {notifs.length === 0 ? (
                            <div className="py-8 text-center">
                              <ShieldCheck className="w-6 h-6 text-emerald-400/50 mx-auto mb-2" />
                              <p className="text-xs text-muted-foreground">No blocked actions recently</p>
                            </div>
                          ) : (
                            notifs.map((n) => (
                              <div
                                key={n.id}
                                className="px-4 py-3 border-b border-white/5 hover:bg-white/5 cursor-pointer transition-colors"
                                onClick={() => { navigate('/audit'); setNotifsOpen(false); }}
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <div className="flex items-center gap-2 min-w-0">
                                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0 mt-1.5" />
                                    <div className="min-w-0">
                                      <p className="text-xs font-mono font-medium truncate">{n.tool}</p>
                                      <p className="text-[10px] text-muted-foreground mt-0.5">
                                        {n.reason_code ?? 'blocked'}{n.agent_id ? ` · ${n.agent_id}` : ''}
                                      </p>
                                    </div>
                                  </div>
                                  <span className="text-[10px] text-muted-foreground/60 shrink-0">{relTime(n.timestamp)}</span>
                                </div>
                              </div>
                            ))
                          )}
                        </div>

                        <div className="px-4 py-2.5 border-t border-border">
                          <button
                            onClick={() => { navigate('/audit'); setNotifsOpen(false); }}
                            className="text-xs text-primary hover:underline"
                          >
                            View all in Audit →
                          </button>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              {/* User menu */}
              {hasToken && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button className={`flex items-center gap-2 rounded-xl border px-2.5 py-1.5 hover:bg-white/10 transition-colors ${
                      previewActive
                        ? 'border-amber-500/30 bg-amber-500/10'
                        : 'border-border bg-secondary hover:bg-muted'
                    }`}>
                      <div className={`w-6 h-6 rounded-full border flex items-center justify-center text-[10px] font-bold ${
                        previewActive
                          ? 'bg-amber-500/20 border-amber-500/40 text-amber-400'
                          : 'bg-[#64dc78]/20 border-[#64dc78]/40 text-[#64dc78]'
                      }`}>
                        {previewActive ? <Eye className="w-3 h-3" /> : (displayName || userEmail || 'U').charAt(0).toUpperCase()}
                      </div>
                      <span className="hidden sm:inline text-xs text-foreground/80 max-w-[120px] truncate">
                        {previewActive ? 'Preview' : (displayName || userEmail || 'Account')}
                      </span>
                      <ChevronDown className="w-3 h-3 text-muted-foreground hidden sm:block" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56 bg-popover border border-border">
                    <DropdownMenuLabel className="pb-1">
                      <p className="text-sm font-medium text-foreground truncate">{displayName || userEmail || 'My Account'}</p>
                      {userEmail && displayName && (
                        <p className="text-xs text-muted-foreground truncate">{userEmail}</p>
                      )}
                      <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                        <Badge variant="outline" className="text-[10px] border-[#64dc78]/30 text-[#64dc78] bg-[#64dc78]/10">
                          {userPlan}
                        </Badge>
                        {adminMode && !previewActive && (
                          <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-400 bg-amber-500/10 gap-1">
                            <Crown className="w-2.5 h-2.5" /> EDON Team
                          </Badge>
                        )}
                        {previewActive && (
                          <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-400 bg-amber-500/10 gap-1">
                            <Eye className="w-2.5 h-2.5" /> Previewing
                          </Badge>
                        )}
                      </div>
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator className="bg-white/10" />
                    <DropdownMenuItem onClick={() => navigate('/profile')} className="gap-2 cursor-pointer hover:bg-white/5">
                      <User className="w-4 h-4 text-muted-foreground" /><span>Profile</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/team')} className="gap-2 cursor-pointer hover:bg-white/5">
                      <Users className="w-4 h-4 text-muted-foreground" /><span>Team</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/api-keys')} className="gap-2 cursor-pointer hover:bg-white/5">
                      <Key className="w-4 h-4 text-muted-foreground" /><span>API Keys</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/billing')} className="gap-2 cursor-pointer hover:bg-white/5">
                      <CreditCard className="w-4 h-4 text-muted-foreground" /><span>Billing</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/capabilities')} className="gap-2 cursor-pointer hover:bg-white/5">
                      <Puzzle className="w-4 h-4 text-muted-foreground" /><span>Capabilities</span>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator className="bg-white/10" />
                    <DropdownMenuItem onClick={() => navigate('/settings')} className="gap-2 cursor-pointer hover:bg-white/5">
                      <Settings2 className="w-4 h-4 text-muted-foreground" /><span>Settings</span>
                    </DropdownMenuItem>
                    {adminMode && (
                      <>
                        <DropdownMenuSeparator className="bg-white/10" />
                        {!previewActive ? (
                          <>
                            <DropdownMenuItem onClick={() => navigate('/admin')} className="gap-2 cursor-pointer hover:bg-amber-500/10 text-amber-400">
                              <Crown className="w-4 h-4" /><span>Admin Panel</span>
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => setPreviewMode(true)}
                              className="gap-2 cursor-pointer hover:bg-amber-500/10 text-amber-400/80"
                            >
                              <Eye className="w-4 h-4" /><span>Preview as Customer</span>
                            </DropdownMenuItem>
                          </>
                        ) : (
                          <DropdownMenuItem
                            onClick={() => setPreviewMode(false)}
                            className="gap-2 cursor-pointer hover:bg-amber-500/10 text-amber-400 font-medium"
                          >
                            <EyeOff className="w-4 h-4" /><span>Exit Customer Preview</span>
                          </DropdownMenuItem>
                        )}
                      </>
                    )}
                    <DropdownMenuSeparator className="bg-white/10" />
                    <DropdownMenuItem
                      className="gap-2 cursor-pointer text-red-400 hover:bg-red-500/10 hover:text-red-400 focus:text-red-400"
                      onClick={() => {
                        ['edon_token','edon_api_key','edon_session_token','edon_user_email','edon_plan'].forEach(k => localStorage.removeItem(k));
                        window.dispatchEvent(new Event('edon-auth-updated'));
                        window.location.replace('/');
                      }}
                    >
                      <LogOut className="w-4 h-4" /><span>Sign out</span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}

              {/* Mobile hamburger */}
              <button
                className="flex md:hidden items-center justify-center w-8 h-8 rounded-lg border border-border bg-secondary hover:bg-muted transition-colors"
                onClick={() => setMobileOpen((v) => !v)}
                aria-label="Open navigation"
              >
                {mobileOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile nav drawer */}
        <AnimatePresence>
          {mobileOpen && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="md:hidden border-t border-border bg-background/95 overflow-hidden"
            >
              <nav className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex flex-col gap-1">
                {navItems.map((item) => {
                  const isActive = location.pathname === item.to;
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      onClick={() => setMobileOpen(false)}
                      className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                        isActive
                          ? 'bg-primary/15 text-primary'
                          : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
                      }`}
                    >
                      <item.icon className="w-4 h-4" />
                      {item.label}
                    </NavLink>
                  );
                })}
              </nav>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.header>
    </>
  );
}
