import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { ShieldCheck, Timer, ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Link } from 'react-router-dom';
import { edonApi } from '@/lib/api';

/** Display config for each governance mode style */
const POLICY_MODE_DISPLAY: Record<string, { label: string; description: string; color: string }> = {
  safe: {
    label: 'Safe Mode',
    description: 'High-oversight mode — every action is reviewed before execution',
    color: 'from-emerald-500 to-emerald-700',
  },
  business: {
    label: 'Business Mode',
    description: 'Balanced autonomy — low-risk actions proceed, sensitive ones are gated',
    color: 'from-sky-400 to-sky-600',
  },
  autonomy: {
    label: 'Autonomy Mode',
    description: 'Full speed — agent acts freely within your defined policy boundaries',
    color: 'from-amber-500 to-orange-600',
  },
  research: {
    label: 'Research Mode',
    description: 'Research-focused — web and data access with controlled risk',
    color: 'from-cyan-500 to-cyan-700',
  },
  default: {
    label: 'Governance',
    description: 'Policy-driven execution — mode set from Policies page',
    color: 'from-slate-500 to-slate-700',
  },
};

/** Map gateway preset_name to display key (must match Policies page: personal_safe=Safe, work_safe=Business, ops_admin=Autonomy) */
function presetToDisplayKey(presetName: string | null | undefined): keyof typeof POLICY_MODE_DISPLAY {
  if (!presetName) return 'default';
  const p = presetName.toLowerCase().replace(/-/g, '_');
  if (p.includes('personal') || p.includes('casual') || p === 'personal_safe' || p === 'casual_user') return 'safe';
  if (p === 'ops_admin' || p.includes('autonomy') || p.includes('founder') || p.includes('helpdesk') || p === 'clawdbot_safe') return 'autonomy';
  if (p.includes('work') || p.includes('ops_commander') || p === 'work_safe') return 'business';
  if (p.includes('research') || p.includes('market')) return 'research';
  return 'default';
}

/** Human-readable label for preset name (e.g. work_safe -> Work Safe) */
function formatPresetLabel(presetName: string): string {
  return presetName
    .split(/[_\s]+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}

export function PolicyModeCard() {
  const [presetName, setPresetName] = useState<string | null>(null);
  const [appliedAt, setAppliedAt] = useState<string | null>(null);
  const [policyVersion, setPolicyVersion] = useState<string>('—');
  const [loading, setLoading] = useState(true);

  const fetchActivePreset = useCallback(async () => {
    try {
      const health = await edonApi.getHealth();
      const preset = health?.governor?.active_preset;
      const version = health?.governor?.policy_version;
      if (preset?.preset_name) {
        setPresetName(preset.preset_name);
        setAppliedAt(preset.applied_at || null);
      } else {
        setPresetName(null);
        setAppliedAt(null);
      }
      if (version) setPolicyVersion(version);
    } catch {
      setPresetName(null);
      setAppliedAt(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchActivePreset();
    const interval = setInterval(fetchActivePreset, 30_000);
    const onVisible = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') fetchActivePreset();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [fetchActivePreset]);

  const displayKey = presetToDisplayKey(presetName);
  const mode = POLICY_MODE_DISPLAY[displayKey] ?? POLICY_MODE_DISPLAY.default;
  const lastUpdated = appliedAt ? new Date(appliedAt) : null;

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.4 }}
      className="glass-card p-6"
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold">Governance Mode</h3>
        <Link to="/policies" className="text-primary text-sm flex items-center gap-1 hover:underline">
          Manage <ChevronRight className="w-4 h-4" />
        </Link>
      </div>

      {loading ? (
        <div className="p-4 rounded-xl bg-muted/50 mb-4 animate-pulse">
          <div className="h-6 w-32 rounded bg-muted mb-2" />
          <div className="h-4 w-full rounded bg-muted" />
        </div>
      ) : (
        <div className={`p-4 rounded-xl bg-gradient-to-br ${mode.color} mb-4`}>
          <div className="flex items-center gap-3 mb-2">
            <ShieldCheck className="w-6 h-6 text-white" />
            <span className="text-lg font-semibold text-white">
              {displayKey !== 'default' ? mode.label : (presetName ? formatPresetLabel(presetName) : mode.label)}
            </span>
          </div>
          <p className="text-sm text-white/80">{mode.description}</p>
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Policy Version</span>
          <Badge variant="outline" className="font-mono">{policyVersion}</Badge>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground flex items-center gap-1">
            <Timer className="w-3 h-3" /> Last Updated
          </span>
          <span className="text-xs">
            {lastUpdated
              ? `${lastUpdated.toLocaleDateString()} ${lastUpdated.toLocaleTimeString()}`
              : '—'}
          </span>
        </div>
      </div>
    </motion.div>
  );
}
