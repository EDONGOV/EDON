import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  GitBranch, GitCommit, CheckCircle2, XCircle, Clock,
  AlertTriangle, Shield, Zap, RefreshCw, Copy, Check,
  ChevronDown, ChevronRight, Terminal, Play, ExternalLink,
  Github, Loader2, BarChart3, TrendingUp, Package,
} from "lucide-react";
import { edonApi, type CicdScan, type CicdFinding } from "@/lib/api";
import { toast } from "sonner";

// ── Severity helpers ───────────────────────────────────────────────────────────

const SEV_COLOR: Record<string, string> = {
  critical: "text-red-400 bg-red-950/50 border-red-800/50",
  high:     "text-orange-400 bg-orange-950/50 border-orange-800/50",
  medium:   "text-yellow-400 bg-yellow-950/50 border-yellow-800/50",
  low:      "text-slate-400 bg-slate-800/50 border-slate-700/50",
};

const SEV_DOT: Record<string, string> = {
  critical: "bg-red-500",
  high:     "bg-orange-500",
  medium:   "bg-yellow-500",
  low:      "bg-slate-500",
};

function SeverityBadge({ sev }: { sev: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${SEV_COLOR[sev] ?? SEV_COLOR.low}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${SEV_DOT[sev] ?? SEV_DOT.low}`} />
      {sev}
    </span>
  );
}

// ── Gate badge ────────────────────────────────────────────────────────────────

function GateBadge({ scan }: { scan: CicdScan }) {
  if (scan.status === "scanning" || scan.status === "pending") {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-blue-950/50 text-blue-300 border border-blue-800/50">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        Scanning…
      </span>
    );
  }
  if (scan.status === "error") {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-slate-800 text-slate-300 border border-slate-700">
        <AlertTriangle className="w-3.5 h-3.5" />
        Error
      </span>
    );
  }
  if (scan.gate_passed) {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-emerald-950/50 text-emerald-400 border border-emerald-800/50">
        <CheckCircle2 className="w-3.5 h-3.5" />
        Gate Passed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-red-950/50 text-red-400 border border-red-800/50">
      <XCircle className="w-3.5 h-3.5" />
      Gate Failed
    </span>
  );
}

// ── Scan row ──────────────────────────────────────────────────────────────────

function ScanRow({ scan, onClick, active }: { scan: CicdScan; onClick: () => void; active: boolean }) {
  const sha = scan.commit_sha?.slice(0, 7) ?? "—";
  const ago = scan.created_at
    ? (() => {
        const diff = Date.now() - new Date(scan.created_at).getTime();
        const m = Math.floor(diff / 60000);
        if (m < 1) return "just now";
        if (m < 60) return `${m}m ago`;
        const h = Math.floor(m / 60);
        if (h < 24) return `${h}h ago`;
        return `${Math.floor(h / 24)}d ago`;
      })()
    : "";

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-4 py-3 border-b border-slate-800 hover:bg-slate-800/40 transition-colors ${
        active ? "bg-slate-800/60 border-l-2 border-l-emerald-500" : ""
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {scan.gate_passed
            ? <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            : scan.status === "error"
            ? <AlertTriangle className="w-4 h-4 text-slate-400 flex-shrink-0" />
            : <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
          }
          <div className="min-w-0">
            <div className="text-sm font-medium text-slate-200 truncate">
              {scan.repo ?? "manual scan"}
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              {scan.branch && (
                <span className="flex items-center gap-1 text-[11px] text-slate-500">
                  <GitBranch className="w-3 h-3" />{scan.branch}
                </span>
              )}
              {scan.commit_sha && (
                <span className="flex items-center gap-1 text-[11px] text-slate-500 font-mono">
                  <GitCommit className="w-3 h-3" />{sha}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <GateBadge scan={scan} />
          <span className="text-[11px] text-slate-500">{ago}</span>
        </div>
      </div>
      {scan.total_findings > 0 && (
        <div className="flex gap-2 mt-2">
          {scan.critical_findings > 0 && (
            <span className="text-[11px] text-red-400">{scan.critical_findings} critical</span>
          )}
          {scan.high_findings > 0 && (
            <span className="text-[11px] text-orange-400">{scan.high_findings} high</span>
          )}
          {scan.medium_findings > 0 && (
            <span className="text-[11px] text-yellow-400">{scan.medium_findings} medium</span>
          )}
        </div>
      )}
    </button>
  );
}

// ── Finding detail row ────────────────────────────────────────────────────────

function FindingRow({ f }: { f: CicdFinding }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`border rounded-lg overflow-hidden ${f.mitigated ? "border-slate-800 opacity-60" : "border-slate-700"}`}>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-slate-800/50 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          {open ? <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />}
          <SeverityBadge sev={f.severity} />
          <span className="text-sm font-mono text-slate-300 truncate">{f.vulnerability_class}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-xs text-slate-500 tabular-nums">{f.severity_score.toFixed(2)}</span>
          {f.mitigated && (
            <span className="text-[11px] text-emerald-500 bg-emerald-950/50 border border-emerald-800/50 px-2 py-0.5 rounded-full">mitigated</span>
          )}
        </div>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-1 bg-slate-900/50 border-t border-slate-800">
              <div className="text-xs text-slate-400 font-mono">
                <span className="text-slate-500">path:</span>{" "}
                {f.path_summary || "—"}
              </div>
              <div className="mt-1 text-xs text-slate-400">
                <span className="text-slate-500">id:</span>{" "}
                <span className="font-mono">{f.failure_state_id}</span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Scan detail panel ─────────────────────────────────────────────────────────

function ScanDetail({ scan }: { scan: CicdScan }) {
  const [copied, setCopied] = useState(false);

  const copyId = () => {
    navigator.clipboard.writeText(scan.scan_id).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const durationStr = scan.scan_duration_ms
    ? scan.scan_duration_ms < 1000
      ? `${scan.scan_duration_ms}ms`
      : `${(scan.scan_duration_ms / 1000).toFixed(1)}s`
    : "—";

  return (
    <div className="flex flex-col gap-5 p-5">
      {/* Gate verdict */}
      <div className={`rounded-xl border p-4 ${scan.gate_passed ? "bg-emerald-950/20 border-emerald-800/40" : scan.status === "error" ? "bg-slate-800/40 border-slate-700" : "bg-red-950/20 border-red-800/40"}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            {scan.gate_passed
              ? <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              : scan.status === "error"
              ? <AlertTriangle className="w-5 h-5 text-slate-400" />
              : <XCircle className="w-5 h-5 text-red-400" />
            }
            <span className={`font-semibold ${scan.gate_passed ? "text-emerald-400" : scan.status === "error" ? "text-slate-300" : "text-red-400"}`}>
              {scan.gate_passed ? "Gate Passed — Safe to deploy" : scan.status === "error" ? "Scan Error" : "Gate Failed — Block deployment"}
            </span>
          </div>
          <span className="text-xs text-slate-500 tabular-nums flex-shrink-0">{durationStr}</span>
        </div>
        {scan.gate_reason && (
          <p className="mt-2 text-sm text-slate-400">{scan.gate_reason}</p>
        )}
      </div>

      {/* Stat row */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Critical", val: scan.critical_findings, cls: "text-red-400" },
          { label: "High",     val: scan.high_findings,     cls: "text-orange-400" },
          { label: "Medium",   val: scan.medium_findings,   cls: "text-yellow-400" },
          { label: "Mitigated", val: scan.mitigated_count,  cls: "text-emerald-400" },
        ].map(({ label, val, cls }) => (
          <div key={label} className="bg-slate-800/50 rounded-lg border border-slate-700 p-3 text-center">
            <div className={`text-2xl font-bold tabular-nums ${cls}`}>{val}</div>
            <div className="text-[11px] text-slate-500 mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      {/* Meta */}
      <div className="grid grid-cols-2 gap-2 text-sm">
        {[
          { k: "Scan ID",       v: scan.scan_id.slice(0, 16) + "…", mono: true, action: copyId },
          { k: "Triggered by",  v: scan.triggered_by },
          { k: "Repo",          v: scan.repo ?? "—", mono: true },
          { k: "Branch",        v: scan.branch ?? "—", mono: true },
          { k: "Commit",        v: scan.commit_sha?.slice(0, 12) ?? "—", mono: true },
          { k: "Environment",   v: scan.environment ?? "—" },
          { k: "GitHub status", v: scan.github_status_posted ? "Posted" : "Not posted" },
          { k: "New findings",  v: String(scan.new_since_last) },
        ].map(({ k, v, mono, action }) => (
          <div key={k} className="bg-slate-800/30 rounded-lg border border-slate-800 px-3 py-2">
            <div className="text-[11px] text-slate-500 mb-0.5">{k}</div>
            <div className={`flex items-center gap-1 text-slate-300 ${mono ? "font-mono text-xs" : "text-sm"}`}>
              <span className="truncate">{v}</span>
              {action && (
                <button onClick={action} className="ml-1 text-slate-500 hover:text-slate-300">
                  {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Findings */}
      {scan.findings_detail.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
            Top Findings
          </div>
          <div className="flex flex-col gap-2">
            {scan.findings_detail.map((f, i) => (
              <FindingRow key={i} f={f} />
            ))}
          </div>
        </div>
      )}

      {/* Errors */}
      {scan.errors.length > 0 && (
        <div className="bg-red-950/20 border border-red-900/30 rounded-lg p-3">
          <div className="text-xs font-semibold text-red-400 mb-1">Scan Errors</div>
          {scan.errors.map((e, i) => (
            <div key={i} className="text-xs font-mono text-red-300">{e}</div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Trigger form ──────────────────────────────────────────────────────────────

function TriggerForm({ onScan }: { onScan: (scan: CicdScan) => void }) {
  const [repo, setRepo] = useState("");
  const [sha, setSha] = useState("");
  const [branch, setBranch] = useState("");
  const [env, setEnv] = useState("production");
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const scan = await edonApi.triggerCicdScan({
        repo: repo || undefined,
        commit_sha: sha || undefined,
        branch: branch || undefined,
        environment: env || undefined,
      });
      onScan(scan);
      toast.success("Scan complete", { description: scan.gate_reason });
    } catch (e) {
      toast.error("Scan failed", { description: String(e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-5 border-b border-slate-800">
      <div className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
        <Play className="w-4 h-4 text-emerald-400" />
        Trigger Manual Scan
      </div>
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div>
          <label className="text-[11px] text-slate-500 block mb-1">Repo (owner/repo)</label>
          <input
            value={repo}
            onChange={e => setRepo(e.target.value)}
            placeholder="e.g. acme/api-service"
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-emerald-600"
          />
        </div>
        <div>
          <label className="text-[11px] text-slate-500 block mb-1">Branch</label>
          <input
            value={branch}
            onChange={e => setBranch(e.target.value)}
            placeholder="main"
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-emerald-600"
          />
        </div>
        <div>
          <label className="text-[11px] text-slate-500 block mb-1">Commit SHA (optional)</label>
          <input
            value={sha}
            onChange={e => setSha(e.target.value)}
            placeholder="abc1234…"
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono placeholder:text-slate-600 focus:outline-none focus:border-emerald-600"
          />
        </div>
        <div>
          <label className="text-[11px] text-slate-500 block mb-1">Environment</label>
          <select
            value={env}
            onChange={e => setEnv(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-emerald-600"
          >
            {["production", "staging", "preview", "development"].map(o => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        </div>
      </div>
      <button
        onClick={run}
        disabled={loading}
        className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white font-semibold text-sm py-2 rounded-lg transition-colors flex items-center justify-center gap-2"
      >
        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
        {loading ? "Scanning…" : "Run Security Gate"}
      </button>
    </div>
  );
}

// ── GitHub Actions snippet ────────────────────────────────────────────────────

const YAML_SNIPPET = `name: EDON Security Gate

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main]

jobs:
  edon-gate:
    runs-on: ubuntu-latest
    steps:
      - name: EDON Security Scan
        id: edon
        run: |
          RESULT=$(curl -sf -X POST \\
            -H "Authorization: Bearer \${{ secrets.EDON_API_KEY }}" \\
            -H "Content-Type: application/json" \\
            -d '{"repo":"\${{ github.repository }}","commit_sha":"\${{ github.sha }}","branch":"\${{ github.ref_name }}","environment":"production"}' \\
            https://gateway.edoncore.com/v1/cicd/scan)
          echo "\$RESULT"
          GATE=$(echo "\$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['gate_passed'])")
          if [ "\$GATE" != "True" ]; then
            echo "::error::EDON gate failed — unmitigated critical findings detected"
            exit 1
          fi`;

function SnippetPanel() {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(YAML_SNIPPET).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.success("Copied to clipboard");
    });
  };

  return (
    <div className="p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-semibold text-slate-200 flex items-center gap-2">
          <Github className="w-4 h-4" />
          GitHub Actions Integration
        </div>
        <button
          onClick={copy}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? "Copied!" : "Copy YAML"}
        </button>
      </div>
      <div className="relative rounded-xl overflow-hidden border border-slate-700 bg-slate-950">
        <div className="flex items-center gap-1.5 px-4 py-2 bg-slate-900 border-b border-slate-800">
          <Terminal className="w-3.5 h-3.5 text-slate-500" />
          <span className="text-xs text-slate-500">.github/workflows/edon-gate.yml</span>
        </div>
        <pre className="text-xs text-slate-300 p-4 overflow-x-auto leading-relaxed">
          <code>{YAML_SNIPPET}</code>
        </pre>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        {[
          {
            icon: <Zap className="w-4 h-4 text-emerald-400" />,
            title: "Webhook (push events)",
            desc: "Set POST /v1/cicd/event as your GitHub repo webhook — all pushes to gate branches auto-scan.",
          },
          {
            icon: <Shield className="w-4 h-4 text-blue-400" />,
            title: "GitHub Commit Status",
            desc: "Set EDON_GITHUB_TOKEN env var and gate results appear as native commit status checks on PRs.",
          },
          {
            icon: <BarChart3 className="w-4 h-4 text-violet-400" />,
            title: "Gate policy",
            desc: "Configure EDON_CICD_GATE_ON_CRITICAL, EDON_CICD_MAX_CRITICAL, EDON_CICD_GATE_ON_HIGH.",
          },
          {
            icon: <TrendingUp className="w-4 h-4 text-orange-400" />,
            title: "History endpoint",
            desc: "GET /v1/cicd/history returns all scans for your tenant — pipe into dashboards or alerts.",
          },
        ].map(({ icon, title, desc }) => (
          <div key={title} className="bg-slate-800/40 rounded-lg border border-slate-800 p-3">
            <div className="flex items-center gap-2 mb-1">
              {icon}
              <span className="text-xs font-semibold text-slate-300">{title}</span>
            </div>
            <p className="text-[11px] text-slate-500 leading-relaxed">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type Tab = "history" | "trigger" | "setup";

export default function CiCd() {
  const [tab, setTab] = useState<Tab>("history");
  const [scans, setScans] = useState<CicdScan[]>([]);
  const [selected, setSelected] = useState<CicdScan | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadHistory = async (quiet = false) => {
    if (!quiet) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await edonApi.getCicdHistory({ limit: 50 });
      setScans(res.scans);
      // Keep selected in sync
      if (selected) {
        const updated = res.scans.find(s => s.scan_id === selected.scan_id);
        if (updated) setSelected(updated);
      }
    } catch {
      // Silently fall back to empty — backend might not have any scans yet
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadHistory();
    // Poll every 15s for live updates
    pollRef.current = setInterval(() => loadHistory(true), 15_000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const handleNewScan = (scan: CicdScan) => {
    setScans(prev => [scan, ...prev.filter(s => s.scan_id !== scan.scan_id)]);
    setSelected(scan);
    setTab("history");
  };

  // Summary stats
  const passed = scans.filter(s => s.gate_passed).length;
  const failed = scans.filter(s => !s.gate_passed && s.status !== "error").length;
  const passRate = scans.length ? Math.round((passed / scans.length) * 100) : null;

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-200 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-emerald-950/50 border border-emerald-800/50">
            <GitBranch className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-100">CI/CD Security Gate</h1>
            <p className="text-xs text-slate-500">Automated security gate — block deploys with unmitigated critical findings</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {passRate !== null && (
            <div className="text-right">
              <div className={`text-xl font-bold tabular-nums ${passRate >= 80 ? "text-emerald-400" : passRate >= 50 ? "text-yellow-400" : "text-red-400"}`}>
                {passRate}%
              </div>
              <div className="text-[11px] text-slate-500">pass rate</div>
            </div>
          )}
          <button
            onClick={() => loadHistory(true)}
            disabled={refreshing}
            className="p-2 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Stat bar */}
      {scans.length > 0 && (
        <div className="flex gap-4 px-6 py-3 bg-slate-900/50 border-b border-slate-800 flex-shrink-0">
          {[
            { label: "Total scans", val: scans.length, cls: "text-slate-200" },
            { label: "Passed", val: passed, cls: "text-emerald-400" },
            { label: "Failed", val: failed, cls: "text-red-400" },
            {
              label: "Avg duration",
              val: (() => {
                const ms = scans.filter(s => s.scan_duration_ms).reduce((a, s) => a + s.scan_duration_ms, 0) / scans.filter(s => s.scan_duration_ms).length;
                return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;
              })(),
              cls: "text-slate-300",
            },
          ].map(({ label, val, cls }) => (
            <div key={label} className="flex items-center gap-2">
              <span className={`text-sm font-bold tabular-nums ${cls}`}>{val}</span>
              <span className="text-xs text-slate-500">{label}</span>
              <span className="text-slate-700 ml-2">|</span>
            </div>
          ))}
        </div>
      )}

      {/* Tab bar */}
      <div className="flex gap-1 px-6 py-2 border-b border-slate-800 flex-shrink-0">
        {(["history", "trigger", "setup"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors capitalize ${
              tab === t
                ? "bg-slate-700 text-slate-100"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {t === "history" ? "Scan History" : t === "trigger" ? "Manual Scan" : "Integration Setup"}
          </button>
        ))}
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          {tab === "history" && (
            <motion.div
              key="history"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-1 overflow-hidden"
            >
              {/* Scan list */}
              <div className="w-80 flex-shrink-0 border-r border-slate-800 overflow-y-auto">
                {loading ? (
                  <div className="flex items-center justify-center py-16 text-slate-500">
                    <Loader2 className="w-5 h-5 animate-spin mr-2" />
                    Loading scans…
                  </div>
                ) : scans.length === 0 ? (
                  <div className="px-6 py-12 text-center">
                    <Package className="w-8 h-8 text-slate-600 mx-auto mb-3" />
                    <p className="text-sm text-slate-500">No scans yet.</p>
                    <p className="text-xs text-slate-600 mt-1">
                      Trigger a manual scan or set up the GitHub Actions integration.
                    </p>
                    <button
                      onClick={() => setTab("trigger")}
                      className="mt-4 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                      Run first scan
                    </button>
                  </div>
                ) : (
                  scans.map(scan => (
                    <ScanRow
                      key={scan.scan_id}
                      scan={scan}
                      onClick={() => setSelected(scan)}
                      active={selected?.scan_id === scan.scan_id}
                    />
                  ))
                )}
              </div>

              {/* Detail pane */}
              <div className="flex-1 overflow-y-auto">
                {selected ? (
                  <ScanDetail scan={selected} />
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
                    <Shield className="w-10 h-10" />
                    <p className="text-sm">Select a scan to see details</p>
                  </div>
                )}
              </div>
            </motion.div>
          )}

          {tab === "trigger" && (
            <motion.div
              key="trigger"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 overflow-y-auto max-w-2xl mx-auto w-full"
            >
              <TriggerForm onScan={handleNewScan} />
              <div className="p-5 text-sm text-slate-500">
                <p>
                  A manual scan triggers the full EDON Impact cycle (Engines A→D) scoped to your tenant,
                  evaluates the gate policy, and returns a structured result. If a GitHub token is set
                  in your gateway config (<code className="font-mono text-xs bg-slate-800 px-1 py-0.5 rounded">EDON_GITHUB_TOKEN</code>),
                  it also posts a commit status check.
                </p>
              </div>
            </motion.div>
          )}

          {tab === "setup" && (
            <motion.div
              key="setup"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 overflow-y-auto"
            >
              <SnippetPanel />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
