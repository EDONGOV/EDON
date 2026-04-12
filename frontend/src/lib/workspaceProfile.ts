/**
 * Workspace Profile System
 *
 * Controls what each customer sees based on what they're governing.
 * EDON team members (admins) always see everything.
 *
 * Stored in localStorage as:
 *   edon_workspace_profile  — active profile id
 *   edon_active_domains     — JSON array of enabled domain ids (can grow over time)
 *   edon_is_admin           — "true" if EDON team member
 */

export type DomainId =
  | "ai_agents"
  | "industrial"
  | "drones"
  | "humanoids"
  | "medical"
  | "edge"
  | "swarm";

export interface WorkspaceDomain {
  id: DomainId;
  label: string;
  description: string;
  icon: string;          // emoji for quick rendering without icon dependency
  features: FeatureFlag[];
  navExtras: NavExtra[];  // additional nav items unlocked by this domain
  color: string;          // tailwind color class prefix e.g. "sky"
  comingSoon?: boolean;
}

export interface FeatureFlag {
  id: string;
  label: string;
}

export interface NavExtra {
  to: string;
  label: string;
}

export type ProfileId =
  | "ai_agents"
  | "industrial"
  | "drones"
  | "humanoids"
  | "medical"
  | "multi";

export interface WorkspaceProfile {
  id: ProfileId;
  label: string;
  tagline: string;
  description: string;
  icon: string;
  color: string;
  defaultDomains: DomainId[];
  suggestedPolicyPack: string;
}

// ─────────────────────────────────────────────
// Domain definitions
// ─────────────────────────────────────────────

export const DOMAINS: Record<DomainId, WorkspaceDomain> = {
  ai_agents: {
    id: "ai_agents",
    label: "AI Agents",
    description: "Govern LLMs, chatbots, autonomous agents, and AI pipelines",
    icon: "🤖",
    color: "sky",
    features: [
      { id: "decisions", label: "Decision stream" },
      { id: "agents", label: "Agent registry" },
      { id: "policies", label: "Policy packs" },
      { id: "audit", label: "Audit trail" },
      { id: "fleet_learning", label: "Fleet learning" },
      { id: "prompt_injection", label: "Prompt injection detection" },
    ],
    navExtras: [],
  },
  industrial: {
    id: "industrial",
    label: "Industrial Robotics",
    description: "Conveyors, forklifts, assembly arms, and factory automation",
    icon: "🏭",
    color: "amber",
    features: [
      { id: "cav_telemetry", label: "Operator cognitive telemetry" },
      { id: "robot_stability", label: "Robot stability monitoring" },
      { id: "anomaly_detection", label: "Behavioral anomaly detection" },
    ],
    navExtras: [{ to: "/telemetry", label: "Telemetry" }],
  },
  drones: {
    id: "drones",
    label: "Drones / UAVs",
    description: "Delivery, inspection, agricultural, and surveillance drones",
    icon: "🚁",
    color: "violet",
    features: [
      { id: "swarm_budgets", label: "Swarm action budgets" },
      { id: "swarm_quorum", label: "Quorum rules" },
      { id: "swarm_dosage", label: "Payload caps" },
      { id: "cav_telemetry", label: "Operator telemetry" },
    ],
    navExtras: [], // /swarm coming soon
  },
  humanoids: {
    id: "humanoids",
    label: "Humanoid Robots",
    description: "Bipedal robots and full-body autonomous systems",
    icon: "🦾",
    color: "emerald",
    features: [
      { id: "cav_telemetry", label: "Operator cognitive telemetry" },
      { id: "robot_stability", label: "Stability monitoring" },
      { id: "human_review", label: "Human-in-the-loop escalation" },
    ],
    navExtras: [], // /telemetry coming soon
  },
  medical: {
    id: "medical",
    label: "Medical / Nanobots",
    description: "Nanobot drug delivery, surgical assistants, and medical AI",
    icon: "💊",
    color: "rose",
    features: [
      { id: "dosage_caps", label: "Dosage caps" },
      { id: "swarm_quorum", label: "Quorum rules for delivery" },
      { id: "edge_offline", label: "Edge / offline operation" },
      { id: "acoustic_transport", label: "Acoustic transport adapter" },
    ],
    navExtras: [], // /swarm and /edge coming soon
    comingSoon: false,
  },
  edge: {
    id: "edge",
    label: "Edge Nodes",
    description: "Offline swarm controllers that sync back when reconnected",
    icon: "📡",
    color: "teal",
    features: [
      { id: "edge_registration", label: "Edge node registration" },
      { id: "policy_bundle", label: "Compiled policy bundles" },
      { id: "offline_sync", label: "Offline action sync" },
    ],
    navExtras: [], // /edge coming soon
  },
  swarm: {
    id: "swarm",
    label: "Swarm Coordination",
    description: "Collective action budgets, quorum rules, and dosage caps",
    icon: "🐝",
    color: "yellow",
    features: [
      { id: "swarm_budgets", label: "Action budgets" },
      { id: "swarm_quorum", label: "Quorum rules" },
      { id: "swarm_dosage", label: "Dosage caps" },
    ],
    navExtras: [], // /swarm coming soon
  },
};

