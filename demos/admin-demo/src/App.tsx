import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Shield, LogOut, KeyRound, Activity, ScrollText,
  Building2, ChevronDown, ChevronUp, Plus, Eye,
  CheckCircle2, AlertCircle, Search,
  TrendingUp, TrendingDown, Minus, X, Copy,
  Clock, Key, Power, DollarSign, BarChart2, Globe,
  ToggleLeft, ToggleRight, FlaskConical, Lock,
  Server, UserCheck, FileText, CalendarClock, Zap, Trophy,
} from 'lucide-react'

// ── Mock Data ─────────────────────────────────────────────────────────────────

const MOCK_TENANTS = [
  {
    tenant_id: 'mercy-general-hospital',
    name: 'Mercy General Hospital',
    status: 'active',
    created_at: '2025-11-03T09:14:22Z',
    active_key_count: 4, total_key_count: 6,
    decisions_today: 1847, block_rate: 2.3, trend: 'up',
    city: 'Chicago, IL', agents: 12,
    pilot_expires: null,
    acv: 60000, term: 2, renewal: '2027-11-03',
    agents_licensed: 15, decisions_included: '2M/mo',
  },
  {
    tenant_id: 'northside-medical-center',
    name: 'Northside Medical Center',
    status: 'active',
    created_at: '2025-12-18T14:30:00Z',
    active_key_count: 3, total_key_count: 3,
    decisions_today: 934, block_rate: 5.1, trend: 'up',
    city: 'Atlanta, GA', agents: 7,
    pilot_expires: null,
    acv: 36000, term: 1, renewal: '2026-06-18',
    agents_licensed: 10, decisions_included: '1M/mo',
  },
  {
    tenant_id: 'st-luke-health-system',
    name: "St. Luke's Health System",
    status: 'active',
    created_at: '2026-01-07T08:00:00Z',
    active_key_count: 5, total_key_count: 5,
    decisions_today: 2203, block_rate: 1.8, trend: 'stable',
    city: 'Houston, TX', agents: 19,
    pilot_expires: null,
    acv: 84000, term: 3, renewal: '2029-01-07',
    agents_licensed: 25, decisions_included: '5M/mo',
  },
  {
    tenant_id: 'valley-orthopedic-group',
    name: 'Valley Orthopedic Group',
    status: 'active',
    created_at: '2026-02-14T11:45:00Z',
    active_key_count: 2, total_key_count: 2,
    decisions_today: 312, block_rate: 0.6, trend: 'up',
    city: 'Phoenix, AZ', agents: 3,
    pilot_expires: null,
    acv: 24000, term: 1, renewal: '2027-02-14',
    agents_licensed: 5, decisions_included: '500k/mo',
  },
  {
    tenant_id: 'coastal-pediatrics',
    name: 'Coastal Pediatrics Network',
    status: 'active',
    created_at: '2026-02-28T16:20:00Z',
    active_key_count: 2, total_key_count: 3,
    decisions_today: 441, block_rate: 3.4, trend: 'down',
    city: 'Miami, FL', agents: 4,
    pilot_expires: null,
    acv: 30000, term: 1, renewal: '2026-06-28',
    agents_licensed: 6, decisions_included: '750k/mo',
  },
  {
    tenant_id: 'pinnacle-oncology',
    name: 'Pinnacle Oncology Institute',
    status: 'active',
    created_at: '2026-03-05T10:00:00Z',
    active_key_count: 3, total_key_count: 3,
    decisions_today: 689, block_rate: 4.2, trend: 'stable',
    city: 'Boston, MA', agents: 8,
    pilot_expires: null,
    acv: 48000, term: 2, renewal: '2028-03-05',
    agents_licensed: 12, decisions_included: '1.5M/mo',
  },
  {
    tenant_id: 'riverdale-urgent-care',
    name: 'Riverdale Urgent Care',
    status: 'active',
    created_at: '2026-03-19T13:15:00Z',
    active_key_count: 1, total_key_count: 1,
    decisions_today: 88, block_rate: 1.1, trend: 'up',
    city: 'Denver, CO', agents: 2,
    pilot_expires: null,
    acv: 18000, term: 1, renewal: '2026-05-19',
    agents_licensed: 4, decisions_included: '250k/mo',
  },
  {
    tenant_id: 'summit-behavioral-health',
    name: 'Summit Behavioral Health',
    status: 'suspended',
    created_at: '2025-10-22T09:00:00Z',
    active_key_count: 0, total_key_count: 2,
    decisions_today: 0, block_rate: 0, trend: 'stable',
    city: 'Seattle, WA', agents: 0,
    pilot_expires: null,
    acv: 0, term: 1, renewal: null,
    agents_licensed: 5, decisions_included: '500k/mo',
  },
  // ── Pilot clients
  {
    tenant_id: 'cedar-valley-medical',
    name: 'Cedar Valley Medical Group',
    status: 'pilot',
    created_at: '2026-03-15T10:00:00Z',
    active_key_count: 2, total_key_count: 2,
    decisions_today: 234, block_rate: 3.1, trend: 'up',
    city: 'New York, NY', agents: 5,
    pilot_expires: '2026-04-30T00:00:00Z',
    acv: 0, term: 0, renewal: null,
    agents_licensed: 10, decisions_included: 'unlimited (pilot)',
  },
  {
    tenant_id: 'redwood-health-partners',
    name: 'Redwood Health Partners',
    status: 'pilot',
    created_at: '2026-03-28T14:00:00Z',
    active_key_count: 1, total_key_count: 1,
    decisions_today: 89, block_rate: 1.7, trend: 'up',
    city: 'San Francisco, CA', agents: 3,
    pilot_expires: '2026-05-15T00:00:00Z',
    acv: 0, term: 0, renewal: null,
    agents_licensed: 8, decisions_included: 'unlimited (pilot)',
  },
  {
    tenant_id: 'lakeside-rehab-center',
    name: 'Lakeside Rehabilitation Center',
    status: 'pilot',
    created_at: '2026-04-01T09:00:00Z',
    active_key_count: 2, total_key_count: 2,
    decisions_today: 156, block_rate: 2.4, trend: 'stable',
    city: 'Minneapolis, MN', agents: 4,
    pilot_expires: '2026-04-20T00:00:00Z',
    acv: 0, term: 0, renewal: null,
    agents_licensed: 8, decisions_included: 'unlimited (pilot)',
  },
]

const MOCK_AUDIT = [
  { id: 'a1', timestamp: '2026-04-07T14:32:11Z', action_type: 'support_key_created', tenant_affected: 'mercy-general-hospital', performed_by_ip: '198.51.100.42', bootstrap_key_hint: 'edon-b…(len=48)', details: { key_id: 'sk_7f3a', label: 'EDON Support 2026-04-07 14:32' } },
  { id: 'a2', timestamp: '2026-04-07T11:18:05Z', action_type: 'tenant_updated', tenant_affected: 'valley-orthopedic-group', performed_by_ip: '198.51.100.42', bootstrap_key_hint: 'edon-b…(len=48)', details: { contract: 'renewed 1yr', acv: '$24,000' } },
  { id: 'a3', timestamp: '2026-04-07T09:44:30Z', action_type: 'bootstrap_key_provisioned', tenant_affected: 'riverdale-urgent-care', performed_by_ip: '198.51.100.42', bootstrap_key_hint: 'edon-b…(len=48)', details: { key_id: 'ak_9c2d', role: 'admin' } },
  { id: 'a4', timestamp: '2026-04-06T17:02:44Z', action_type: 'tenant_updated', tenant_affected: 'summit-behavioral-health', performed_by_ip: '198.51.100.42', bootstrap_key_hint: 'edon-b…(len=48)', details: { status: 'suspended' } },
  { id: 'a5', timestamp: '2026-04-06T14:55:18Z', action_type: 'bootstrap_key_provisioned', tenant_affected: 'pinnacle-oncology', performed_by_ip: '203.0.113.15', bootstrap_key_hint: 'edon-b…(len=48)', details: { key_id: 'ak_4e8b', acv: '$48,000' } },
  { id: 'a6', timestamp: '2026-04-06T10:30:00Z', action_type: 'support_key_created', tenant_affected: 'northside-medical-center', performed_by_ip: '198.51.100.42', bootstrap_key_hint: 'edon-b…(len=48)', details: { key_id: 'sk_2a1f', label: 'EDON Support 2026-04-06 10:30' } },
  { id: 'a7', timestamp: '2026-04-05T16:14:09Z', action_type: 'ip_allowlist_add', tenant_affected: 'mercy-general-hospital', performed_by_ip: '198.51.100.42', bootstrap_key_hint: 'edon-b…(len=48)', details: { cidr: '10.12.0.0/16' } },
  { id: 'a8', timestamp: '2026-04-05T09:00:00Z', action_type: 'bootstrap_key_provisioned', tenant_affected: 'coastal-pediatrics', performed_by_ip: '203.0.113.15', bootstrap_key_hint: 'edon-b…(len=48)', details: { key_id: 'ak_7d3c' } },
  { id: 'a9', timestamp: '2026-04-04T20:45:33Z', action_type: 'ip_brute_force_unlocked', tenant_affected: null, performed_by_ip: '198.51.100.42', bootstrap_key_hint: 'edon-b…(len=48)', details: { unlocked_ip: '10.0.5.88' } },
  { id: 'a10', timestamp: '2026-04-04T15:22:17Z', action_type: 'tenant_updated', tenant_affected: 'st-luke-health-system', performed_by_ip: '198.51.100.42', bootstrap_key_hint: 'edon-b…(len=48)', details: { contract: 'upsell 3yr signed', acv: '$84,000' } },
]

