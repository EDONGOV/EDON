import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Copy, Check, RefreshCw, Plus, Trash2, Shield, Link, AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'
import AccountLayout, { PageHeader } from './AccountLayout'
import {
  gwListApiKeys, gwRotateApiKey,
  gwGetIpAllowlist, gwAddIpAllowlist, gwRemoveIpAllowlist,
  getBase, getToken,
} from '../../lib/gateway'

// ── Helpers ──────────────────────────────────────────────────────────────────

function useClipboard(ms = 2000) {
  const [copied, setCopied] = useState(false)
  const copy = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), ms)
    })
  }
  return { copied, copy }
}

// ── API Keys section ──────────────────────────────────────────────────────────

function ApiKeysSection() {
  const qc = useQueryClient()
  const keys = useQuery({ queryKey: ['api-keys'], queryFn: gwListApiKeys })
  const [newKey, setNewKey] = useState<string | null>(null)
  const [overlapHours, setOverlapHours] = useState(24)
  const { copied, copy } = useClipboard()

  const rotate = useMutation({
    mutationFn: (keyId: string) => gwRotateApiKey(keyId, overlapHours),
    onSuccess: (data) => {
      setNewKey(data.new_key)
      qc.invalidateQueries({ queryKey: ['api-keys'] })
      toast.success('Key rotated — old key valid for ' + data.overlap_hours + 'h')
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const keyList = keys.data?.keys ?? []

  return (
    <section className="mb-10">
      <h2 className="text-sm font-semibold text-foreground mb-1">API Keys</h2>
      <p className="text-xs text-muted-foreground mb-4">
        Rotate a key to issue a new one. The old key stays valid for the overlap window so you can
        deploy without downtime.
      </p>

      {keys.isLoading && <div className="text-xs text-muted-foreground">Loading…</div>}

      {keyList.length === 0 && !keys.isLoading && (
        <p className="text-xs text-muted-foreground">No API keys found.</p>
      )}

      <div className="space-y-2">
        {keyList.map((k) => (
          <div key={k.id} className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{k.name ?? 'Unnamed key'}</p>
              <p className="text-[10px] font-mono text-muted-foreground/60 truncate">{k.id}</p>
            </div>
            <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${
              k.status === 'active'
                ? 'bg-status-active/10 border-status-active/20 text-status-active'
                : k.status === 'rotating'
                ? 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400'
                : 'bg-muted/20 border-border text-muted-foreground'
            }`}>
              {k.status}
            </span>
            <span className="text-[10px] text-muted-foreground/50 uppercase">{k.role}</span>

            <div className="flex items-center gap-1.5">
              <select
                value={overlapHours}
                onChange={(e) => setOverlapHours(Number(e.target.value))}
                className="text-xs bg-background border border-border rounded-lg px-2 py-1 text-muted-foreground"
              >
                <option value={1}>1h overlap</option>
                <option value={4}>4h overlap</option>
                <option value={24}>24h overlap</option>
                <option value={72}>3d overlap</option>
              </select>
              <button
                onClick={() => rotate.mutate(k.id)}
                disabled={rotate.isPending}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border bg-background hover:bg-white/5 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${rotate.isPending ? 'animate-spin' : ''}`} />
                Rotate
              </button>
            </div>
          </div>
        ))}
      </div>

      {newKey && (
        <div className="mt-4 rounded-xl border border-status-active/30 bg-status-active/5 p-4">
          <p className="text-xs font-medium text-status-active mb-2 flex items-center gap-1.5">
            <Check className="h-3.5 w-3.5" />
            New key — copy it now, it won't be shown again
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs font-mono bg-black/30 rounded-lg px-3 py-2 text-foreground break-all">
              {newKey}
            </code>
            <button
              onClick={() => copy(newKey)}
              className="shrink-0 p-2 rounded-lg border border-border hover:bg-white/5 transition-colors"
            >
              {copied ? <Check className="h-4 w-4 text-status-active" /> : <Copy className="h-4 w-4 text-muted-foreground" />}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

// ── Console link section ──────────────────────────────────────────────────────

function ConsoleLinkSection() {
  const { copied, copy } = useClipboard()
  const token = getToken()
  const base = getBase()
  const consoleUrl = `https://console.edoncore.com/#token=${token}&base=${encodeURIComponent(base)}`

  return (
    <section className="mb-10">
      <h2 className="text-sm font-semibold text-foreground mb-1">Console Access Link</h2>
      <p className="text-xs text-muted-foreground mb-4">
        Share this link with your team. The token is in the URL hash — it's never sent to servers or
        stored in access logs.
      </p>

      <div className="flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-3">
        <Link className="h-4 w-4 text-muted-foreground shrink-0" />
        <code className="flex-1 text-xs font-mono text-muted-foreground truncate">{consoleUrl}</code>
        <button
          onClick={() => copy(consoleUrl)}
          className="shrink-0 p-2 rounded-lg border border-border hover:bg-white/5 transition-colors"
        >
          {copied ? <Check className="h-4 w-4 text-status-active" /> : <Copy className="h-4 w-4 text-muted-foreground" />}
        </button>
      </div>
      <p className="text-[10px] text-muted-foreground/50 mt-2 flex items-center gap-1">
        <Shield className="h-3 w-3" />
        Hash fragment (#token=…) — never transmitted to or logged by servers
      </p>
    </section>
  )
}

// ── IP allowlist section ──────────────────────────────────────────────────────

function IpAllowlistSection() {
  const qc = useQueryClient()
  const [input, setInput] = useState('')
  const allowlist = useQuery({ queryKey: ['ip-allowlist'], queryFn: gwGetIpAllowlist })

  const add = useMutation({
    mutationFn: (cidr: string) => gwAddIpAllowlist(cidr),
    onSuccess: () => {
      setInput('')
      qc.invalidateQueries({ queryKey: ['ip-allowlist'] })
      toast.success('CIDR added')
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const remove = useMutation({
    mutationFn: (cidr: string) => gwRemoveIpAllowlist(cidr),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ip-allowlist'] })
      toast.success('CIDR removed')
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const cidrs = allowlist.data?.cidrs ?? []
  const enabled = cidrs.length > 0

  return (
    <section className="mb-10">
      <h2 className="text-sm font-semibold text-foreground mb-1 flex items-center gap-2">
        IP Allowlist
        {enabled && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-status-active/10 border border-status-active/20 text-status-active font-medium">
            Active
          </span>
        )}
      </h2>
      <p className="text-xs text-muted-foreground mb-4">
        Restrict API access to specific IP ranges. Once any entry is added, requests from all other
        IPs are rejected.{' '}
        <strong className="text-foreground/70">Add your own IP first before enabling.</strong>
      </p>

      {enabled && (
        <div className="flex items-start gap-2 rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-3 mb-4 text-xs text-yellow-400">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <span>Allowlist is active — requests from IPs not in this list will be blocked.</span>
        </div>
      )}

      {allowlist.isLoading && <div className="text-xs text-muted-foreground">Loading…</div>}

      <div className="space-y-2 mb-4">
        {cidrs.map((cidr) => (
          <div key={cidr} className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-2.5">
            <Shield className="h-3.5 w-3.5 text-status-active shrink-0" />
            <code className="flex-1 text-xs font-mono text-foreground">{cidr}</code>
            <button
              onClick={() => remove.mutate(cidr)}
              disabled={remove.isPending}
              className="p-1.5 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && input.trim() && add.mutate(input.trim())}
          placeholder="203.0.113.0/24 or 1.2.3.4"
          className="flex-1 text-sm bg-background border border-border rounded-xl px-3 py-2 placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary/40"
        />
        <button
          onClick={() => input.trim() && add.mutate(input.trim())}
          disabled={!input.trim() || add.isPending}
          className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          <Plus className="h-4 w-4" />
          Add
        </button>
      </div>
    </section>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Settings() {
  return (
    <AccountLayout>
      <div className="p-6 max-w-2xl">
        <PageHeader
          title="Settings"
          description="API key rotation, access links, and IP restrictions."
        />
        <ApiKeysSection />
        <ConsoleLinkSection />
        <IpAllowlistSection />
      </div>
    </AccountLayout>
  )
}