// ─────────────────────────────────────────────
// Profile definitions (what customers pick at onboarding)
// ─────────────────────────────────────────────

export const PROFILES: WorkspaceProfile[] = [
  {
    id: "ai_agents",
    label: "AI Agents",
    tagline: "Govern LLMs, chatbots & pipelines",
    description:
      "You're deploying AI agents — LLMs, autonomous pipelines, chatbots, or tool-calling assistants. EDON governs every action they take.",
    icon: "🤖",
    color: "sky",
    defaultDomains: ["ai_agents"],
    suggestedPolicyPack: "work_safe",
  },
  {
    id: "industrial",
    label: "Industrial Robotics",
    tagline: "Forklifts, assembly arms & factory automation",
    description:
      "Physical robots on a factory floor. EDON monitors operator cognitive load and robot stability before every high-risk action.",
    icon: "🏭",
    color: "amber",
    defaultDomains: ["ai_agents", "industrial"],
    suggestedPolicyPack: "personal_safe",
  },
  {
    id: "drones",
    label: "Drones / UAVs",
    tagline: "Delivery, inspection & agricultural fleets",
    description:
      "Drone swarms with collective governance. Action budgets, quorum rules, and payload caps ensure the whole fleet stays within bounds.",
    icon: "🚁",
    color: "violet",
    defaultDomains: ["ai_agents", "drones", "swarm"],
    suggestedPolicyPack: "work_safe",
  },
  {
    id: "humanoids",
    label: "Humanoid Robots",
    tagline: "Bipedal robots & full-body autonomy",
    description:
      "Humanoid systems operating near people. EDON escalates to human review for any action outside the defined safety envelope.",
    icon: "🦾",
    color: "emerald",
    defaultDomains: ["ai_agents", "humanoids"],
    suggestedPolicyPack: "personal_safe",
  },
  {
    id: "medical",
    label: "Medical / Nanobots",
    tagline: "Drug delivery, surgical AI & nanobot swarms",
    description:
      "The highest-stakes environment. Every delivery is governed by dosage caps, quorum requirements, and a physician escalation queue.",
    icon: "💊",
    color: "rose",
    defaultDomains: ["ai_agents", "medical", "swarm", "edge"],
    suggestedPolicyPack: "personal_safe",
  },
  {
    id: "multi",
    label: "Multiple / Custom",
    tagline: "Mix of agent types — I'll configure manually",
    description:
      "You have a mix of AI agents and physical systems, or you want to pick exactly which capabilities to enable from scratch.",
    icon: "⚙️",
    color: "slate",
    defaultDomains: ["ai_agents"],
    suggestedPolicyPack: "work_safe",
  },
];

// ─────────────────────────────────────────────
// Storage helpers
// ─────────────────────────────────────────────

const PROFILE_KEY = "edon_workspace_profile";
const DOMAINS_KEY = "edon_active_domains";
const ADMIN_KEY = "edon_is_admin";
const ONBOARDED_KEY = "edon_onboarding_complete";
const PREVIEW_KEY = "edon_preview_mode";

export function getActiveProfile(): ProfileId | null {
  return (localStorage.getItem(PROFILE_KEY) as ProfileId) || null;
}

export function setActiveProfile(id: ProfileId): void {
  localStorage.setItem(PROFILE_KEY, id);
}

export function getActiveDomains(): DomainId[] {
  try {
    const raw = localStorage.getItem(DOMAINS_KEY);
    if (!raw) return ["ai_agents"];
    return JSON.parse(raw) as DomainId[];
  } catch {
    return ["ai_agents"];
  }
}

export function setActiveDomains(domains: DomainId[]): void {
  localStorage.setItem(DOMAINS_KEY, JSON.stringify(domains));
}

export function enableDomain(id: DomainId): void {
  const current = getActiveDomains();
  if (!current.includes(id)) {
    setActiveDomains([...current, id]);
  }
}

export function disableDomain(id: DomainId): void {
  const current = getActiveDomains();
  setActiveDomains(current.filter((d) => d !== id));
}

export function isAdmin(): boolean {
  return localStorage.getItem(ADMIN_KEY) === "true";
}

export function setAdmin(value: boolean): void {
  localStorage.setItem(ADMIN_KEY, value ? "true" : "false");
}