const MOCK_USAGE = [
  { tenant_id: 'st-luke-health-system',     name: "St. Luke's Health System",      calls_30d: 782340, avg_latency: 29, rate_limit_hits: 0,  block_rate: 1.8, p99_latency: 140 },
  { tenant_id: 'mercy-general-hospital',    name: 'Mercy General Hospital',        calls_30d: 654210, avg_latency: 34, rate_limit_hits: 2,  block_rate: 2.3, p99_latency: 162 },
  { tenant_id: 'pinnacle-oncology',         name: 'Pinnacle Oncology Institute',   calls_30d: 244800, avg_latency: 41, rate_limit_hits: 0,  block_rate: 4.2, p99_latency: 198 },
  { tenant_id: 'northside-medical-center',  name: 'Northside Medical Center',      calls_30d: 188400, avg_latency: 31, rate_limit_hits: 1,  block_rate: 5.1, p99_latency: 155 },
  { tenant_id: 'coastal-pediatrics',        name: 'Coastal Pediatrics Network',    calls_30d:  94320, avg_latency: 38, rate_limit_hits: 18, block_rate: 3.4, p99_latency: 210 },
  { tenant_id: 'valley-orthopedic-group',   name: 'Valley Orthopedic Group',       calls_30d:  72100, avg_latency: 27, rate_limit_hits: 0,  block_rate: 0.6, p99_latency: 118 },
  { tenant_id: 'cedar-valley-medical',      name: 'Cedar Valley Medical Group',    calls_30d:  43200, avg_latency: 35, rate_limit_hits: 2,  block_rate: 3.1, p99_latency: 177 },
  { tenant_id: 'lakeside-rehab-center',     name: 'Lakeside Rehabilitation Center',calls_30d:  28100, avg_latency: 32, rate_limit_hits: 0,  block_rate: 2.4, p99_latency: 149 },
  { tenant_id: 'redwood-health-partners',   name: 'Redwood Health Partners',       calls_30d:  16400, avg_latency: 29, rate_limit_hits: 0,  block_rate: 1.7, p99_latency: 131 },
  { tenant_id: 'riverdale-urgent-care',     name: 'Riverdale Urgent Care',         calls_30d:   9820, avg_latency: 28, rate_limit_hits: 0,  block_rate: 1.1, p99_latency: 124 },
]

const MOCK_IP_ALLOWLISTS: Record<string, string[]> = {
  'mercy-general-hospital':    ['10.12.0.0/16', '192.168.50.0/24'],
  'st-luke-health-system':     ['10.50.0.0/16', '172.16.0.0/12'],
  'northside-medical-center':  ['10.24.0.0/20'],
  'pinnacle-oncology':         ['10.30.0.0/16', '192.168.100.0/24'],
  'cedar-valley-medical':      ['10.100.0.0/16'],
}

const ALL_FEATURES = [
  { id: 'hipaa_advanced_audit',       label: 'HIPAA Advanced Audit',        description: 'Extended audit log retention + tamper-evident export' },
  { id: 'custom_policy_packs',        label: 'Custom Policy Packs',         description: 'Upload and deploy custom governance rule sets' },
  { id: 'sso_saml',                   label: 'SSO / SAML',                  description: 'Single sign-on via SAML 2.0 identity providers' },
  { id: 'multi_agent_orchestration',  label: 'Multi-Agent Orchestration',   description: 'Coordinate multiple AI agents with shared policies' },
  { id: 'real_time_webhooks',         label: 'Real-Time Webhooks',          description: 'Push decision events to external systems instantly' },
  { id: 'telegram_alerts',            label: 'Telegram Alerts',             description: 'Governance alerts and daily summaries via Telegram' },
  { id: 'api_rate_limit_override',    label: 'Rate Limit Override',         description: 'Custom rate limits above contract default (admin-set)' },
]

const INITIAL_FLAGS: Record<string, Record<string, boolean>> = {
  'riverdale-urgent-care':    { telegram_alerts: true },
  'cedar-valley-medical':     { hipaa_advanced_audit: true, custom_policy_packs: true, sso_saml: true, multi_agent_orchestration: true, real_time_webhooks: true, telegram_alerts: true },
  'redwood-health-partners':  { real_time_webhooks: true, telegram_alerts: true },
  'lakeside-rehab-center':    { hipaa_advanced_audit: true, custom_policy_packs: true, sso_saml: true, multi_agent_orchestration: true, real_time_webhooks: true, telegram_alerts: true },
  'valley-orthopedic-group':  { real_time_webhooks: true, telegram_alerts: true },
  'coastal-pediatrics':       { telegram_alerts: true },
  'mercy-general-hospital':   { hipaa_advanced_audit: true, custom_policy_packs: true, sso_saml: true, multi_agent_orchestration: true, real_time_webhooks: true, telegram_alerts: true },
  'st-luke-health-system':    { hipaa_advanced_audit: true, custom_policy_packs: true, sso_saml: true, multi_agent_orchestration: true, real_time_webhooks: true, telegram_alerts: true, api_rate_limit_override: true },
  'northside-medical-center': { hipaa_advanced_audit: true, custom_policy_packs: true, sso_saml: true, multi_agent_orchestration: true, real_time_webhooks: true, telegram_alerts: true },
  'pinnacle-oncology':        { hipaa_advanced_audit: true, custom_policy_packs: true, sso_saml: true, multi_agent_orchestration: true, real_time_webhooks: true, telegram_alerts: true },
}

const MOCK_SUPPORT_KEYS = [
  { id: 'sk_7f3a', tenant_id: 'mercy-general-hospital',   tenant_name: 'Mercy General Hospital',    label: 'EDON Support 2026-04-07 14:32', created_at: '2026-04-07T14:32:11Z', created_by_ip: '198.51.100.42', expires_at: '2026-04-14T14:32:11Z', status: 'active'  },
  { id: 'sk_2a1f', tenant_id: 'northside-medical-center', tenant_name: 'Northside Medical Center',  label: 'EDON Support 2026-04-06 10:30', created_at: '2026-04-06T10:30:00Z', created_by_ip: '198.51.100.42', expires_at: '2026-04-13T10:30:00Z', status: 'active'  },
  { id: 'sk_4b9e', tenant_id: 'st-luke-health-system',    tenant_name: "St. Luke's Health System",  label: 'EDON Support 2026-03-28 09:14', created_at: '2026-03-28T09:14:22Z', created_by_ip: '198.51.100.42', expires_at: '2026-04-04T09:14:22Z', status: 'expired' },
  { id: 'sk_1c7d', tenant_id: 'pinnacle-oncology',        tenant_name: 'Pinnacle Oncology Institute',label: 'EDON Support 2026-03-15 16:05', created_at: '2026-03-15T16:05:44Z', created_by_ip: '203.0.113.15', expires_at: '2026-03-22T16:05:44Z', status: 'expired' },
  { id: 'sk_8e3f', tenant_id: 'coastal-pediatrics',       tenant_name: 'Coastal Pediatrics Network',label: 'EDON Support 2026-03-02 11:20', created_at: '2026-03-02T11:20:00Z', created_by_ip: '198.51.100.42', expires_at: '2026-03-09T11:20:00Z', status: 'expired' },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function daysUntil(iso: string) {
  return Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000)
}

