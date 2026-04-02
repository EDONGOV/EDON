import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import { Check, Lock, Plus, ExternalLink } from "lucide-react";
import {
  DOMAINS,
  DomainId,
  getActiveDomains,
  enableDomain,
  disableDomain,
} from "@/lib/workspaceProfile";

const DOMAIN_ORDER: DomainId[] = [
  "ai_agents",
  "industrial",
  "drones",
  "humanoids",
  "medical",
  "swarm",
  "edge",
];

const COLOR_MAP: Record<string, string> = {
  sky: "border-sky-500/30 bg-sky-500/10 text-sky-400",
  amber: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  violet: "border-violet-500/30 bg-violet-500/10 text-violet-400",
  emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  rose: "border-rose-500/30 bg-rose-500/10 text-rose-400",
  teal: "border-teal-500/30 bg-teal-500/10 text-teal-400",
  yellow: "border-yellow-500/30 bg-yellow-500/10 text-yellow-400",
  slate: "border-slate-500/30 bg-slate-500/10 text-slate-400",
};

const ICON_BG_MAP: Record<string, string> = {
  sky: "bg-sky-500/15",
  amber: "bg-amber-500/15",
  violet: "bg-violet-500/15",
  emerald: "bg-emerald-500/15",
  rose: "bg-rose-500/15",
  teal: "bg-teal-500/15",
  yellow: "bg-yellow-500/15",
  slate: "bg-slate-500/15",
};

export default function Capabilities() {
  const { toast } = useToast();
  const [activeDomains, setActiveDomains] = useState<DomainId[]>(
    () => getActiveDomains()
  );

  const isActive = (id: DomainId) => activeDomains.includes(id);
  const isCoreAlwaysOn = (id: DomainId) => id === "ai_agents";

  const handleToggle = (id: DomainId, enabled: boolean) => {
    if (isCoreAlwaysOn(id)) return;

    if (enabled) {
      enableDomain(id);
      setActiveDomains((prev) => [...prev, id]);
      const domain = DOMAINS[id];
      const extras = domain.navExtras.length > 0
        ? ` — ${domain.navExtras.map((e) => e.label).join(", ")} added to navigation`
        : "";
      toast({
        title: `${domain.label} enabled`,
        description: `New governance capabilities unlocked${extras}.`,
      });
      window.dispatchEvent(new Event("edon-profile-updated"));
    } else {
      disableDomain(id);
      setActiveDomains((prev) => prev.filter((d) => d !== id));
      toast({
        title: `${DOMAINS[id].label} disabled`,
        description: "You can re-enable this any time.",
      });
      window.dispatchEvent(new Event("edon-profile-updated"));
    }
  };

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 max-w-3xl">

        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground mb-1">Workspace</p>
          <h1 className="text-2xl font-semibold">Capabilities</h1>
          <p className="text-sm text-muted-foreground mt-2">
            Enable governance for new system types as your deployment grows.
            Your dashboard updates automatically.
          </p>
        </motion.div>

        {/* Active count summary */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="flex items-center gap-3 mb-6 rounded-xl border border-white/10 bg-white/5 px-4 py-3"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/20">
            <Check className="h-4 w-4 text-primary" />
          </div>
          <div>
            <p className="text-sm font-medium">
              {activeDomains.length} capability area{activeDomains.length !== 1 ? "s" : ""} active
            </p>
            <p className="text-xs text-muted-foreground">
              {activeDomains.map((id) => DOMAINS[id]?.label).join(" · ")}
            </p>
          </div>
        </motion.div>

        {/* Domain cards */}
        <div className="space-y-3">
          {DOMAIN_ORDER.map((id, index) => {
            const domain = DOMAINS[id];
            if (!domain) return null;
            const active = isActive(id);
            const locked = isCoreAlwaysOn(id);
            const colorClass = COLOR_MAP[domain.color] || COLOR_MAP["slate"];
            const iconBgClass = ICON_BG_MAP[domain.color] || ICON_BG_MAP["slate"];

            return (
              <motion.div
                key={id}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.04 }}
                className={`rounded-xl border transition-all ${
                  active
                    ? "border-white/20 bg-white/5"
                    : "border-white/8 bg-white/[0.02]"
                }`}
              >
                <div className="flex items-start gap-4 p-5">
                  {/* Icon */}
                  <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-2xl ${iconBgClass}`}>
                    {domain.icon}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <p className="font-semibold">{domain.label}</p>
                      {locked && (
                        <Badge variant="outline" className="text-[10px] border-white/20 text-muted-foreground gap-1">
                          <Lock className="h-2.5 w-2.5" /> Always on
                        </Badge>
                      )}
                      {active && !locked && (
                        <Badge variant="outline" className={`text-[10px] ${colorClass} gap-1`}>
                          <Check className="h-2.5 w-2.5" /> Active
                        </Badge>
                      )}
                      {domain.navExtras.length > 0 && active && (
                        <Badge variant="outline" className="text-[10px] border-white/15 text-muted-foreground">
                          + {domain.navExtras.map((e) => e.label).join(", ")} in nav
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mb-3">
                      {domain.description}
                    </p>

                    {/* Features */}
                    <AnimatePresence>
                      {active && (
                        <motion.ul
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: "auto" }}
                          exit={{ opacity: 0, height: 0 }}
                          className="space-y-1 overflow-hidden"
                        >
                          {domain.features.map((f) => (
                            <li key={f.id} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                              <Check className="h-3 w-3 text-primary shrink-0" />
                              {f.label}
                            </li>
                          ))}
                        </motion.ul>
                      )}
                    </AnimatePresence>

                    {!active && (
                      <ul className="space-y-1">
                        {domain.features.slice(0, 2).map((f) => (
                          <li key={f.id} className="flex items-center gap-1.5 text-xs text-muted-foreground/50">
                            <Plus className="h-3 w-3 shrink-0" />
                            {f.label}
                          </li>
                        ))}
                        {domain.features.length > 2 && (
                          <li className="text-xs text-muted-foreground/40 pl-4">
                            +{domain.features.length - 2} more features
                          </li>
                        )}
                      </ul>
                    )}
                  </div>

                  {/* Toggle */}
                  <div className="shrink-0 pt-0.5">
                    {locked ? (
                      <Switch checked disabled />
                    ) : (
                      <Switch
                        checked={active}
                        onCheckedChange={(v) => handleToggle(id, v)}
                      />
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Footer */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="mt-8 rounded-xl border border-white/10 bg-white/5 px-5 py-4 flex items-center justify-between"
        >
          <div>
            <p className="text-sm font-medium">Need a capability we don't have yet?</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              We're building governance for new system types. Let us know what you need.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5 shrink-0"
            onClick={() => window.open("mailto:hello@edoncore.com?subject=New capability request", "_blank")}
          >
            <ExternalLink className="h-3.5 w-3.5" /> Request
          </Button>
        </motion.div>

      </main>
    </div>
  );
}