export function isOnboardingComplete(): boolean {
  return localStorage.getItem(ONBOARDED_KEY) === "true";
}

export function markOnboardingComplete(): void {
  localStorage.setItem(ONBOARDED_KEY, "true");
}

// ─────────────────────────────────────────────
// Preview mode — lets admins see the customer view
// ─────────────────────────────────────────────

export function isPreviewMode(): boolean {
  return localStorage.getItem(PREVIEW_KEY) === "true";
}

export function setPreviewMode(value: boolean): void {
  if (value) {
    localStorage.setItem(PREVIEW_KEY, "true");
  } else {
    localStorage.removeItem(PREVIEW_KEY);
  }
  window.dispatchEvent(new Event("edon-preview-updated"));
}

// ─────────────────────────────────────────────
// Nav helpers — what routes should the nav show?
// ─────────────────────────────────────────────

export interface NavItem {
  to: string;
  label: string;
  iconName: string;
  minRole?: 'admin' | 'operator' | 'viewer';
}

/** Base nav items shown to every customer regardless of profile. */
export const BASE_NAV: NavItem[] = [
  { to: "/",          label: "Dashboard",    iconName: "Gauge" },
  { to: "/decisions", label: "Decisions",    iconName: "ListChecks" },
  { to: "/agents",    label: "Agents",       iconName: "Bot" },
  { to: "/audit",     label: "Audit",        iconName: "FileSearch",    minRole: "operator" },
  { to: "/policies",  label: "Policies",     iconName: "ShieldCheck",   minRole: "operator" },
  { to: "/review",    label: "Review Queue", iconName: "ClipboardList", minRole: "operator" },
  { to: "/hgi",       label: "HGI",          iconName: "ShieldAlert",   minRole: "operator" },
  { to: "/settings",  label: "Settings",     iconName: "Settings2" },
];

/** Additional nav items only visible to EDON admins. */
export const ADMIN_NAV: NavItem[] = [
  { to: "/admin", label: "Admin", iconName: "Crown" },
];

/**
 * Returns the full list of nav items the current user should see.
 * Admins get everything. Customers get base + extras from their active domains.
 * Pass forceCustomer=true to simulate the customer view (used by preview mode).
 */
export function getNavItems(forceCustomer = false): NavItem[] {
  // Lazy import to avoid circular deps — auth reads localStorage directly
  const ROLE_LEVEL: Record<string, number> = { viewer: 0, operator: 1, admin: 2 };
  const storedRole = localStorage.getItem('edon_user_role') ?? '';
  const isAdminUser = isAdmin();
  const userLevel = isAdminUser && !forceCustomer ? 2 : (ROLE_LEVEL[storedRole] ?? 1);

  const filterByRole = (items: NavItem[]) =>
    items.filter(item => {
      const required = ROLE_LEVEL[item.minRole ?? 'viewer'] ?? 0;
      return userLevel >= required;
    });

  if (isAdminUser && !forceCustomer) {
    const allExtras: NavItem[] = Object.values(DOMAINS).flatMap((d) =>
      d.navExtras.map((e) => ({ to: e.to, label: e.label, iconName: "Circle" }))
    );
    const seen = new Set<string>();
    const deduped = [...BASE_NAV, ...allExtras, ...ADMIN_NAV].filter((item) => {
      if (seen.has(item.to)) return false;
      seen.add(item.to);
      return true;
    });
    return filterByRole(deduped);
  }

  const activeDomains = getActiveDomains();
  const extras: NavItem[] = activeDomains.flatMap((domainId) => {
    const domain = DOMAINS[domainId];
    return domain
      ? domain.navExtras.map((e) => ({ to: e.to, label: e.label, iconName: "Circle" }))
      : [];
  });

  const seen = new Set<string>();
  const all = [...BASE_NAV, ...extras].filter((item) => {
    if (seen.has(item.to)) return false;
    seen.add(item.to);
    return true;
  });
  return filterByRole(all);
}

/**
 * Check if a specific feature is enabled for the current workspace.
 * Admins always have all features.
 */
export function hasFeature(featureId: string): boolean {
  if (isAdmin()) return true;
  const activeDomains = getActiveDomains();
  return activeDomains.some((domainId) => {
    const domain = DOMAINS[domainId];
    return domain?.features.some((f) => f.id === featureId) ?? false;
  });
}

/**
 * Initialize a new workspace after onboarding.
 * Sets the profile and its default domains.
 */
export function initWorkspace(profileId: ProfileId): void {
  const profile = PROFILES.find((p) => p.id === profileId);
  if (!profile) return;
  setActiveProfile(profileId);
  setActiveDomains(profile.defaultDomains);
  markOnboardingComplete();
}