function fmtAcv(n: number) {
  return n >= 1000 ? `$${(n / 1000).toFixed(0)}k` : `$${n}`
}

function fmtTime(iso: string) {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return new Date(iso).toLocaleDateString()
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

// ── Shared UI ─────────────────────────────────────────────────────────────────

function Badge({ label, color }: { label: string; color: string }) {
  return <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${color}`}>{label}</span>
}

const STATUS_COLOR: Record<string, string> = {
  active:    'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  pilot:     'text-teal-400 bg-teal-500/10 border-teal-500/20',
  suspended: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
}
const ACTION_COLOR: Record<string, string> = {
  bootstrap_key_provisioned: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  tenant_updated:            'text-blue-400 bg-blue-500/10 border-blue-500/20',
  support_key_created:       'text-purple-400 bg-purple-500/10 border-purple-500/20',
  ip_allowlist_add:          'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
  ip_allowlist_remove:       'text-orange-400 bg-orange-500/10 border-orange-500/20',
  ip_brute_force_unlocked:   'text-amber-400 bg-amber-500/10 border-amber-500/20',
}

function Toast({ msg, onClose }: { msg: string; onClose: () => void }) {
  useEffect(() => { const t = setTimeout(onClose, 3000); return () => clearTimeout(t) }, [onClose])
  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 16 }}
      className="fixed bottom-5 right-5 z-50 flex items-center gap-2 px-4 py-2.5 rounded-xl border bg-emerald-500/15 border-emerald-500/30 text-emerald-400 text-sm font-medium shadow-xl">
      <CheckCircle2 size={14} />{msg}
      <button onClick={onClose}><X size={12} className="opacity-60" /></button>
    </motion.div>
  )
}

// ── Overview Tab ──────────────────────────────────────────────────────────────

function OverviewTab() {
  const paying = MOCK_TENANTS.filter(t => t.status === 'active' && t.acv > 0)
  const pilots  = MOCK_TENANTS.filter(t => t.status === 'pilot')
  const arr     = paying.reduce((s, t) => s + t.acv, 0)
  const renewingSoon = paying.filter(t => t.renewal && daysUntil(t.renewal) <= 90)
  const totalDecisions = MOCK_TENANTS.reduce((s, t) => s + t.decisions_today, 0)
  const recentAudit = MOCK_AUDIT.slice(0, 4)

  return (
    <div className="space-y-5 fade-in">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'ARR',              value: fmtAcv(arr),                       icon: DollarSign,   color: 'text-emerald-400', sub: `${paying.length} active contracts` },
          { label: 'Avg Contract',     value: fmtAcv(Math.round(arr / paying.length)), icon: FileText, color: 'text-blue-400',    sub: 'avg ACV' },
          { label: 'Decisions Today',  value: totalDecisions.toLocaleString(),    icon: Shield,       color: 'text-primary',     sub: 'across all clients' },
          { label: 'Renewing ≤90d',    value: renewingSoon.length,               icon: CalendarClock, color: renewingSoon.length > 0 ? 'text-amber-400' : 'text-emerald-400', sub: renewingSoon.map(t => t.name.split(' ')[0]).join(', ') || 'none upcoming' },
        ].map(c => (
          <div key={c.label} className="glass-card p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{c.label}</span>
              <c.icon size={14} className={c.color} />
            </div>
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
            <p className="text-[11px] text-muted-foreground/60 truncate">{c.sub}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Contract breakdown */}
        <div className="glass-card p-5 space-y-3">
          <h3 className="text-sm font-semibold flex items-center gap-2"><FileText size={13} className="text-primary" /> Contract Breakdown</h3>
          <div className="space-y-2.5">
            {([1, 2, 3] as const).map(term => {
              const group = paying.filter(t => t.term === term)
              if (!group.length) return null
              const groupArr = group.reduce((s, t) => s + t.acv, 0)
              return (
                <div key={term} className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground w-14 shrink-0">{term}-year</span>
                  <div className="flex-1 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                    <div className="h-full rounded-full bg-primary/60" style={{ width: `${(groupArr / arr) * 100}%` }} />
                  </div>
                  <span className="text-xs font-semibold w-12 text-right">{fmtAcv(groupArr)}</span>
                  <span className="text-[10px] text-muted-foreground/50 w-8">{group.length} co.</span>
                </div>
              )
            })}
          </div>
          <div className="pt-1 border-t border-border/50 flex items-center justify-between text-xs text-muted-foreground">
            <span className="flex items-center gap-1"><FlaskConical size={11} className="text-teal-400" /> Pilot pipeline</span>
            <span className="text-teal-400 font-semibold">{pilots.length} orgs evaluating</span>
          </div>
        </div>

        {/* Recent admin actions */}
        <div className="glass-card p-5 space-y-3">
          <h3 className="text-sm font-semibold flex items-center gap-2"><ScrollText size={13} className="text-primary" /> Recent Admin Actions</h3>
          <div className="space-y-2">
            {recentAudit.map(e => (
              <div key={e.id} className="flex items-start gap-2.5">
                <div className="w-1.5 h-1.5 rounded-full bg-primary/60 shrink-0 mt-1.5" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`px-1.5 py-0 rounded text-[10px] font-semibold border ${ACTION_COLOR[e.action_type] || 'text-muted-foreground bg-muted/30 border-border'}`}>
                      {e.action_type.replace(/_/g, ' ')}
                    </span>
                    {e.tenant_affected && <span className="text-xs font-mono text-primary truncate">{e.tenant_affected}</span>}
                  </div>
                  <span className="text-[11px] text-muted-foreground/50">{fmtTime(e.timestamp)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Gateway health */}
      <div className="glass-card p-5 space-y-4">
        <h3 className="text-sm font-semibold flex items-center gap-2"><Server size={13} className="text-primary" /> Gateway Health</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-1">
          {[
            { label: 'p50 Latency',    value: '12ms',      color: 'text-emerald-400' },
            { label: 'p95 Latency',    value: '48ms',      color: 'text-emerald-400' },
            { label: 'p99 Latency',    value: '142ms',     color: 'text-amber-400'   },
            { label: 'Error Rate',     value: '0.02%',     color: 'text-emerald-400' },
            { label: 'Request Rate',   value: '847 req/m', color: 'text-blue-400'    },
            { label: '30d Uptime',     value: '99.98%',    color: 'text-emerald-400' },
            { label: 'Active Keys',    value: String(MOCK_TENANTS.reduce((s, t) => s + t.active_key_count, 0)), color: 'text-foreground' },
            { label: 'Version',        value: 'v1.0.1',    color: 'text-muted-foreground' },
          ].map(m => (
            <div key={m.label} className="bg-muted/20 rounded-lg px-3 py-2.5 border border-border/40">
              <p className="text-[10px] text-muted-foreground mb-0.5">{m.label}</p>
              <p className={`text-sm font-semibold ${m.color}`}>{m.value}</p>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {['Database','Auth Middleware','Policy Engine','Audit Logger','Rate Limiter','Telegram','RBAC','Encryption'].map((name, i) => (
            <div key={name} className="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/20 border border-border/40">
              <span className="text-xs text-muted-foreground">{name}</span>
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot" />
                <span className="text-[10px] text-muted-foreground/50">{['1.2ms','0.4ms','2.1ms','0.8ms','0.3ms','48ms','0.2ms','0.6ms'][i]}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Clients Tab ───────────────────────────────────────────────────────────────

function ClientsTab({ toast }: { toast: (msg: string) => void }) {
  const [search, setSearch]   = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [filter, setFilter]   = useState<'all' | 'active' | 'pilot' | 'suspended'>('all')

  const filtered = MOCK_TENANTS.filter(t => {
    const matchSearch = t.tenant_id.includes(search.toLowerCase()) || t.name.toLowerCase().includes(search.toLowerCase())
    return matchSearch && (filter === 'all' || t.status === filter)
  })

  return (
    <div className="space-y-4 fade-in">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search clients…"
            className="w-full pl-8 pr-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
        </div>
        <div className="flex rounded-lg border border-border overflow-hidden text-xs">
          {(['all','active','pilot','suspended'] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-2 capitalize transition ${filter === f ? 'bg-primary text-primary-foreground font-semibold' : 'text-muted-foreground hover:text-foreground hover:bg-muted/40'}`}>
              {f}
            </button>
          ))}
        </div>
        <button onClick={() => { setShowNew(v => !v); toast('Demo: New client form opened') }}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition">
          <Plus size={13} /> New Client
        </button>
      </div>

      {(filter === 'all' || filter === 'pilot') && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-teal-500/8 border border-teal-500/20 text-xs text-teal-400">
          <FlaskConical size={13} />
          <span><strong>3 pilots in evaluation</strong> · Lakeside expires in {daysUntil('2026-04-20T00:00:00Z')}d</span>
        </div>
      )}

      <AnimatePresence>
        {showNew && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            className="glass-card p-5 overflow-hidden border-primary/20">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold flex items-center gap-2"><Building2 size={13} className="text-primary" /> Onboard New Client</h3>
              <button onClick={() => setShowNew(false)}><X size={14} className="text-muted-foreground" /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {[['Tenant ID','e.g. hospital-name'],['Organisation Name','e.g. Mercy General'],['Primary Email','admin@hospital.com'],['Contract ACV','e.g. $48,000']].map(([label, ph]) => (
                <div key={label}>
                  <label className="text-xs text-muted-foreground mb-1 block">{label}</label>
                  <input readOnly placeholder={ph} className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm text-muted-foreground/50 cursor-default" />
                </div>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-4 text-xs">
              <label className="text-muted-foreground">Contract term:</label>
              {['1-year','2-year','3-year'].map(t => (
                <button key={t} onClick={() => toast(`Demo: ${t} selected`)} className="px-2.5 py-1 rounded-lg border border-border text-muted-foreground hover:border-primary/40 hover:text-primary transition">{t}</button>
              ))}
              <button onClick={() => toast('Demo: Pilot mode toggled')} className="flex items-center gap-1.5 text-teal-400 font-medium ml-auto">
                <ToggleRight size={16} /> Start as pilot
              </button>
            </div>
            <div className="mt-4">
              <label className="text-xs text-muted-foreground mb-1 block">Generated Admin Key</label>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-[11px] font-mono bg-muted/30 px-2 py-1.5 rounded border border-border text-muted-foreground/50">edon-admin-Kx7mP2nQvR9sT4wY...</code>
                <button onClick={() => toast('Demo: Key copied')} className="p-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground transition"><Copy size={12} /></button>
              </div>
            </div>
            <button onClick={() => { setShowNew(false); toast('Demo: Client provisioned') }}
              className="mt-4 flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition">
              <Plus size={12} /> Provision Client
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="space-y-2">
        {filtered.map(t => {
          const isOpen = expanded === t.tenant_id
          const renewDays = t.renewal ? daysUntil(t.renewal) : null
          const renewSoon = renewDays !== null && renewDays <= 90

          return (
            <div key={t.tenant_id} className={`glass-card overflow-hidden ${renewSoon ? 'border-amber-500/20' : ''}`}>
              <button className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-white/[0.02] transition"
                onClick={() => setExpanded(isOpen ? null : t.tenant_id)}>
                <Building2 size={15} className="text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium truncate">{t.name}</p>
                    {t.status === 'pilot' && <FlaskConical size={11} className="text-teal-400 shrink-0" />}
                    {renewSoon && <span className="text-[10px] font-semibold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1.5 rounded">renews {renewDays}d</span>}
                  </div>
                  <p className="text-[11px] text-muted-foreground font-mono">{t.tenant_id} · {t.city}</p>
                </div>
                <div className="hidden sm:flex items-center gap-2 shrink-0">
                  <Badge label={t.status} color={STATUS_COLOR[t.status] || ''} />
                  {t.acv > 0 && <span className="text-xs font-semibold text-emerald-400">{fmtAcv(t.acv)}/yr</span>}
                  {t.term > 0 && <span className="text-xs text-muted-foreground">{t.term}yr contract</span>}
                  <span className="text-xs text-muted-foreground">{t.decisions_today.toLocaleString()} decisions</span>
                  {t.trend === 'up'     && <TrendingUp   size={13} className="text-emerald-400" />}
                  {t.trend === 'down'   && <TrendingDown size={13} className="text-red-400" />}
                  {t.trend === 'stable' && <Minus        size={13} className="text-muted-foreground" />}
                </div>
                {isOpen ? <ChevronUp size={14} className="text-muted-foreground shrink-0" /> : <ChevronDown size={14} className="text-muted-foreground shrink-0" />}
              </button>

              <AnimatePresence>
                {isOpen && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden border-t border-border/50">
                    <div className="px-5 py-4 space-y-4">
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        {[
                          { label: 'ACV',               value: t.acv > 0 ? fmtAcv(t.acv) + '/yr' : t.status === 'pilot' ? 'Pilot (free)' : '—' },
                          { label: 'Contract Term',     value: t.term > 0 ? `${t.term}-year` : t.status === 'pilot' ? 'Pilot eval' : '—' },
                          { label: 'Agents Licensed',   value: t.agents_licensed },
                          { label: t.status === 'pilot' ? 'Pilot Expires' : t.renewal ? 'Renews' : 'Renewal', value: t.renewal ? fmtDate(t.renewal) : t.pilot_expires ? fmtDate(t.pilot_expires) : '—' },
                        ].map(s => (
                          <div key={s.label} className="bg-muted/20 rounded-lg px-3 py-2.5 border border-border/40">
                            <p className="text-[10px] text-muted-foreground mb-0.5">{s.label}</p>
                            <p className="text-sm font-semibold">{s.value}</p>
                          </div>
                        ))}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button onClick={() => toast(`Demo: Support key created for ${t.name}`)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-medium hover:bg-blue-500/20 transition">
                          <Eye size={12} /> Support Access
                        </button>
                        {t.status === 'pilot' && <>
                          <button onClick={() => toast(`Demo: Pilot extended for ${t.name}`)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-teal-500/10 border border-teal-500/20 text-teal-400 text-xs font-medium hover:bg-teal-500/20 transition">
                            <FlaskConical size={12} /> Extend Pilot
                          </button>
                          <button onClick={() => toast(`Demo: ${t.name} converted to contract`)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium hover:bg-emerald-500/20 transition">
                            <CheckCircle2 size={12} /> Convert to Contract
                          </button>
                        </>}
                        {renewSoon && (
                          <button onClick={() => toast(`Demo: Renewal started for ${t.name}`)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-medium hover:bg-amber-500/20 transition">
                            <CalendarClock size={12} /> Start Renewal
                          </button>
                        )}
                        {t.status === 'active' && (
                          <button onClick={() => toast(`Demo: ${t.name} suspended`)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-medium hover:bg-red-500/20 transition">
                            <Power size={12} /> Suspend
                          </button>
                        )}
                        {t.status === 'suspended' && (
                          <button onClick={() => toast(`Demo: ${t.name} reactivated`)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium hover:bg-emerald-500/20 transition">
                            <CheckCircle2 size={12} /> Reactivate
                          </button>
                        )}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Billing Tab ───────────────────────────────────────────────────────────────

function BillingTab() {
  const paying   = MOCK_TENANTS.filter(t => t.status === 'active' && t.acv > 0)
  const pilots   = MOCK_TENANTS.filter(t => t.status === 'pilot')
  const arr      = paying.reduce((s, t) => s + t.acv, 0)
  const tcv      = paying.reduce((s, t) => s + t.acv * t.term, 0)
  const avgAcv   = Math.round(arr / paying.length)
  const pilotPotential = 50000 * pilots.length // estimated avg ACV if converted
  const renewingSoon = paying.filter(t => t.renewal && daysUntil(t.renewal) <= 90)

  const monthly = [
    { month: 'Nov', arr: 96000 }, { month: 'Dec', arr: 132000 }, { month: 'Jan', arr: 198000 },
    { month: 'Feb', arr: 252000 }, { month: 'Mar', arr: 282000 }, { month: 'Apr', arr: arr },
  ]
  const maxArr = Math.max(...monthly.map(m => m.arr))

  return (
    <div className="space-y-5 fade-in">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'ARR',           value: fmtAcv(arr),      sub: `${paying.length} active contracts`, color: 'text-emerald-400' },
          { label: 'Avg ACV',       value: fmtAcv(avgAcv),   sub: 'per contract',                      color: 'text-blue-400'    },
          { label: 'Total TCV',     value: fmtAcv(tcv),      sub: 'committed revenue',                 color: 'text-primary'     },
          { label: 'Pilot Pipeline',value: fmtAcv(pilotPotential), sub: `${pilots.length} orgs in eval`, color: 'text-teal-400'  },
        ].map(c => (
          <div key={c.label} className="glass-card p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{c.label}</span>
              <DollarSign size={13} className={c.color} />
            </div>
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
            <p className="text-[11px] text-muted-foreground/60">{c.sub}</p>
          </div>
        ))}
      </div>

      {renewingSoon.length > 0 && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-amber-500/8 border border-amber-500/20 text-xs text-amber-400">
          <CalendarClock size={13} />
          <span><strong>{renewingSoon.length} contract{renewingSoon.length > 1 ? 's' : ''}</strong> renewing in the next 90 days: {renewingSoon.map(t => `${t.name} (${daysUntil(t.renewal!)}d)`).join(', ')}</span>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* ARR growth */}
        <div className="glass-card p-5 space-y-3">
          <h3 className="text-sm font-semibold flex items-center gap-2"><TrendingUp size={13} className="text-emerald-400" /> ARR Growth</h3>
          <div className="flex items-end gap-2 h-24">
            {monthly.map(m => (
              <div key={m.month} className="flex-1 flex flex-col items-center gap-1">
                <span className="text-[9px] text-muted-foreground/60">{fmtAcv(m.arr)}</span>
                <div className="w-full rounded-t-sm bg-emerald-500/30 border-t border-emerald-500/50" style={{ height: `${(m.arr / maxArr) * 68}px` }} />
                <span className="text-[10px] text-muted-foreground/50">{m.month}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Contract term split */}
        <div className="glass-card p-5 space-y-3">
          <h3 className="text-sm font-semibold flex items-center gap-2"><FileText size={13} className="text-primary" /> ARR by Contract Term</h3>
          <div className="space-y-3">
            {([1, 2, 3] as const).map(term => {
              const group = paying.filter(t => t.term === term)
              if (!group.length) return null
              const groupArr = group.reduce((s, t) => s + t.acv, 0)
              return (
                <div key={term} className="space-y-1.5">
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">{term}-year contracts <span className="text-muted-foreground/50">({group.length})</span></span>
                    <span className="font-semibold">{fmtAcv(groupArr)}/yr</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-muted/50 overflow-hidden">
                    <div className="h-full rounded-full bg-primary/60" style={{ width: `${(groupArr / arr) * 100}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
          <div className="pt-2 border-t border-border/50 flex justify-between text-xs">
            <span className="text-muted-foreground">TCV (multi-year committed)</span>
            <span className="font-semibold text-primary">{fmtAcv(tcv)}</span>
          </div>
        </div>
      </div>

      {/* All contracts table */}
      <div className="glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold">All Contracts</h3>
        <div className="space-y-1">
          {MOCK_TENANTS.filter(t => t.status !== 'suspended').sort((a, b) => b.acv - a.acv).map(t => {
            const renewDays = t.renewal ? daysUntil(t.renewal) : null
            return (
              <div key={t.tenant_id} className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted/20 transition text-xs">
                <Building2 size={12} className="text-muted-foreground shrink-0" />
                <span className="flex-1 truncate font-medium">{t.name}</span>
                <span className="text-muted-foreground hidden sm:block">{t.city}</span>
                <Badge label={t.status} color={STATUS_COLOR[t.status] || ''} />
                <span className="text-muted-foreground w-16 text-right">{t.term > 0 ? `${t.term}yr` : '—'}</span>
                {t.renewal && renewDays !== null && renewDays <= 90
                  ? <span className="text-amber-400 text-[10px] font-semibold w-20 text-right">renews {renewDays}d</span>
                  : <span className="text-muted-foreground/40 w-20 text-right text-[10px]">{t.renewal ? fmtDate(t.renewal) : t.status === 'pilot' ? 'pilot' : '—'}</span>
                }
                <span className={`w-20 text-right font-mono font-semibold ${t.acv > 0 ? 'text-emerald-400' : 'text-teal-400'}`}>
                  {t.acv > 0 ? `${fmtAcv(t.acv)}/yr` : 'pilot'}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── Usage Analytics Tab ───────────────────────────────────────────────────────

function UsageTab() {
  const totalCalls   = MOCK_USAGE.reduce((s, t) => s + t.calls_30d, 0)
  const totalHits    = MOCK_USAGE.reduce((s, t) => s + t.rate_limit_hits, 0)
  const avgLatency   = Math.round(MOCK_USAGE.reduce((s, t) => s + t.avg_latency, 0) / MOCK_USAGE.length)

  return (
    <div className="space-y-5 fade-in">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'API Calls (30d)',  value: `${(totalCalls / 1_000_000).toFixed(2)}M`, color: 'text-blue-400'    },
          { label: 'Avg Latency',      value: `${avgLatency}ms`,                         color: 'text-emerald-400' },
          { label: 'Rate Limit Hits',  value: totalHits, color: totalHits > 10 ? 'text-amber-400' : 'text-emerald-400' },
          { label: 'Active Clients',   value: MOCK_USAGE.length,                         color: 'text-foreground'  },
        ].map(c => (
          <div key={c.label} className="glass-card p-4 space-y-2">
            <span className="text-xs text-muted-foreground">{c.label}</span>
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
          </div>
        ))}
      </div>

      <div className="glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold flex items-center gap-2"><BarChart2 size={13} className="text-primary" /> Call Volume — Top Consumers (30d)</h3>
        <div className="space-y-2.5">
          {MOCK_USAGE.slice(0, 6).map((t, i) => (
            <div key={t.tenant_id} className="flex items-center gap-3">
              <span className="text-[10px] text-muted-foreground/50 w-4 text-right">{i + 1}</span>
              <span className="text-xs truncate w-48">{t.name}</span>
              <div className="flex-1 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                <div className="h-full rounded-full bg-blue-500/60" style={{ width: `${(t.calls_30d / MOCK_USAGE[0].calls_30d) * 100}%` }} />
              </div>
              <span className="text-xs font-mono text-muted-foreground w-16 text-right">{(t.calls_30d / 1000).toFixed(0)}k</span>
            </div>
          ))}
        </div>
      </div>

      <div className="glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold">Per-Client Metrics</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted-foreground/70 border-b border-border/40">
                <th className="text-left pb-2 font-medium">Client</th>
                <th className="text-right pb-2 font-medium">API Calls</th>
                <th className="text-right pb-2 font-medium">Avg</th>
                <th className="text-right pb-2 font-medium">p99</th>
                <th className="text-right pb-2 font-medium">Block %</th>
                <th className="text-right pb-2 font-medium">Rate Hits</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/20">
              {MOCK_USAGE.map(t => (
                <tr key={t.tenant_id} className="hover:bg-muted/10 transition">
                  <td className="py-2 font-medium truncate max-w-[160px]">{t.name}</td>
                  <td className="py-2 text-right font-mono">{(t.calls_30d / 1000).toFixed(0)}k</td>
                  <td className="py-2 text-right font-mono">{t.avg_latency}ms</td>
                  <td className={`py-2 text-right font-mono ${t.p99_latency > 200 ? 'text-amber-400' : 'text-muted-foreground'}`}>{t.p99_latency}ms</td>
                  <td className="py-2 text-right font-mono">{t.block_rate}%</td>
                  <td className={`py-2 text-right font-mono ${t.rate_limit_hits > 5 ? 'text-amber-400 font-semibold' : 'text-muted-foreground'}`}>{t.rate_limit_hits}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {totalHits > 0 && (
          <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-500/8 border border-amber-500/20 rounded-lg px-3 py-2">
            <AlertCircle size={12} />
            Coastal Pediatrics has {MOCK_USAGE.find(t => t.tenant_id === 'coastal-pediatrics')?.rate_limit_hits} rate limit hits this month — consider a contract volume upgrade conversation.
          </div>
        )}
      </div>
    </div>
  )
}

// ── IP Allowlist Tab ──────────────────────────────────────────────────────────

function IPAllowlistTab({ toast }: { toast: (msg: string) => void }) {
  const [allowlists, setAllowlists] = useState<Record<string, string[]>>(MOCK_IP_ALLOWLISTS)
  const [newCidr, setNewCidr] = useState<Record<string, string>>({})

  function addCidr(tenantId: string) {
    const cidr = newCidr[tenantId]?.trim()
    if (!cidr) return
    setAllowlists(prev => ({ ...prev, [tenantId]: [...(prev[tenantId] || []), cidr] }))
    setNewCidr(prev => ({ ...prev, [tenantId]: '' }))
    toast(`Demo: ${cidr} added to ${tenantId}`)
  }

  return (
    <div className="space-y-4 fade-in">
      <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-blue-500/8 border border-blue-500/20 text-xs text-blue-400">
        <Lock size={12} />
        IP allowlists restrict which source IPs can reach the EDON gateway per client. Clients with no allowlist accept requests from any IP.
      </div>
      <div className="space-y-3">
        {MOCK_TENANTS.filter(t => t.status !== 'suspended').map(t => {
          const cidrs = allowlists[t.tenant_id] || []
          return (
            <div key={t.tenant_id} className="glass-card p-4 space-y-3">
              <div className="flex items-center gap-3">
                <Globe size={14} className="text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{t.name}</p>
                  <p className="text-[11px] font-mono text-muted-foreground">{t.tenant_id}</p>
                </div>
                <div className="flex items-center gap-1.5 text-xs">
                  {cidrs.length > 0
                    ? <><div className="w-1.5 h-1.5 rounded-full bg-emerald-400" /><span className="text-emerald-400 font-medium">{cidrs.length} rule{cidrs.length !== 1 ? 's' : ''}</span></>
                    : <><div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40" /><span className="text-muted-foreground">unrestricted</span></>}
                </div>
              </div>
              {cidrs.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {cidrs.map(cidr => (
                    <div key={cidr} className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-mono">
                      {cidr}
                      <button onClick={() => { setAllowlists(p => ({ ...p, [t.tenant_id]: p[t.tenant_id].filter(c => c !== cidr) })); toast(`Demo: ${cidr} removed`) }}>
                        <X size={10} className="hover:text-red-400 transition" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <div className="flex items-center gap-2">
                <input value={newCidr[t.tenant_id] || ''} onChange={e => setNewCidr(p => ({ ...p, [t.tenant_id]: e.target.value }))}
                  placeholder="e.g. 10.0.0.0/8 or 203.0.113.5/32"
                  className="flex-1 px-3 py-1.5 rounded-lg bg-muted/50 border border-border text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary" />
                <button onClick={() => addCidr(t.tenant_id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 border border-primary/20 text-primary text-xs font-medium hover:bg-primary/20 transition shrink-0">
                  <Plus size={11} /> Add
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Feature Flags Tab ─────────────────────────────────────────────────────────

function FeatureFlagsTab({ toast }: { toast: (msg: string) => void }) {
  const [flags, setFlags] = useState<Record<string, Record<string, boolean>>>(INITIAL_FLAGS)
  const [selected, setSelected] = useState(MOCK_TENANTS[0].tenant_id)
  const tenant = MOCK_TENANTS.find(t => t.tenant_id === selected)!

  function toggle(featureId: string) {
    const cur = flags[selected]?.[featureId] ?? false
    setFlags(prev => ({ ...prev, [selected]: { ...(prev[selected] || {}), [featureId]: !cur } }))
    toast(`Demo: ${featureId} ${cur ? 'disabled' : 'enabled'} for ${tenant.name}`)
  }

  return (
    <div className="space-y-5 fade-in">
      <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-muted/20 border border-border/40 text-xs text-muted-foreground">
        <AlertCircle size={12} />
        Feature flags let you enable specific capabilities per client — useful for pilots, contract add-ons, and support escalations.
      </div>

      <div className="glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold">Select Client</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {MOCK_TENANTS.filter(t => t.status !== 'suspended').map(t => (
            <button key={t.tenant_id} onClick={() => setSelected(t.tenant_id)}
              className={`text-left px-3 py-2 rounded-lg border text-xs transition ${selected === t.tenant_id ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border/40 bg-muted/20 text-muted-foreground hover:text-foreground hover:bg-muted/40'}`}>
              <p className="font-medium truncate">{t.name}</p>
              <div className="flex items-center gap-1 mt-0.5">
                <Badge label={t.status} color={STATUS_COLOR[t.status] || ''} />
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="glass-card p-5 space-y-1">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">{tenant.name} — Features</h3>
          <Badge label={tenant.status} color={STATUS_COLOR[tenant.status] || ''} />
        </div>
        {ALL_FEATURES.map(f => {
          const enabled = flags[selected]?.[f.id] ?? false
          return (
            <div key={f.id} className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-muted/10 transition">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium">{f.label}</p>
                <p className="text-[11px] text-muted-foreground/60">{f.description}</p>
              </div>
              <button onClick={() => toggle(f.id)} className="shrink-0 transition hover:opacity-80">
                {enabled ? <ToggleRight size={20} className="text-primary" /> : <ToggleLeft size={20} className="text-muted-foreground/40" />}
              </button>
            </div>
          )
        })}
        {tenant.status === 'pilot' && (
          <div className="mt-3 pt-3 border-t border-border/40 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-teal-400">Pilot — all features enabled for evaluation</p>
              <p className="text-[11px] text-muted-foreground/60">Expires {fmtDate(tenant.pilot_expires!)}</p>
            </div>
            <button onClick={() => toast(`Demo: Pilot extended for ${tenant.name}`)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-teal-500/10 border border-teal-500/20 text-teal-400 text-xs font-medium hover:bg-teal-500/20 transition shrink-0">
              <Clock size={11} /> Extend 30d
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Support Keys Tab ──────────────────────────────────────────────────────────

function SupportKeysTab({ toast }: { toast: (msg: string) => void }) {
  const active  = MOCK_SUPPORT_KEYS.filter(k => k.status === 'active')
  const expired = MOCK_SUPPORT_KEYS.filter(k => k.status === 'expired')
  return (
    <div className="space-y-5 fade-in">
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Active Support Keys', value: active.length,                   color: 'text-blue-400'        },
          { label: 'Total Issued',        value: MOCK_SUPPORT_KEYS.length,        color: 'text-foreground'      },
          { label: 'Expired / Revoked',   value: expired.length,                  color: 'text-muted-foreground'},
        ].map(c => (
          <div key={c.label} className="glass-card p-4">
            <p className="text-xs text-muted-foreground mb-1">{c.label}</p>
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
          </div>
        ))}
      </div>
      <div className="glass-card p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold flex items-center gap-2"><UserCheck size={13} className="text-primary" /> Support Key Log</h3>
          <span className="text-xs text-muted-foreground">7-day expiry · read-only scoped access</span>
        </div>
        <div className="space-y-2">
          {MOCK_SUPPORT_KEYS.map(k => (
            <div key={k.id} className="flex items-center gap-3 px-3 py-3 rounded-lg border border-border/40 hover:bg-muted/10 transition text-xs">
              <div className={`w-2 h-2 rounded-full shrink-0 ${k.status === 'active' ? 'bg-blue-400 animate-pulse-dot' : 'bg-muted-foreground/30'}`} />
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{k.tenant_name}</p>
                <p className="text-[11px] text-muted-foreground/60">{k.label}</p>
              </div>
              <div className="hidden sm:block text-muted-foreground/60 shrink-0 text-right">
                <p>created {fmtTime(k.created_at)}</p>
                <p>from {k.created_by_ip}</p>
              </div>
              <div className="shrink-0 text-right">
                <p className={k.status === 'active' ? 'text-blue-400 font-medium' : 'text-muted-foreground/50'}>
                  {k.status === 'active' ? `expires ${fmtDate(k.expires_at)}` : 'expired'}
                </p>
                <p className="font-mono text-muted-foreground/40">{k.id}</p>
              </div>
              {k.status === 'active' && (
                <button onClick={() => toast(`Demo: ${k.id} revoked`)}
                  className="shrink-0 px-2 py-1 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-[10px] font-medium hover:bg-red-500/20 transition">
                  Revoke
                </button>
              )}
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground/50 flex items-center gap-1.5">
          <AlertCircle size={11} />
          All support key usage is captured in the immutable audit log.
        </p>
      </div>
    </div>
  )
}

// ── Recovery Tab ──────────────────────────────────────────────────────────────

function RecoveryTab({ toast }: { toast: (msg: string) => void }) {
  const [tenantId, setTenantId] = useState('')
  const [done, setDone] = useState(false)
  const mockKey = 'edon-admin-Kx7mP2nQvR9sT4wYhJ3cLpN8dZq5fX2'

  return (
    <div className="max-w-lg space-y-5 fade-in">
      <div className="glass-card p-5 border-amber-500/20 space-y-2">
        <h3 className="text-sm font-semibold flex items-center gap-2 text-amber-400"><KeyRound size={14} /> Emergency Admin Key Recovery</h3>
        <p className="text-xs text-muted-foreground">Provision a fresh admin key for any client using only the bootstrap secret. Every recovery is logged immutably.</p>
      </div>
      <AnimatePresence>
        {done && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
            className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/25 space-y-2">
            <p className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5"><CheckCircle2 size={12} /> Recovery key provisioned for <span className="font-mono">{tenantId}</span></p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-[11px] font-mono break-all bg-emerald-500/10 px-2 py-1.5 rounded border border-emerald-500/20 text-emerald-300 select-all">{mockKey}</code>
              <button onClick={() => toast('Key copied')}><Copy size={13} className="text-muted-foreground hover:text-foreground" /></button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      <form onSubmit={e => { e.preventDefault(); setDone(true); toast('Recovery key provisioned') }} className="glass-card p-5 space-y-4">
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Tenant ID</label>
          <input value={tenantId} onChange={e => setTenantId(e.target.value)} required placeholder="e.g. mercy-general-hospital"
            className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Key that will be created</label>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-[11px] font-mono break-all bg-muted/30 px-2 py-1.5 rounded border border-border text-muted-foreground select-all">{mockKey}</code>
            <button type="button" onClick={() => toast('Key copied')}><Copy size={12} className="text-muted-foreground hover:text-foreground" /></button>
          </div>
          <p className="text-[10px] text-muted-foreground/60 mt-1">Copy this before submitting.</p>
        </div>
        <button type="submit" className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-500/20 border border-amber-500/30 text-amber-400 text-sm font-semibold hover:bg-amber-500/30 transition">
          <KeyRound size={14} /> Provision Recovery Key
        </button>
      </form>
    </div>
  )
}

// ── Audit Log Tab ─────────────────────────────────────────────────────────────

function AuditLogTab() {
  const [filter, setFilter] = useState('')
  const filtered = MOCK_AUDIT.filter(e => !filter || (e.tenant_affected?.includes(filter) || e.action_type.includes(filter)))

  return (
    <div className="space-y-4 fade-in">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter by client or action…"
            className="w-full pl-8 pr-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
        </div>
        <span className="text-xs text-muted-foreground">{MOCK_AUDIT.length} entries · append-only</span>
        <div className="flex items-center gap-1.5 text-xs text-emerald-400">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot" /> Immutable
        </div>
      </div>
      <div className="space-y-2">
        {filtered.map((e, i) => (
          <motion.div key={e.id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
            className="glass-card px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
            <span className="text-xs text-muted-foreground/60 shrink-0 tabular-nums w-36">{fmtTime(e.timestamp)}</span>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border shrink-0 ${ACTION_COLOR[e.action_type] || 'text-muted-foreground bg-muted/30 border-border'}`}>
              {e.action_type.replace(/_/g, ' ')}
            </span>
            {e.tenant_affected && <span className="font-mono text-xs text-primary shrink-0">{e.tenant_affected}</span>}
            <span className="text-xs text-muted-foreground/50 shrink-0">IP: {e.performed_by_ip}</span>
            <span className="text-xs text-muted-foreground/40 truncate">
              {Object.entries(e.details).filter(([, v]) => v !== null).map(([k, v]) => `${k}: ${v}`).join(' · ')}
            </span>
          </motion.div>
        ))}
      </div>
      <div className="glass-card p-4 border-muted/20">
        <p className="text-xs text-muted-foreground/60 flex items-center gap-1.5">
          <AlertCircle size={12} />
          Audit log entries are append-only and cannot be modified or deleted. Every admin action is recorded with source IP and timestamp.
        </p>
      </div>
    </div>
  )
}

// ── Scale Tab ─────────────────────────────────────────────────────────────────

const SCALE_DATA = {
  // All-time cumulative totals
  decisions_total:   24_680_441,
  blocks_total:         847_312,
  api_calls_total:   86_420_000,
  audit_entries:         42_183,
  agents_ever:                67,
  clients_ever:               12,
  days_running:              157,
  // Milestones — [current, target, label]
  milestones: [
    { label: 'Decisions Governed',  current: 24_680_441, target: 25_000_000, unit: 'M',  fmt: (n: number) => `${(n/1e6).toFixed(2)}M` },
    { label: 'Harmful Blocks',      current:    847_312, target:  1_000_000, unit: 'M',  fmt: (n: number) => `${(n/1000).toFixed(0)}k`  },
    { label: 'API Calls Processed', current: 86_420_000, target: 100_000_000,unit: 'M', fmt: (n: number) => `${(n/1e6).toFixed(1)}M`  },
    { label: 'Paying Clients',      current:          7, target:         10, unit: '',   fmt: (n: number) => `${n}`                      },
    { label: 'AI Agents Governed',  current:         67, target:        100, unit: '',   fmt: (n: number) => `${n}`                      },
    { label: 'ARR',                 current:    300_000, target:    500_000, unit: '$',  fmt: (n: number) => `$${(n/1000).toFixed(0)}k`  },
  ],
  // Records
  records: [
    { label: 'Most decisions in a day',   value: '6,513',       who: "St. Luke's Health System",     date: 'Mar 15, 2026' },
    { label: 'Highest block rate',        value: '5.1%',        who: 'Northside Medical Center',     date: 'ongoing'      },
    { label: 'Most AI agents (1 client)', value: '19 agents',   who: "St. Luke's Health System",     date: 'current'      },
    { label: 'Fastest onboarding',        value: '47 minutes',  who: 'Riverdale Urgent Care',        date: 'Mar 19, 2026' },
    { label: 'Longest contract',          value: '3-year TCV',  who: "St. Luke's Health System",     date: 'Jan 7, 2026'  },
    { label: 'Highest ACV',              value: '$84k / yr',   who: "St. Luke's Health System",     date: 'signed Jan 2026' },
  ],
  // Monthly velocity (last 6 months)
  velocity: [
    { month: 'Nov', decisions: 820_000,  new_clients: 1, new_agents: 12 },
    { month: 'Dec', decisions: 1_240_000,new_clients: 1, new_agents: 7  },
    { month: 'Jan', decisions: 2_900_000,new_clients: 1, new_agents: 19 },
    { month: 'Feb', decisions: 4_800_000,new_clients: 2, new_agents: 7  },
    { month: 'Mar', decisions: 7_200_000,new_clients: 2, new_agents: 17 },
    { month: 'Apr', decisions: 7_720_441,new_clients: 3, new_agents: 5  },
  ],
}

function MilestoneBar({ label, current, target, fmt }: { label: string; current: number; target: number; fmt: (n: number) => string }) {
  const pct = Math.min((current / target) * 100, 100)
  const reached = pct >= 100
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          {reached
            ? <Trophy size={11} className="text-primary shrink-0" />
            : <div className="w-2.5 h-2.5 rounded-full border-2 border-muted-foreground/30 shrink-0" />}
          <span className={reached ? 'text-primary font-semibold' : 'text-muted-foreground'}>{label}</span>
        </div>
        <div className="flex items-center gap-2 tabular-nums">
          <span className="font-semibold">{fmt(current)}</span>
          <span className="text-muted-foreground/40">/</span>
          <span className="text-muted-foreground/60">{fmt(target)}</span>
          {reached && <span className="px-1.5 py-0 rounded-full text-[9px] font-bold bg-primary/15 text-primary border border-primary/30">HIT</span>}
        </div>
      </div>
      <div className="h-1.5 rounded-full bg-muted/40 overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${reached ? 'bg-primary' : 'bg-primary/50'}`}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
        />
      </div>
      <div className="flex justify-end">
        <span className={`text-[10px] ${reached ? 'text-primary font-semibold' : 'text-muted-foreground/50'}`}>
          {reached ? '✓ Milestone reached' : `${pct.toFixed(1)}% · ${fmt(target - current)} to go`}
        </span>
      </div>
    </div>
  )
}

function ScaleTab() {
  const d = SCALE_DATA
  const maxDecisions = Math.max(...d.velocity.map(v => v.decisions))

  return (
    <div className="space-y-5 fade-in">
      {/* Big impact counters */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Total Decisions Governed', value: `${(d.decisions_total / 1e6).toFixed(2)}M`, icon: Shield,     color: 'text-primary',     sub: 'all time, all clients'     },
          { label: 'Harmful Actions Blocked',  value: `${(d.blocks_total / 1000).toFixed(0)}k`,   icon: Zap,        color: 'text-emerald-400', sub: `avg ${((d.blocks_total/d.decisions_total)*100).toFixed(1)}% block rate` },
          { label: 'AI Agents Governed',       value: d.agents_ever,                               icon: Server,     color: 'text-blue-400',    sub: 'across all contracts'       },
          { label: 'Days Running',             value: d.days_running,                              icon: Clock,      color: 'text-muted-foreground', sub: 'since first client Nov 2025' },
        ].map(c => (
          <div key={c.label} className="glass-card p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{c.label}</span>
              <c.icon size={14} className={c.color} />
            </div>
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
            <p className="text-[11px] text-muted-foreground/60">{c.sub}</p>
          </div>
        ))}
      </div>

      {/* Milestone tracker */}
      <div className="glass-card p-5 space-y-5">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold flex items-center gap-2"><Trophy size={13} className="text-primary" /> Milestone Tracker</h3>
          <span className="text-xs text-muted-foreground/60">{d.milestones.filter(m => m.current >= m.target).length}/{d.milestones.length} reached</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {d.milestones.map(m => (
            <MilestoneBar key={m.label} {...m} />
          ))}
        </div>
      </div>

      {/* Decision volume growth */}
      <div className="glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold flex items-center gap-2"><TrendingUp size={13} className="text-emerald-400" /> Monthly Decision Volume</h3>
        <div className="flex items-end gap-2 h-28">
          {d.velocity.map(v => (
            <div key={v.month} className="flex-1 flex flex-col items-center gap-1">
              <span className="text-[9px] text-muted-foreground/60">{(v.decisions / 1e6).toFixed(1)}M</span>
              <div className="w-full rounded-t bg-primary/30 border-t border-primary/50" style={{ height: `${(v.decisions / maxDecisions) * 88}px` }} />
              <span className="text-[10px] text-muted-foreground/50">{v.month}</span>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-3 gap-3 pt-1 border-t border-border/40">
          {[
            { label: 'New Clients Added', values: d.velocity.map(v => v.new_clients) },
            { label: 'New Agents Added',  values: d.velocity.map(v => v.new_agents)  },
          ].map(row => (
            <div key={row.label} className="col-span-3 flex items-center gap-3">
              <span className="text-[11px] text-muted-foreground/60 w-32 shrink-0">{row.label}</span>
              <div className="flex flex-1 gap-2">
                {d.velocity.map((v, i) => (
                  <div key={v.month} className="flex-1 text-center">
                    <span className={`text-xs font-semibold ${row.values[i] > 0 ? 'text-foreground' : 'text-muted-foreground/30'}`}>
                      {row.values[i] > 0 ? `+${row.values[i]}` : '—'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Records */}
      <div className="glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold flex items-center gap-2"><Trophy size={13} className="text-primary" /> All-Time Records</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {d.records.map(r => (
            <div key={r.label} className="flex items-start gap-3 px-3 py-2.5 rounded-lg bg-muted/20 border border-border/40">
              <div className="w-1.5 h-1.5 rounded-full bg-primary/60 mt-1.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-[11px] text-muted-foreground/60">{r.label}</p>
                <p className="text-sm font-bold text-primary">{r.value}</p>
                <p className="text-[11px] text-muted-foreground/50 truncate">{r.who} · {r.date}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Additional totals */}
      <div className="glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold">All-Time Totals</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Total API Calls',     value: `${(d.api_calls_total / 1e6).toFixed(1)}M` },
            { label: 'Audit Log Entries',   value: d.audit_entries.toLocaleString()            },
            { label: 'Clients Onboarded',   value: d.clients_ever                              },
            { label: 'Avg Uptime',          value: '99.98%'                                    },
            { label: 'Policies Evaluated',  value: `${(d.decisions_total / 1e6).toFixed(2)}M` },
            { label: 'Total Agents Ever',   value: d.agents_ever                               },
            { label: 'Support Keys Issued', value: MOCK_SUPPORT_KEYS.length                    },
            { label: 'IP Rules Configured', value: Object.values(MOCK_IP_ALLOWLISTS).flat().length },
          ].map(s => (
            <div key={s.label} className="bg-muted/20 rounded-lg px-3 py-2.5 border border-border/40">
              <p className="text-[10px] text-muted-foreground mb-0.5">{s.label}</p>
              <p className="text-sm font-semibold">{s.value}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

const TABS = [
  { id: 'overview', label: 'Overview',   icon: Activity    },
  { id: 'scale',    label: 'Scale',      icon: Trophy      },
  { id: 'clients',  label: 'Clients',    icon: Building2   },
  { id: 'billing',  label: 'Billing',    icon: DollarSign  },
  { id: 'usage',    label: 'Usage',      icon: BarChart2   },
  { id: 'ip',       label: 'IP Rules',   icon: Globe       },
  { id: 'flags',    label: 'Features',   icon: Server      },
  { id: 'supkeys',  label: 'Sup. Keys',  icon: UserCheck   },
  { id: 'recovery', label: 'Recovery',   icon: KeyRound    },
  { id: 'audit',    label: 'Audit Log',  icon: ScrollText  },
] as const

type Tab = typeof TABS[number]['id']

export default function App() {
  const [tab, setTab] = useState<Tab>('overview')
  const [toastMsg, setToastMsg] = useState<string | null>(null)
  const toast = (msg: string) => setToastMsg(msg)

  return (
    <div className="min-h-screen">
      <div className="demo-banner px-4 py-2 flex items-center justify-center gap-2">
        <Key size={12} className="text-primary" />
        <span className="text-xs text-primary/80 font-medium">EDON Admin Dashboard — Interactive Demo · All data is simulated</span>
      </div>

      <header className="sticky top-0 z-40 border-b border-border/40 bg-background/90 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-4 flex items-center gap-4 h-14">
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-7 h-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
              <Shield size={14} className="text-primary" />
            </div>
            <span className="text-sm font-bold tracking-widest" style={{ color: 'hsl(38 95% 55%)' }}>EDON</span>
            <span className="text-xs text-muted-foreground px-1.5 py-0.5 rounded border border-border bg-muted/40">ADMIN</span>
          </div>

          <nav className="flex items-center gap-0.5 px-1 py-0.5 rounded-xl bg-muted/40 border border-border/40 overflow-x-auto">
            {TABS.map(t => {
              const Icon = t.icon
              const isActive = tab === t.id
              return (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={`relative nav-item flex items-center gap-1.5 px-2.5 h-8 text-xs font-medium rounded-lg shrink-0 ${isActive ? 'text-primary font-semibold' : ''}`}>
                  {isActive && (
                    <motion.div
                      layoutId="nav-pill"
                      className="absolute inset-0 rounded-lg"
                      style={{ background: 'hsl(38 95% 55% / 0.12)', border: '1px solid hsl(38 95% 55% / 0.25)' }}
                      transition={{ type: 'spring', stiffness: 400, damping: 32 }}
                    />
                  )}
                  <Icon size={12} className="relative z-10" />
                  <span className="hidden lg:inline relative z-10">{t.label}</span>
                </button>
              )
            })}
          </nav>

          <div className="flex items-center gap-3 ml-auto shrink-0">
            <div className="hidden sm:flex items-center gap-1.5 text-xs text-muted-foreground">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot" />
              <span>edon-gateway-prod.fly.dev</span>
            </div>
            <div className="flex items-center gap-1.5 px-2.5 h-7 rounded-full border border-primary/30 bg-primary/10 text-xs text-primary font-medium">
              <Clock size={11} /><span>Demo Mode</span>
            </div>
            <button onClick={() => toast('Demo: Disconnected')}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition">
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        <AnimatePresence mode="wait">
          <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
            {tab === 'overview' && <OverviewTab />}
            {tab === 'scale'    && <ScaleTab />}
            {tab === 'clients'  && <ClientsTab toast={toast} />}
            {tab === 'billing'  && <BillingTab />}
            {tab === 'usage'    && <UsageTab />}
            {tab === 'ip'       && <IPAllowlistTab toast={toast} />}
            {tab === 'flags'    && <FeatureFlagsTab toast={toast} />}
            {tab === 'supkeys'  && <SupportKeysTab toast={toast} />}
            {tab === 'recovery' && <RecoveryTab toast={toast} />}
            {tab === 'audit'    && <AuditLogTab />}
          </motion.div>
        </AnimatePresence>
      </main>

      <AnimatePresence>
        {toastMsg && <Toast msg={toastMsg} onClose={() => setToastMsg(null)} />}
      </AnimatePresence>
    </div>
  )
}
