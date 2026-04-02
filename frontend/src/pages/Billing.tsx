import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { edonApi } from "@/lib/api";
import {
  Zap,
  Activity,
  Users,
  Key,
  ExternalLink,
  CheckCircle2,
  TrendingUp,
} from "lucide-react";

type PlanTier = "starter" | "growth" | "business" | "enterprise";

interface PlanConfig {
  label: string;
  decisions: number | null;
  apiKeys: number | null;
  members: number | null;
  policyPacks: number | null;
  channels: number | null;
  auditDays: number | null;
  monthlyPrice: number;
  nextTier: PlanTier | null;
}

const PLANS: Record<PlanTier, PlanConfig> = {
  starter: {
    label: "Starter",
    decisions: 10000,
    apiKeys: 3,
    members: 3,
    policyPacks: 3,
    channels: 2,
    auditDays: 30,
    monthlyPrice: 49,
    nextTier: "growth",
  },
  growth: {
    label: "Growth",
    decisions: 100000,
    apiKeys: 10,
    members: 10,
    policyPacks: 6,
    channels: 5,
    auditDays: 90,
    monthlyPrice: 299,
    nextTier: "business",
  },
  business: {
    label: "Business",
    decisions: 1000000,
    apiKeys: 25,
    members: 50,
    policyPacks: null,
    channels: null,
    auditDays: 365,
    monthlyPrice: 999,
    nextTier: "enterprise",
  },
  enterprise: {
    label: "Enterprise",
    decisions: null,
    apiKeys: null,
    members: null,
    policyPacks: null,
    channels: null,
    auditDays: null,
    monthlyPrice: 0,
    nextTier: null,
  },
};

const NEXT_TIER_HIGHLIGHTS: Record<PlanTier, string[]> = {
  growth: ["10x more decisions/month", "Up to 10 team members", "6 policy packs", "90-day audit retention"],
  business: ["1M decisions/month", "50 team members", "All policy packs", "1 year audit retention"],
  enterprise: ["Unlimited everything", "Dedicated support", "Custom SLA", "On-premise option"],
  starter: [],
};

function fmtLimit(val: number | null): string {
  if (val === null) return "Unlimited";
  if (val >= 1000000) return `${val / 1000000}M`;
  if (val >= 1000) return `${(val / 1000).toFixed(0)}k`;
  return String(val);
}

