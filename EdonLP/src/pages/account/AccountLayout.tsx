import { type ReactNode, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  Shield, LayoutDashboard, Bot, ClipboardList, BookOpen,
  CreditCard, AlertTriangle, LogOut, Menu, X, Settings,
} from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import { cn } from '../../lib/utils'

const NAV = [
  { to: '/account', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/account/agents', label: 'Agents', icon: Bot },
  { to: '/account/audit', label: 'Audit Log', icon: ClipboardList },
  { to: '/account/policies', label: 'Policies', icon: BookOpen },
  { to: '/account/review', label: 'Review Queue', icon: AlertTriangle, badge: true },
  { to: '/account/billing', label: 'Billing', icon: CreditCard },
  { to: '/account/settings', label: 'Settings', icon: Settings },
]

export default function AccountLayout({ children }: { children: ReactNode }) {
  const { logout, token, user } = useAuth()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)

  async function handleLogout() {
    await logout()
    navigate('/')
  }

  const userEmail = user?.email ?? ''
  const tokenPreview = token ? `…${token.slice(-8)}` : ''

  const Sidebar = () => (
    <aside className="flex w-56 flex-col border-r border-border bg-[#0a0a12] h-full">
      {/* Logo */}
      <div className="flex h-14 items-center gap-2.5 border-b border-border px-4">
        <div className="h-7 w-7 rounded-lg bg-primary flex items-center justify-center shrink-0 glow-primary-sm">
          <Shield className="h-4 w-4 text-primary-foreground" />
        </div>
        <span className="font-space font-semibold tracking-tight text-[15px]">EDON</span>
        <span className="ml-auto rounded-md bg-primary/10 border border-primary/20 px-1.5 py-0.5 text-[10px] font-medium text-primary">
          Console
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
        {NAV.map(({ to, label, icon: Icon, end, badge }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-150',
                isActive
                  ? 'bg-primary/10 text-primary font-medium border border-primary/15'
                  : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
            {badge && (
              <span className="ml-auto h-1.5 w-1.5 rounded-full bg-status-warning shadow-[0_0_6px_hsl(38_95%_56%/0.8)]" />
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-border p-2">
        <div className="px-3 py-2 mb-1">
          {userEmail && (
            <p className="text-xs text-muted-foreground/70 truncate mb-0.5">{userEmail}</p>
          )}
          {tokenPreview && (
            <>
              <p className="text-[10px] text-muted-foreground/40 uppercase tracking-wider">API key</p>
              <p className="text-xs font-mono text-muted-foreground/60">{tokenPreview}</p>
            </>
          )}
        </div>
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </aside>
  )

  return (
    <div className="min-h-screen bg-background flex">
      {/* Desktop sidebar */}
      <div className="hidden md:flex shrink-0">
        <div className="fixed inset-y-0 left-0 w-56">
          <Sidebar />
        </div>
      </div>

      {/* Mobile overlay */}
      {mobileOpen && (
        <>
          <div
            className="fixed inset-0 z-20 bg-black/70 backdrop-blur-sm md:hidden"
            onClick={() => setMobileOpen(false)}
          />
          <div className="fixed inset-y-0 left-0 z-30 w-56 md:hidden">
            <Sidebar />
            <button
              onClick={() => setMobileOpen(false)}
              className="absolute top-4 right-4 text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </>
      )}

      {/* Main */}
      <div className="flex flex-1 flex-col min-w-0 md:ml-56">
        {/* Mobile top bar */}
        <header className="flex h-14 items-center gap-3 border-b border-border px-4 md:hidden bg-[#0a0a12]">
          <button onClick={() => setMobileOpen(true)} className="text-muted-foreground hover:text-foreground">
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-lg bg-primary flex items-center justify-center">
              <Shield className="h-3.5 w-3.5 text-primary-foreground" />
            </div>
            <span className="font-space font-semibold text-sm">EDON</span>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  )
}

/* ── Shared components ───────────────────────────────── */

export function PageHeader({
  title, description, action,
}: {
  title: string; description?: string; action?: ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-7">
      <div>
        <h1 className="font-space text-xl font-bold tracking-tight">{title}</h1>
        {description && <p className="text-sm text-muted-foreground mt-0.5">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

export function StatCard({
  label, value, sub, accent,
}: {
  label: string; value: string | number; sub?: string; accent?: 'green' | 'red' | 'yellow' | 'default'
}) {
  const colors = { green: 'text-status-active', red: 'text-destructive', yellow: 'text-status-warning', default: 'text-foreground' }
  return (
    <div className="rounded-2xl border border-border bg-card p-5 hover:border-border/80 transition-colors">
      <p className="text-xs text-muted-foreground mb-1.5 uppercase tracking-wide">{label}</p>
      <p className={cn('font-space text-2xl font-bold', colors[accent ?? 'default'])}>{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
    </div>
  )
}

export function VerdictBadge({ verdict }: { verdict: string }) {
  const styles: Record<string, string> = {
    ALLOW: 'bg-status-active/10 text-status-active border-status-active/20',
    BLOCK: 'bg-destructive/10 text-destructive border-destructive/20',
    ESCALATE: 'bg-status-warning/10 text-status-warning border-status-warning/20',
    DEGRADE: 'bg-muted/50 text-muted-foreground border-border',
    PAUSE: 'bg-muted/50 text-muted-foreground border-border',
    ERROR: 'bg-destructive/10 text-destructive border-destructive/20',
  }
  return (
    <span className={cn('inline-flex items-center rounded-lg border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider', styles[verdict] ?? styles.ERROR)}>
      {verdict}
    </span>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { bg: string; dot: string }> = {
    idle:    { bg: 'bg-secondary text-muted-foreground', dot: 'bg-muted-foreground' },
    working: { bg: 'bg-status-active/10 text-status-active', dot: 'bg-status-active animate-pulse' },
    blocked: { bg: 'bg-destructive/10 text-destructive', dot: 'bg-destructive' },
    error:   { bg: 'bg-destructive/10 text-destructive', dot: 'bg-destructive' },
    offline: { bg: 'bg-muted/30 text-muted-foreground/50', dot: 'bg-muted-foreground/30' },
  }
  const c = cfg[status] ?? cfg.offline
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs capitalize font-medium', c.bg)}>
      <span className={cn('h-1.5 w-1.5 rounded-full', c.dot)} />
      {status}
    </span>
  )
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="h-6 w-6 rounded-full border-2 border-primary border-t-transparent animate-spin" />
    </div>
  )
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="h-12 w-12 rounded-2xl border border-border bg-secondary flex items-center justify-center mb-4">
        <Shield className="h-5 w-5 text-muted-foreground/40" />
      </div>
      <p className="text-sm text-muted-foreground max-w-xs">{message}</p>
    </div>
  )
}
