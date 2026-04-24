import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ShieldCheck, Gauge, ListChecks, FileSearch, Settings2,
  LogOut, User, CreditCard, Users, Key, ChevronDown, Bot,
  Bell, ShieldAlert, X, Menu, Crown, Puzzle, Radio, Layers,
  Eye, EyeOff, Lock, Sun, Moon, Power, ClipboardList,
  AlertTriangle, Radar, GitBranch, type LucideIcon,
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

const ICON_MAP: Record<string, LucideIcon> = {
  Gauge, ListChecks, FileSearch, Bot, ShieldCheck, ShieldAlert, Settings2,
  Crown, Puzzle, Radio, Layers, ClipboardList, Radar, GitBranch,
  Circle: Layers,
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
  const [lockdownConfirm, setLockdownConfirm] = useState(false);
  const [pendingReviews, setPendingReviews] = useState(0);

  useEffect(() => {
    if (!_hasAnyToken()) return;
    const fetchCount = async () => {
      try {
        const res = await edonApi.getReviewQueue('pending');
        setPendingReviews(res?.count ?? 0);
      } catch { /* silent */ }
    };
    fetchCount();
    const iv = setInterval(fetchCount, 30000);
    return () => clearInterval(iv);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    } catch { /* silent */ }
  };

  const markAllRead = () => {
    const now = new Date().toISOString();
    lastSeenRef.current = now;
    localStorage.setItem(LAST_SEEN_KEY, now);
    setUnread(0);
  };

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

  useEffect(() => {
    const checkConnection = async () => {
      try { await edonApi.getHealth(); setIsConnected(true); }
      catch { setIsConnected(false); }
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

  const initials = (displayName || userEmail || 'U').charAt(0).toUpperCase();

  return (
    <>
      <motion.header
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="sticky top-0 z-50 border-b border-border/60 bg-background/90 backdrop-blur-xl"
      >
        {/* Emergency lockdown banner */}
        <AnimatePresence>
          {hgiHalt && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.15 }}
              className="flex items-center justify-between px-6 py-1.5 bg-red-500/12 border-b border-red-500/25 overflow-hidden"
            >
              <div className="flex items-center gap-2 text-red-400 text-xs">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 animate-pulse" />
                <span className="font-semibold tracking-wide">EMERGENCY LOCKDOWN ACTIVE</span>
                <span className="text-red-400/50 hidden sm:inline">— all agent actions suspended</span>
              </div>
              <button
                onClick={() => { localStorage.removeItem('edon_hgi_halt'); window.dispatchEvent(new Event('edon-hgi-halt')); }}
                className="px-2.5 py-0.5 rounded-full text-xs font-medium text-red-400 bg-red-500/12 hover:bg-red-500/20 border border-red-500/25 transition-colors"
              >
                Lift Lockdown
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Preview banner */}
        <AnimatePresence>
          {previewActive && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.15 }}
              className="flex items-center justify-between px-6 py-1.5 bg-amber-500/8 border-b border-amber-500/15 overflow-hidden"
            >
              <div className="flex items-center gap-2 text-amber-400 text-xs">
                <Eye className="w-3.5 h-3.5 shrink-0" />
                <span className="font-semibold">Customer Preview</span>
                <span className="text-amber-400/50 hidden sm:inline">— viewing as Standard user</span>
              </div>
              <button
                onClick={() => setPreviewMode(false)}
                className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium text-amber-400 bg-amber-500/12 hover:bg-amber-500/20 border border-amber-500/20 transition-colors"
              >
                <EyeOff className="w-3 h-3" /> Exit Preview
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Main bar */}
        <div className="px-4 sm:px-6">
          <div className="flex items-center gap-3 h-13" style={{ height: 52 }}>

            {/* Logo */}
            <NavLink to="/" className="flex items-center gap-2 shrink-0 group">
              <div className="w-7 h-7 rounded-lg bg-primary/15 border border-primary/25 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                <Lock className="w-3.5 h-3.5 text-primary" />
              </div>
              <div className="flex items-center gap-1.5">
                <span className="edon-brand font-bold text-foreground text-sm tracking-widest">EDON</span>
                {/* Connection dot */}
                <span
                  title={isConnected ? 'Connected' : 'Offline'}
                  className={`w-1.5 h-1.5 rounded-full transition-colors ${isConnected ? 'bg-emerald-400' : 'bg-red-400'}`}
                />
              </div>
            </NavLink>

            {/* Divider */}
            <div className="hidden md:block w-px h-5 bg-border/60 mx-1" />

            {/* Desktop nav */}
            <nav className="hidden md:flex items-center gap-0.5">
              {navItems.map((item) => {
                const isActive = location.pathname === item.to;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={`relative flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all duration-150 ${
                      isActive
                        ? 'text-foreground'
                        : 'text-muted-foreground hover:text-foreground hover:bg-white/5'
                    }`}
                  >
                    {isActive && (
                      <motion.div
                        layoutId="nav-pill"
                        className="absolute inset-0 rounded-lg bg-white/8 border border-white/8"
                        transition={{ type: 'spring', bounce: 0.15, duration: 0.3 }}
                      />
                    )}
                    <span className="relative flex items-center gap-1.5">
                      <item.icon className="w-3.5 h-3.5 shrink-0" />
                      <span className="hidden lg:inline">{item.label}</span>
                      {item.to === '/review' && pendingReviews > 0 && (
                        <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white px-1">
                          {pendingReviews > 9 ? '9+' : pendingReviews}
                        </span>
                      )}
                    </span>
                  </NavLink>
                );
              })}
            </nav>

            {/* Spacer */}
            <div className="flex-1" />

            {/* Right actions */}
            <div className="flex items-center gap-1 shrink-0">

              {/* Lockdown pill — only when active or as subtle button */}
              {hasToken && hgiHalt && (
                <button
                  onClick={() => { localStorage.removeItem('edon_hgi_halt'); window.dispatchEvent(new Event('edon-hgi-halt')); }}
                  className="hidden sm:flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-semibold text-red-400 bg-red-500/15 border border-red-500/30 animate-pulse"
                >
                  <Power className="w-3 h-3" /> LOCKDOWN
                </button>
              )}
              {hasToken && !hgiHalt && (
                <button
                  onClick={() => setLockdownConfirm(true)}
                  title="Emergency lockdown — halts all agents"
                  className="hidden sm:flex items-center justify-center w-8 h-8 rounded-lg text-muted-foreground/50 hover:text-red-400/80 hover:bg-red-500/8 border border-transparent hover:border-red-500/20 transition-all"
                >
                  <Power className="w-3.5 h-3.5" />
                </button>
              )}

              {/* AI assistant */}
              {hasToken && (
                <button
                  onClick={() => window.dispatchEvent(new Event('edon-chat-open'))}
                  title="Governance AI Assistant"
                  className="flex items-center justify-center w-8 h-8 rounded-lg border border-primary/20 bg-primary/8 hover:bg-primary/15 text-primary transition-colors"
                >
                  <Bot className="w-3.5 h-3.5" />
                </button>
              )}

              {/* Notifications */}
              {hasToken && (
                <div className="relative" ref={notifsRef}>
                  <button
                    onClick={() => setNotifsOpen((v) => !v)}
                    className="relative flex items-center justify-center w-8 h-8 rounded-lg border border-border/60 bg-secondary/60 hover:bg-secondary transition-colors"
                    aria-label="Alerts"
                  >
                    <Bell className="w-3.5 h-3.5 text-muted-foreground" />
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
                        transition={{ duration: 0.13 }}
                        className="absolute right-0 top-10 w-80 rounded-xl border border-border bg-popover shadow-2xl z-50 overflow-hidden"
                      >
                        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                          <div className="flex items-center gap-2">
                            <ShieldAlert className="w-4 h-4 text-red-400" />
                            <span className="text-sm font-semibold">Governance Alerts</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <button onClick={markAllRead} className="text-[10px] text-muted-foreground hover:text-foreground">
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
                              <ShieldCheck className="w-6 h-6 text-emerald-400/40 mx-auto mb-2" />
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
                                  <span className="text-[10px] text-muted-foreground/50 shrink-0">{relTime(n.timestamp)}</span>
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
                    <button className={`flex items-center gap-2 rounded-lg border px-2 py-1.5 hover:bg-white/8 transition-colors ${
                      previewActive
                        ? 'border-amber-500/25 bg-amber-500/8'
                        : 'border-border/60 bg-secondary/60'
                    }`}>
                      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${
                        previewActive
                          ? 'bg-amber-500/20 text-amber-400'
                          : 'bg-primary/20 text-primary'
                      }`}>
                        {previewActive ? <Eye className="w-3 h-3" /> : initials}
                      </div>
                      <ChevronDown className="w-3 h-3 text-muted-foreground hidden sm:block" />
                    </button>
                  </DropdownMenuTrigger>

                  <DropdownMenuContent align="end" className="w-52 bg-popover border border-border">
                    <DropdownMenuLabel className="pb-1.5">
                      <p className="text-sm font-medium text-foreground truncate">{displayName || userEmail || 'My Account'}</p>
                      {userEmail && displayName && (
                        <p className="text-xs text-muted-foreground truncate">{userEmail}</p>
                      )}
                      <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                        <Badge variant="outline" className="text-[10px] border-primary/25 text-primary bg-primary/8 h-5">
                          {userPlan}
                        </Badge>
                        {adminMode && !previewActive && (
                          <Badge variant="outline" className="text-[10px] border-amber-500/30 text-amber-400 bg-amber-500/8 h-5 gap-1">
                            <Crown className="w-2.5 h-2.5" /> Team
                          </Badge>
                        )}
                      </div>
                    </DropdownMenuLabel>

                    <DropdownMenuSeparator className="bg-border/60" />

                    <DropdownMenuItem onClick={() => navigate('/profile')} className="gap-2 cursor-pointer hover:bg-white/5 text-sm">
                      <User className="w-3.5 h-3.5 text-muted-foreground" /> Profile
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/team')} className="gap-2 cursor-pointer hover:bg-white/5 text-sm">
                      <Users className="w-3.5 h-3.5 text-muted-foreground" /> Team
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/api-keys')} className="gap-2 cursor-pointer hover:bg-white/5 text-sm">
                      <Key className="w-3.5 h-3.5 text-muted-foreground" /> API Keys
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/billing')} className="gap-2 cursor-pointer hover:bg-white/5 text-sm">
                      <CreditCard className="w-3.5 h-3.5 text-muted-foreground" /> Billing
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/capabilities')} className="gap-2 cursor-pointer hover:bg-white/5 text-sm">
                      <Puzzle className="w-3.5 h-3.5 text-muted-foreground" /> Capabilities
                    </DropdownMenuItem>

                    <DropdownMenuSeparator className="bg-border/60" />

                    {/* Theme toggle */}
                    <DropdownMenuItem onClick={toggleTheme} className="gap-2 cursor-pointer hover:bg-white/5 text-sm">
                      {theme === 'dark'
                        ? <><Sun className="w-3.5 h-3.5 text-muted-foreground" /> Light mode</>
                        : <><Moon className="w-3.5 h-3.5 text-muted-foreground" /> Dark mode</>}
                    </DropdownMenuItem>

                    <DropdownMenuItem onClick={() => navigate('/settings')} className="gap-2 cursor-pointer hover:bg-white/5 text-sm">
                      <Settings2 className="w-3.5 h-3.5 text-muted-foreground" /> Settings
                    </DropdownMenuItem>

                    {adminMode && (
                      <>
                        <DropdownMenuSeparator className="bg-border/60" />
                        {!previewActive ? (
                          <>
                            <DropdownMenuItem onClick={() => navigate('/admin')} className="gap-2 cursor-pointer hover:bg-amber-500/8 text-amber-400 text-sm">
                              <Crown className="w-3.5 h-3.5" /> Admin Panel
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => setPreviewMode(true)} className="gap-2 cursor-pointer hover:bg-amber-500/8 text-amber-400/80 text-sm">
                              <Eye className="w-3.5 h-3.5" /> Preview as Customer
                            </DropdownMenuItem>
                          </>
                        ) : (
                          <DropdownMenuItem onClick={() => setPreviewMode(false)} className="gap-2 cursor-pointer hover:bg-amber-500/8 text-amber-400 font-medium text-sm">
                            <EyeOff className="w-3.5 h-3.5" /> Exit Customer Preview
                          </DropdownMenuItem>
                        )}
                      </>
                    )}

                    <DropdownMenuSeparator className="bg-border/60" />
                    <DropdownMenuItem
                      className="gap-2 cursor-pointer text-red-400 hover:bg-red-500/8 hover:text-red-400 focus:text-red-400 text-sm"
                      onClick={() => {
                        ['edon_token','edon_api_key','edon_session_token','edon_user_email','edon_plan'].forEach(k => localStorage.removeItem(k));
                        window.dispatchEvent(new Event('edon-auth-updated'));
                        window.location.replace('/');
                      }}
                    >
                      <LogOut className="w-3.5 h-3.5" /> Sign out
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}

              {/* Mobile hamburger */}
              <button
                className="flex md:hidden items-center justify-center w-8 h-8 rounded-lg border border-border/60 bg-secondary/60 hover:bg-secondary transition-colors"
                onClick={() => setMobileOpen((v) => !v)}
                aria-label="Open navigation"
              >
                {mobileOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile nav */}
        <AnimatePresence>
          {mobileOpen && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="md:hidden border-t border-border/60 bg-background/95 overflow-hidden"
            >
              <nav className="px-4 py-3 flex flex-col gap-0.5">
                {navItems.map((item) => {
                  const isActive = location.pathname === item.to;
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      onClick={() => setMobileOpen(false)}
                      className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                        isActive
                          ? 'bg-white/8 text-foreground'
                          : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
                      }`}
                    >
                      <item.icon className="w-4 h-4" />
                      {item.label}
                      {item.to === '/review' && pendingReviews > 0 && (
                        <span className="ml-auto flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">
                          {pendingReviews > 9 ? '9+' : pendingReviews}
                        </span>
                      )}
                    </NavLink>
                  );
                })}
              </nav>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.header>

      {/* Lockdown confirmation */}
      <AnimatePresence>
        {lockdownConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          >
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setLockdownConfirm(false)} />
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ type: 'spring', bounce: 0.2, duration: 0.25 }}
              className="relative z-10 glass-card max-w-sm w-full p-6 space-y-4"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-red-500/12 border border-red-500/25 flex items-center justify-center shrink-0">
                  <AlertTriangle className="w-5 h-5 text-red-400" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-foreground">Activate Emergency Lockdown?</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">All agent actions will be suspended immediately.</p>
                </div>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Every AI agent action will be blocked system-wide until you lift the lockdown. This is recorded in your audit trail.
              </p>
              <div className="flex gap-2.5">
                <button
                  onClick={() => setLockdownConfirm(false)}
                  className="flex-1 py-2.5 rounded-xl border border-white/12 text-sm text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    localStorage.setItem('edon_hgi_halt', 'true');
                    window.dispatchEvent(new Event('edon-hgi-halt'));
                    setLockdownConfirm(false);
                  }}
                  className="flex-1 py-2.5 rounded-xl bg-red-500/15 border border-red-500/35 text-red-400 text-sm font-bold hover:bg-red-500/25 transition-colors"
                >
                  Activate Lockdown
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