function usagePct(used: number, limit: number | null): number {
  if (!limit) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

interface MockUsage {
  decisions: number;
  apiCalls: number;
  agentsConnected: number;
  teamMembers: number;
}

function getMockUsage(plan: PlanTier): MockUsage {
  const multipliers: Record<PlanTier, number> = {
    starter: 0.4,
    growth: 0.25,
    business: 0.1,
    enterprise: 0,
  };
  const m = multipliers[plan];
  return {
    decisions: Math.round((PLANS[plan].decisions ?? 1000000) * m),
    apiCalls: Math.round((PLANS[plan].decisions ?? 1000000) * m * 1.3),
    agentsConnected: Math.min(2, PLANS[plan].members ?? 50),
    teamMembers: Math.min(1, PLANS[plan].members ?? 50),
  };
}

function getMockInvoices(plan: PlanTier) {
  const price = PLANS[plan].monthlyPrice;
  if (price === 0) return [];
  const months = ["Feb 2026", "Jan 2026", "Dec 2025"];
  return months.map((m, i) => ({
    id: `inv_${1000 + i}`,
    period: m,
    amount: price,
    status: "Paid",
    url: "#",
  }));
}

export default function Billing() {
  const [loading, setLoading] = useState(true);
  const [planKey, setPlanKey] = useState<PlanTier>("starter");
  const [usage, setUsage] = useState<MockUsage | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const billing = await edonApi.getBillingStatus();
        const rawPlan = (billing?.plan ?? "").toLowerCase() as PlanTier;
        const tier: PlanTier = PLANS[rawPlan] ? rawPlan : "starter";
        setPlanKey(tier);
        const decisionsUsed = billing?.usage?.today ?? getMockUsage(tier).decisions;
        setUsage({
          decisions: decisionsUsed,
          apiCalls: Math.round(decisionsUsed * 1.3),
          agentsConnected: 2,
          teamMembers: 1,
        });
      } catch {
        const stored = (localStorage.getItem("edon_plan") ?? "").toLowerCase() as PlanTier;
        const tier: PlanTier = PLANS[stored] ? stored : "starter";
        setPlanKey(tier);
        setUsage(getMockUsage(tier));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const plan = PLANS[planKey];
  const nextTierKey = plan.nextTier;
  const nextTier = nextTierKey ? PLANS[nextTierKey] : null;
  const invoices = getMockInvoices(planKey);

  const statCards = usage
    ? [
        {
          icon: Zap,
          label: "Decisions Used",
          value: usage.decisions.toLocaleString(),
          limit: plan.decisions,
          pct: usagePct(usage.decisions, plan.decisions),
          color: "text-primary",
        },
        {
          icon: Activity,
          label: "API Calls",
          value: usage.apiCalls.toLocaleString(),
          limit: null,
          pct: null,
          color: "text-blue-400",
        },
        {
          icon: Users,
          label: "Agents Connected",
          value: String(usage.agentsConnected),
          limit: null,
          pct: null,
          color: "text-violet-400",
        },
        {
          icon: Users,
          label: "Team Members",
          value: String(usage.teamMembers),
          limit: plan.members,
          pct: usagePct(usage.teamMembers, plan.members),
          color: "text-amber-400",
        },
      ]
    : [];

  const limitRows = [
    { feature: "Decisions / month", limit: plan.decisions, used: usage?.decisions ?? 0 },
    { feature: "API Keys", limit: plan.apiKeys, used: 2 },
    { feature: "Team Members", limit: plan.members, used: usage?.teamMembers ?? 1 },
    { feature: "Policy Packs", limit: plan.policyPacks, used: 1 },
    { feature: "Channels", limit: plan.channels, used: 1 },
    { feature: "Audit Retention (days)", limit: plan.auditDays, used: null },
  ];

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 max-w-4xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6"
        >
          {/* Page title */}
          <div>
            <h1 className="text-xl font-semibold text-foreground/90">Usage & Billing</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Track your usage, manage your plan, and view billing history.
            </p>
          </div>

          {/* ── PLAN BANNER ──────────────────────────── */}
          <section className="glass-card px-6 py-5">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/20 border border-primary/30">
                  <Zap className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {loading ? (
                      <Skeleton className="h-5 w-24" />
                    ) : (
                      <p className="text-base font-semibold">{plan.label} Plan</p>
                    )}
                    <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 text-xs">
                      Active
                    </Badge>
                  </div>
                  {loading ? (
                    <Skeleton className="h-3 w-32 mt-1.5" />
                  ) : (
                    <p className="text-sm text-muted-foreground mt-0.5">
                      {plan.monthlyPrice > 0 ? `$${plan.monthlyPrice}/month` : "Custom pricing"}
                    </p>
                  )}
                </div>
              </div>
              {nextTier && (
                <Button
                  variant="outline"
                  className="gap-2 border-primary/40 text-primary hover:bg-primary/10"
                  onClick={() => window.open("https://edoncore.com/pricing", "_blank")}
                >
                  <TrendingUp className="w-4 h-4" />
                  Upgrade to {nextTier.label}
                  <ExternalLink className="w-3 h-3" />
                </Button>
              )}
            </div>
          </section>

          {/* ── USAGE STATS ──────────────────────────── */}
          <section>
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
              Usage this month
            </p>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {loading
                ? Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="glass-card px-4 py-4 space-y-2">
                      <Skeleton className="h-3 w-20" />
                      <Skeleton className="h-6 w-16" />
                      <Skeleton className="h-1.5 w-full" />
                    </div>
                  ))
                : statCards.map((card) => {
                    const Icon = card.icon;
                    return (
                      <div key={card.label} className="glass-card px-4 py-4 space-y-2">
                        <div className="flex items-center gap-1.5">
                          <Icon className={`w-3.5 h-3.5 ${card.color}`} />
                          <p className="text-xs text-muted-foreground">{card.label}</p>
                        </div>
                        <p className="text-2xl font-bold tabular-nums">{card.value}</p>
                        {card.pct !== null && card.limit !== null && (
                          <>
                            <Progress
                              value={card.pct}
                              className="h-1.5"
                            />
                            <p className="text-xs text-muted-foreground">
                              of {fmtLimit(card.limit)} limit
                            </p>
                          </>
                        )}
                      </div>
                    );
                  })}
            </div>
          </section>

          {/* ── PLAN LIMITS TABLE ────────────────────── */}
          <section>
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
              Plan limits
            </p>
            <div className="glass-card overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="border-white/10 hover:bg-white/5">
                    <TableHead className="text-muted-foreground">Feature</TableHead>
                    <TableHead className="text-muted-foreground">Your Limit</TableHead>
                    <TableHead className="text-muted-foreground">Used</TableHead>
                    <TableHead className="text-muted-foreground">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading
                    ? Array.from({ length: 6 }).map((_, i) => (
                        <TableRow key={i} className="border-white/10">
                          <TableCell colSpan={4}>
                            <Skeleton className="h-6 w-full" />
                          </TableCell>
                        </TableRow>
                      ))
                    : limitRows.map((row) => {
                        const used = row.used ?? null;
                        const pct = used !== null && row.limit ? usagePct(used, row.limit) : 0;
                        const isOver = pct >= 90;
                        return (
                          <TableRow
                            key={row.feature}
                            className="border-white/10 hover:bg-white/5 transition-colors"
                          >
                            <TableCell className="font-medium text-sm">{row.feature}</TableCell>
                            <TableCell className="text-sm text-muted-foreground tabular-nums">
                              {fmtLimit(row.limit)}
                            </TableCell>
                            <TableCell className="text-sm text-muted-foreground tabular-nums">
                              {used !== null ? used.toLocaleString() : "—"}
                            </TableCell>
                            <TableCell>
                              {used !== null && row.limit ? (
                                isOver ? (
                                  <Badge className="bg-red-500/15 text-red-400 border border-red-500/25 text-xs">
                                    Near limit
                                  </Badge>
                                ) : (
                                  <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 text-xs">
                                    OK
                                  </Badge>
                                )
                              ) : (
                                <Badge className="bg-white/5 text-muted-foreground border border-white/10 text-xs">
                                  —
                                </Badge>
                              )}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                </TableBody>
              </Table>
            </div>
          </section>

          {/* ── BILLING HISTORY ──────────────────────── */}
          {invoices.length > 0 && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
                Billing history
              </p>
              <div className="glass-card overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="border-white/10 hover:bg-white/5">
                      <TableHead className="text-muted-foreground">Period</TableHead>
                      <TableHead className="text-muted-foreground">Amount</TableHead>
                      <TableHead className="text-muted-foreground">Status</TableHead>
                      <TableHead className="text-muted-foreground text-right">Invoice</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {invoices.map((inv) => (
                      <TableRow
                        key={inv.id}
                        className="border-white/10 hover:bg-white/5 transition-colors"
                      >
                        <TableCell className="font-medium text-sm">{inv.period}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          ${inv.amount.toLocaleString()}
                        </TableCell>
                        <TableCell>
                          <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 text-xs">
                            {inv.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <button
                            type="button"
                            onClick={() => window.open("https://edoncore.com/billing", "_blank")}
                            className="text-xs text-primary hover:underline inline-flex items-center gap-1"
                          >
                            View <ExternalLink className="w-3 h-3" />
                          </button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </section>
          )}

          {/* ── UPGRADE SECTION ──────────────────────── */}
          {nextTierKey && nextTier && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
                Upgrade your plan
              </p>
              <div className="glass-card px-6 py-5 border border-primary/20">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="space-y-3">
                    <div>
                      <p className="text-base font-semibold text-foreground/90">
                        {nextTier.label} Plan
                      </p>
                      <p className="text-sm text-muted-foreground mt-0.5">
                        {nextTier.monthlyPrice > 0
                          ? `$${nextTier.monthlyPrice}/month`
                          : "Contact us for pricing"}
                      </p>
                    </div>
                    <ul className="space-y-1.5">
                      {NEXT_TIER_HIGHLIGHTS[nextTierKey].map((highlight) => (
                        <li key={highlight} className="flex items-center gap-2 text-sm">
                          <CheckCircle2 className="w-3.5 h-3.5 text-primary shrink-0" />
                          <span>{highlight}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <Button
                    className="gap-2 shrink-0"
                    onClick={() => window.open("https://edoncore.com/pricing", "_blank")}
                  >
                    <TrendingUp className="w-4 h-4" />
                    Upgrade to {nextTier.label}
                    <ExternalLink className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            </section>
          )}
        </motion.div>
      </main>
    </div>
  );
}
