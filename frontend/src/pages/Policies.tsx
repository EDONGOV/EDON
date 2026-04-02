import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { TopNav } from '@/components/TopNav';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Shield, ShieldCheck, ShieldAlert, Zap, Check, ChevronRight,
  RefreshCcw, Lock, Briefcase, Bot, ChevronDown, X,
  Search, BarChart2, Headphones, UserCog, Plus,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { edonApi, isMockMode, getToken } from '@/lib/api';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';

/* ─────────────────────────────────────────────
   Types
───────────────────────────────────────────── */
interface PolicyPack {
  name: string;
  description: string;
  risk_level: string;
  scope_summary: Record<string, number>;
  constraints_summary: { allowed_tools: number; blocked_tools: number; confirm_required: boolean };
}

interface PolicyPackWithMeta extends PolicyPack {
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  bgGradient: string;
  borderColor: string;
}

interface CustomPolicyRules {
  allowedTools: string[];
  blockedTools: string[];
  confirmActions: string[];
  maxActionsPerHour: number;
  blockAfterHours: boolean;
  riskLevel: 'low' | 'medium' | 'high';
  agentTypes: string[];
  notes: string;
}

interface CustomPolicy {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  rules?: CustomPolicyRules;
}

/* ─────────────────────────────────────────────
   Tool taxonomy — Digital + Physical
───────────────────────────────────────────── */
export const TOOL_CATEGORIES: Record<string, string[]> = {
  'Web & Research': ['web.search', 'web.browse', 'web.scrape'],
  'Files & Storage': ['file.read', 'file.write', 'file.delete', 'file.delete_bulk'],
  'Email & Calendar': ['email.read', 'email.send', 'email.draft', 'calendar.read', 'calendar.write', 'calendar.delete'],
  'Tasks & Notes': ['task.create', 'task.update', 'task.delete', 'notes.create', 'notes.read', 'notes.update'],
  'APIs & Integrations': ['api.call', 'api.post', 'api.delete'],
  'Database & Data': ['db.query', 'db.write', 'db.admin', 'data.read', 'data.write', 'data.export'],
  'Shell & Code': ['shell.exec', 'shell.admin', 'code.execute', 'code.deploy'],
  'Users & Identity': ['user.lookup', 'user.modify', 'user.delete'],
  'Reports & Knowledge': ['report.generate', 'report.share', 'knowledge.search', 'knowledge.write'],
  'Finance & Payments': ['finance.query', 'finance.transfer', 'payment.process'],
  'Tickets & Support': ['ticket.create', 'ticket.update', 'ticket.close'],
  'System': ['system.admin', 'system.shutdown', 'llm.invoke', 'llm.finetune'],
  '🤖 Physical — Navigation': ['navigation.move', 'navigation.stop', 'navigation.plan'],
  '🤖 Physical — Flight': ['flight.takeoff', 'flight.land', 'flight.waypoint', 'flight.abort'],
  '🤖 Physical — Actuators': ['actuator.control', 'actuator.emergency_stop', 'motor.control', 'gripper.control', 'arm.move', 'arm.grasp', 'arm.release'],
  '🤖 Physical — Sensors': ['sensor.read', 'sensor.configure', 'camera.capture', 'camera.stream', 'camera.record'],
  '🤖 Physical — Comms': ['communication.broadcast', 'communication.send'],
};

export const ALL_TOOLS: string[] = Object.values(TOOL_CATEGORIES).flat();

/* ─────────────────────────────────────────────
   Pack definitions — all 6 real gateway packs
───────────────────────────────────────────── */
export const PACK_ALLOWED_TOOLS: Record<string, string[]> = {
  casual_user: [
    'web.search', 'web.browse', 'file.read', 'calendar.read', 'email.read',
    'notes.create', 'notes.read', 'knowledge.search', 'data.read', 'report.generate',
  ],
  market_analyst: [
    'web.search', 'web.browse', 'web.scrape', 'finance.query', 'data.read', 'data.export',
    'report.generate', 'report.share', 'calendar.read', 'notes.create', 'notes.read',
    'knowledge.search', 'email.read', 'file.read',
  ],
  ops_commander: [
    'web.search', 'web.browse', 'file.read', 'file.write', 'email.read', 'email.send',
    'email.draft', 'calendar.read', 'calendar.write', 'task.create', 'task.update',
    'api.call', 'db.query', 'user.lookup', 'report.generate', 'data.read',
    'ticket.create', 'ticket.update', 'notes.create', 'knowledge.search', 'knowledge.write',
  ],
  founder_mode: [
    'web.search', 'web.browse', 'web.scrape', 'file.read', 'file.write',
    'email.read', 'email.send', 'email.draft', 'calendar.read', 'calendar.write',
    'task.create', 'task.update', 'api.call', 'api.post', 'db.query', 'db.write',
    'user.lookup', 'user.modify', 'report.generate', 'report.share',
    'data.read', 'data.write', 'data.export', 'finance.query', 'knowledge.search',
    'knowledge.write', 'notes.create', 'notes.update', 'ticket.create', 'ticket.update',
    'ticket.close', 'code.execute', 'llm.invoke',
  ],
  helpdesk: [
    'email.read', 'email.send', 'email.draft', 'ticket.create', 'ticket.update', 'ticket.close',
    'knowledge.search', 'user.lookup', 'notes.create', 'notes.read', 'calendar.read',
    'web.search', 'data.read', 'report.generate',
  ],
  autonomy_mode: [
    'web.search', 'web.browse', 'web.scrape', 'file.read', 'file.write', 'file.delete',
    'email.read', 'email.send', 'email.draft', 'calendar.read', 'calendar.write', 'calendar.delete',
    'task.create', 'task.update', 'task.delete', 'notes.create', 'notes.read', 'notes.update',
    'api.call', 'api.post', 'api.delete', 'db.query', 'db.write', 'data.read', 'data.write', 'data.export',
    'shell.exec', 'code.execute', 'user.lookup', 'user.modify',
    'report.generate', 'report.share', 'knowledge.search', 'knowledge.write',
    'finance.query', 'ticket.create', 'ticket.update', 'ticket.close', 'llm.invoke',
    'navigation.move', 'navigation.stop', 'navigation.plan',
    'sensor.read', 'camera.capture', 'camera.stream',
    'communication.broadcast', 'communication.send',
  ],
};

export const PACK_BLOCKED_TOOLS: Record<string, string[]> = {
  casual_user: [
    'email.send', 'file.write', 'file.delete', 'file.delete_bulk',
    'calendar.write', 'calendar.delete', 'task.create', 'task.update', 'task.delete',
    'api.call', 'api.post', 'api.delete', 'db.query', 'db.write', 'db.admin',
    'shell.exec', 'shell.admin', 'code.execute', 'code.deploy',
    'user.modify', 'user.delete', 'finance.transfer', 'payment.process',
    'data.write', 'data.export', 'system.admin', 'system.shutdown', 'llm.finetune',
    'navigation.move', 'navigation.stop', 'navigation.plan',
    'flight.takeoff', 'flight.land', 'flight.waypoint', 'flight.abort',
    'actuator.control', 'actuator.emergency_stop', 'motor.control', 'gripper.control',
    'arm.move', 'arm.grasp', 'arm.release', 'sensor.configure',
    'camera.record', 'communication.broadcast',
  ],
  market_analyst: [
    'email.send', 'file.write', 'file.delete', 'file.delete_bulk',
    'calendar.write', 'calendar.delete', 'task.create', 'task.update', 'task.delete',
    'api.post', 'api.delete', 'db.write', 'db.admin',
    'shell.exec', 'shell.admin', 'code.execute', 'code.deploy',
    'user.modify', 'user.delete', 'finance.transfer', 'payment.process',
    'data.write', 'system.admin', 'system.shutdown', 'llm.finetune',
    'navigation.move', 'navigation.stop', 'navigation.plan',
    'flight.takeoff', 'flight.land', 'flight.waypoint', 'flight.abort',
    'actuator.control', 'actuator.emergency_stop', 'motor.control', 'gripper.control',
    'arm.move', 'arm.grasp', 'arm.release',
  ],
  ops_commander: [
    'file.delete', 'file.delete_bulk', 'calendar.delete', 'task.delete',
    'api.delete', 'db.write', 'db.admin', 'shell.exec', 'shell.admin',
    'code.execute', 'code.deploy', 'user.modify', 'user.delete',
    'finance.transfer', 'payment.process', 'data.write',
    'system.admin', 'system.shutdown', 'llm.finetune',
    'navigation.move', 'navigation.plan', 'flight.takeoff', 'flight.land',
    'flight.waypoint', 'flight.abort', 'actuator.control', 'actuator.emergency_stop',
    'motor.control', 'gripper.control', 'arm.move', 'arm.grasp', 'arm.release',
  ],
  founder_mode: [
    'file.delete_bulk', 'db.admin', 'shell.admin', 'code.deploy',
    'user.delete', 'finance.transfer', 'payment.process',
    'system.admin', 'system.shutdown', 'llm.finetune',
    'navigation.move', 'navigation.plan', 'flight.takeoff', 'flight.land',
    'flight.waypoint', 'flight.abort', 'actuator.control', 'actuator.emergency_stop',
    'motor.control', 'gripper.control', 'arm.move', 'arm.grasp', 'arm.release',
  ],
  helpdesk: [
    'file.write', 'file.delete', 'file.delete_bulk',
    'calendar.write', 'calendar.delete', 'task.delete',
    'api.post', 'api.delete', 'db.query', 'db.write', 'db.admin',
    'shell.exec', 'shell.admin', 'code.execute', 'code.deploy',
    'user.modify', 'user.delete', 'finance.query', 'finance.transfer', 'payment.process',
    'data.write', 'data.export', 'system.admin', 'system.shutdown', 'llm.invoke', 'llm.finetune',
    'navigation.move', 'navigation.stop', 'navigation.plan',
    'flight.takeoff', 'flight.land', 'flight.waypoint', 'flight.abort',
    'actuator.control', 'actuator.emergency_stop', 'motor.control', 'gripper.control',
    'arm.move', 'arm.grasp', 'arm.release',
  ],
  autonomy_mode: [
    'file.delete_bulk', 'db.admin', 'shell.admin', 'code.deploy',
    'user.delete', 'finance.transfer', 'payment.process',
    'system.admin', 'system.shutdown', 'llm.finetune',
    'flight.takeoff', 'flight.abort', 'actuator.emergency_stop',
  ],
};

export const PACK_CONFIRM_ACTIONS: Record<string, string[]> = {
  casual_user: ['email.send', 'file.write', 'calendar.write', 'task.create', 'api.call'],
  market_analyst: ['email.send', 'api.call', 'data.write', 'report.share'],
  ops_commander: ['email.send', 'api.post', 'payment.process', 'user.modify', 'db.write', 'data.write', 'file.delete'],
  founder_mode: ['finance.transfer', 'payment.process', 'user.delete', 'system.admin', 'code.deploy', 'db.admin', 'shell.exec'],
  helpdesk: ['email.send', 'user.modify', 'api.call', 'ticket.close'],
  autonomy_mode: ['finance.transfer', 'payment.process', 'system.admin', 'db.admin', 'code.deploy', 'user.delete', 'flight.takeoff', 'actuator.emergency_stop'],
};

export const PACK_MAX_PER_HOUR: Record<string, number> = {
  casual_user: 200,
  market_analyst: 500,
  ops_commander: 1000,
  founder_mode: 2000,
  helpdesk: 500,
  autonomy_mode: 10000,
};

const PACK_AFTER_HOURS_BLOCK: Record<string, boolean> = {
  casual_user: true,
  market_analyst: false,
  ops_commander: false,
  founder_mode: false,
  helpdesk: false,
  autonomy_mode: false,
};

/* ─────────────────────────────────────────────
   Pack display metadata
───────────────────────────────────────────── */
const PACK_META: Record<string, {
  icon: React.ComponentType<{ className?: string }>;
  color: string; bgGradient: string; borderColor: string;
  label: string; tagline: string; agentTypes: string[];
}> = {
  casual_user: {
    icon: Lock, color: 'text-emerald-400',
    bgGradient: 'from-emerald-500/15 to-emerald-700/5',
    borderColor: 'border-emerald-500/30',
    label: 'Casual User',
    tagline: 'Ultra-safe everyday use — read-only by default',
    agentTypes: ['Digital', 'Voice', 'Browser'],
  },
  market_analyst: {
    icon: BarChart2, color: 'text-sky-400',
    bgGradient: 'from-sky-500/15 to-sky-700/5',
    borderColor: 'border-sky-500/30',
    label: 'Market Analyst',
    tagline: 'Financial research focus — read and report',
    agentTypes: ['Digital', 'Data Pipeline'],
  },
  ops_commander: {
    icon: Briefcase, color: 'text-primary',
    bgGradient: 'from-primary/15 to-primary/5',
    borderColor: 'border-primary/30',
    label: 'Ops Commander',
    tagline: 'Workflow automation with confirmations on writes',
    agentTypes: ['Digital', 'Browser', 'Voice'],
  },
  founder_mode: {
    icon: UserCog, color: 'text-violet-400',
    bgGradient: 'from-violet-500/15 to-violet-700/5',
    borderColor: 'border-violet-500/30',
    label: 'Founder Mode',
    tagline: 'Power user — broad access, conservative on irreversible ops',
    agentTypes: ['Digital', 'Browser', 'Data Pipeline'],
  },
  helpdesk: {
    icon: Headphones, color: 'text-amber-400',
    bgGradient: 'from-amber-500/15 to-amber-700/5',
    borderColor: 'border-amber-500/30',
    label: 'Helpdesk',
    tagline: 'Customer support — tickets, email, knowledge base',
    agentTypes: ['Digital', 'Voice'],
  },
  autonomy_mode: {
    icon: Zap, color: 'text-red-400',
    bgGradient: 'from-red-500/15 to-red-700/5',
    borderColor: 'border-red-500/30',
    label: 'Autonomy Mode',
    tagline: 'High-autonomy co-pilot — includes physical agent tools',
    agentTypes: ['Digital', 'Humanoid', 'Drone', 'Ground Robot', 'IoT', 'Vision'],
  },
};

/* ─────────────────────────────────────────────
   Governance mode → pack mapping
───────────────────────────────────────────── */
const GOVERNANCE_MODES = [
  {
    key: 'safe', packName: 'casual_user', title: 'Safe Mode', icon: Lock,
    gradient: 'from-emerald-500/20 to-emerald-700/10', border: 'border-emerald-500/30',
    what: 'Read-only by default. Stops any action that writes, sends, or modifies before it executes.',
    scope: 'Web search, file reads, email reads, calendar reads. Everything else requires confirmation or is blocked.',
    escalation: 'Immediate alert when a policy boundary is crossed. Every blocked action is logged.',
    useCase: 'New deployments, consumer-facing agents, and any system where safety is non-negotiable.',
  },
  {
    key: 'business', packName: 'ops_commander', title: 'Business Mode', icon: Briefcase,
    gradient: 'from-sky-500/20 to-sky-700/10', border: 'border-sky-500/30',
    what: 'Full workflow automation. Writes, sends, and task management run freely with confirmation on high-stakes ops.',
    scope: 'Emails, calendar, tasks, APIs, and database reads. Financial and destructive ops require human approval.',
    escalation: 'Escalates to team lead or audit log — full accountability without slowing operations.',
    useCase: 'Ops teams, business automation pipelines, and enterprise-scale deployments.',
  },
  {
    key: 'autonomy', packName: 'autonomy_mode', title: 'Autonomy Mode', icon: Bot,
    gradient: 'from-amber-500/20 to-orange-600/10', border: 'border-amber-500/30',
    what: 'EDON runs continuously — includes physical agent tools. Only true safety violations are blocked.',
    scope: 'Nearly everything including navigation, sensors, shell, and code execution. Irreversible ops confirm first.',
    escalation: 'Silent by design. Only critical safety violations — finance transfers, system admin — surface.',
    useCase: 'High-trust environments, always-on automation, robotics, and physical AI deployments.',
  },
] as const;

/* ─────────────────────────────────────────────
   Confirm options (full list)
───────────────────────────────────────────── */
const CONFIRM_OPTIONS = [
  'email.send', 'email.draft', 'file.write', 'file.delete', 'file.delete_bulk',
  'calendar.write', 'calendar.delete', 'task.create', 'task.delete',
  'api.call', 'api.post', 'api.delete', 'db.write', 'db.admin',
  'shell.exec', 'code.execute', 'code.deploy',
  'user.modify', 'user.delete', 'finance.transfer', 'payment.process',
  'data.write', 'data.export', 'system.admin', 'system.shutdown',
  'navigation.move', 'flight.takeoff', 'flight.abort',
  'actuator.control', 'actuator.emergency_stop',
  'communication.broadcast',
];

/* ─────────────────────────────────────────────
   LocalStorage keys
───────────────────────────────────────────── */
const PLAN_KEY = 'edon_plan';
const CUSTOM_POLICIES_KEY = 'edon_custom_policies';

/* ─────────────────────────────────────────────
   Tool Picker component
───────────────────────────────────────────── */
function ToolPicker({
  selected, onChange, label, accentClass,
}: {
  selected: string[];
  onChange: (tools: string[]) => void;
  label: string;
  accentClass: string;
}) {
  const [search, setSearch] = useState('');
  const toggle = (tool: string) =>
    onChange(selected.includes(tool) ? selected.filter((t) => t !== tool) : [...selected, tool]);

  return (
    <div className="space-y-2">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {selected.map((t) => (
            <span key={t} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-mono ${accentClass}`}>
              {t}
              <button onClick={() => toggle(t)} className="hover:opacity-70"><X className="w-2.5 h-2.5" /></button>
            </span>
          ))}
        </div>
      )}
      <div className="relative mb-1">
        <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search tools..."
          className="pl-7 h-7 text-xs bg-secondary/50"
        />
      </div>
      <ScrollArea className="h-48 rounded-lg border border-white/10 bg-white/[0.02]">
        <div className="p-2 space-y-3">
          {Object.entries(TOOL_CATEGORIES).map(([cat, tools]) => {
            const filtered = tools.filter((t) => !search || t.includes(search.toLowerCase()));
            if (filtered.length === 0) return null;
            return (
              <div key={cat}>
                <p className="text-[9px] uppercase tracking-widest text-muted-foreground/50 mb-1 px-1">{cat}</p>
                <div className="grid grid-cols-2 gap-0.5">
                  {filtered.map((tool) => (
                    <label key={tool} className="flex items-center gap-1.5 px-2 py-1 rounded-md hover:bg-white/5 cursor-pointer group">
                      <Checkbox
                        checked={selected.includes(tool)}
                        onCheckedChange={() => toggle(tool)}
                        className="w-3 h-3"
                      />
                      <span className="text-[10px] font-mono text-muted-foreground group-hover:text-foreground transition-colors">{tool}</span>
                    </label>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </ScrollArea>
      <p className="text-[10px] text-muted-foreground/50">{selected.length} tool{selected.length !== 1 ? 's' : ''} selected</p>
    </div>
  );
}

/* ─────────────────────────────────────────────
   25 pre-built custom policies
───────────────────────────────────────────── */
const DEFAULT_CUSTOM_POLICIES: CustomPolicy[] = [
  {
    id: 'default-1', name: 'Drone Delivery Ops',
    description: 'Safe autonomous delivery drone operations. Flight navigation allowed; actuators and emergency stops require human confirmation.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['navigation.move','navigation.plan','navigation.stop','sensor.read','camera.capture','camera.stream','communication.send'], blockedTools: ['arm.move','arm.grasp','arm.release','gripper.control','shell.exec','code.deploy','user.delete','db.admin'], confirmActions: ['flight.takeoff','flight.land','flight.waypoint','flight.abort','actuator.emergency_stop','actuator.control','communication.broadcast'], maxActionsPerHour: 2000, blockAfterHours: false, riskLevel: 'medium', agentTypes: ['Drone'], notes: 'Last-mile delivery drones in urban environments.' },
  },
  {
    id: 'default-2', name: 'Medical AI Assistant',
    description: 'Clinical AI with strict read-only defaults. All data writes, user modifications, and reports require confirmation. Blocks financial and shell ops.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['data.read','knowledge.search','web.search','file.read','report.generate','calendar.read','email.read'], blockedTools: ['shell.exec','shell.admin','code.deploy','user.delete','finance.transfer','payment.process','db.admin','system.admin','system.shutdown','llm.finetune'], confirmActions: ['data.write','data.export','file.write','user.modify','report.share','email.send','api.post'], maxActionsPerHour: 300, blockAfterHours: true, riskLevel: 'high', agentTypes: ['Digital','Voice'], notes: 'HIPAA-conscious defaults. All PHI writes require human approval.' },
  },
  {
    id: 'default-3', name: 'Customer Support Bot',
    description: 'Tier-1 support agent handling tickets, email responses, and knowledge base lookups. No access to financial or user modification tools.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['email.read','email.draft','ticket.create','ticket.update','ticket.close','knowledge.search','user.lookup','notes.create','notes.read','calendar.read','web.search','data.read'], blockedTools: ['finance.query','finance.transfer','payment.process','user.delete','db.admin','shell.exec','code.deploy','system.admin'], confirmActions: ['email.send','user.modify','api.call','ticket.close'], maxActionsPerHour: 500, blockAfterHours: false, riskLevel: 'low', agentTypes: ['Digital','Voice'], notes: 'Helpdesk agents; escalate to human for anything beyond tier-1.' },
  },
  {
    id: 'default-4', name: 'Security Audit Agent',
    description: 'Read-only security scanning and compliance checks. No writes, no shell execution. All findings go to report generation only.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['web.search','file.read','data.read','db.query','user.lookup','report.generate','knowledge.search','api.call'], blockedTools: ['file.write','file.delete','file.delete_bulk','db.write','db.admin','shell.exec','shell.admin','code.deploy','user.modify','user.delete','finance.transfer','payment.process','system.admin','system.shutdown'], confirmActions: ['report.share','data.export','api.post'], maxActionsPerHour: 1000, blockAfterHours: false, riskLevel: 'low', agentTypes: ['Digital','Data Pipeline'], notes: 'Penetration testing support and compliance scanning. Zero write footprint.' },
  },
  {
    id: 'default-5', name: 'DevOps Pipeline Bot',
    description: 'CI/CD automation with guardrails. Code execution and builds allowed; deploys and infrastructure changes require explicit human approval.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['code.execute','file.read','file.write','db.query','api.call','report.generate','data.read','shell.exec','knowledge.search','notes.create'], blockedTools: ['user.delete','db.admin','system.shutdown','llm.finetune','finance.transfer','payment.process','shell.admin'], confirmActions: ['code.deploy','db.write','api.post','api.delete','system.admin','file.delete','file.delete_bulk'], maxActionsPerHour: 3000, blockAfterHours: false, riskLevel: 'high', agentTypes: ['Digital','Data Pipeline'], notes: 'For automated build/test pipelines. Production deploys require 2-person approval.' },
  },
  {
    id: 'default-6', name: 'Legal Research Agent',
    description: 'Document search and analysis for legal teams. Read-only across all sources. Summaries and memos generated; no sending without approval.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['web.search','web.browse','web.scrape','file.read','data.read','knowledge.search','report.generate','notes.create','notes.read','calendar.read'], blockedTools: ['file.write','file.delete','email.send','api.post','db.write','shell.exec','code.deploy','user.modify','finance.transfer','payment.process'], confirmActions: ['report.share','email.draft','notes.update','file.write'], maxActionsPerHour: 400, blockAfterHours: true, riskLevel: 'low', agentTypes: ['Digital','Browser'], notes: 'Attorney-client privilege considerations. No external sends without lawyer sign-off.' },
  },
  {
    id: 'default-7', name: 'Financial Advisor Bot',
    description: 'Portfolio analysis and financial research. All transactions, transfers, and account modifications require human approval before execution.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['finance.query','data.read','web.search','web.browse','report.generate','calendar.read','email.read','knowledge.search','notes.create'], blockedTools: ['shell.exec','shell.admin','code.deploy','user.delete','db.admin','system.admin','system.shutdown'], confirmActions: ['finance.transfer','payment.process','email.send','report.share','api.post','data.export','user.modify'], maxActionsPerHour: 200, blockAfterHours: true, riskLevel: 'high', agentTypes: ['Digital','Voice'], notes: 'SEC/FINRA compliance mode. All advisory outputs reviewed before delivery.' },
  },
  {
    id: 'default-8', name: 'Smart Home Controller',
    description: 'IoT home automation with safety guardrails. Sensors and reads always allowed; physical actuators and broadcasts require confirmation.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['sensor.read','camera.capture','data.read','api.call','calendar.read','notes.read','knowledge.search'], blockedTools: ['shell.admin','code.deploy','user.delete','db.admin','finance.transfer','payment.process','system.shutdown','flight.takeoff','arm.move'], confirmActions: ['actuator.control','actuator.emergency_stop','motor.control','communication.broadcast','camera.stream','camera.record','sensor.configure'], maxActionsPerHour: 5000, blockAfterHours: false, riskLevel: 'medium', agentTypes: ['IoT'], notes: 'Residential automation. Safety-critical actuators always require explicit user intent.' },
  },
  {
    id: 'default-9', name: 'Social Media Manager',
    description: 'Draft-first social media agent. Content creation and scheduling are free; all public posts and sends require human review before going live.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['web.search','web.browse','file.read','notes.create','notes.read','notes.update','report.generate','calendar.read','knowledge.search','email.read'], blockedTools: ['file.delete_bulk','db.admin','shell.exec','code.deploy','user.delete','finance.transfer','payment.process','system.admin'], confirmActions: ['email.send','email.draft','file.write','api.post','api.call','data.export','report.share'], maxActionsPerHour: 300, blockAfterHours: true, riskLevel: 'medium', agentTypes: ['Digital','Browser'], notes: 'Brand safety mode. Marketing team approves all external-facing content.' },
  },
  {
    id: 'default-10', name: 'Warehouse Robot',
    description: 'Ground robot for warehouse operations. Navigation and arm movements allowed in designated zones; emergency stops are always accessible.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['navigation.move','navigation.stop','navigation.plan','sensor.read','camera.capture','arm.move','arm.grasp','arm.release','gripper.control','communication.send'], blockedTools: ['flight.takeoff','flight.land','flight.waypoint','shell.admin','code.deploy','user.delete','db.admin','finance.transfer'], confirmActions: ['actuator.emergency_stop','motor.control','communication.broadcast','camera.stream','sensor.configure'], maxActionsPerHour: 10000, blockAfterHours: false, riskLevel: 'medium', agentTypes: ['Ground Robot'], notes: 'Warehouse 3PL integration. Geofenced operations with emergency override always enabled.' },
  },
  {
    id: 'default-11', name: 'Sales Intelligence Bot',
    description: 'CRM enrichment and sales research. Read and draft only; mass emails and data exports require approval to prevent spam or data leaks.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['web.search','web.browse','web.scrape','email.read','email.draft','data.read','user.lookup','notes.create','notes.read','calendar.read','report.generate','knowledge.search'], blockedTools: ['user.delete','db.admin','shell.exec','code.deploy','finance.transfer','payment.process','system.admin','system.shutdown'], confirmActions: ['email.send','api.post','data.export','data.write','user.modify','report.share'], maxActionsPerHour: 600, blockAfterHours: true, riskLevel: 'low', agentTypes: ['Digital','Browser'], notes: 'GDPR-aware sales automation. Bulk outreach requires SDR sign-off.' },
  },
  {
    id: 'default-12', name: 'HR Onboarding Agent',
    description: 'Automates new-hire onboarding workflows. User account creation allowed; role changes, access grants, and offboarding require HR approval.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['email.read','email.draft','calendar.read','calendar.write','task.create','task.update','notes.create','knowledge.search','user.lookup','data.read','report.generate'], blockedTools: ['user.delete','db.admin','shell.admin','code.deploy','finance.transfer','payment.process','system.shutdown','llm.finetune'], confirmActions: ['email.send','user.modify','api.post','data.write','file.delete','calendar.delete'], maxActionsPerHour: 200, blockAfterHours: true, riskLevel: 'medium', agentTypes: ['Digital','Voice'], notes: 'SOC2 compliance mode. All IAM changes logged and require manager approval.' },
  },
  {
    id: 'default-13', name: 'Data Backup Pipeline',
    description: 'Automated backup and archival workflows. Reads from all sources and writes to backup targets; destructive operations are fully blocked.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['data.read','data.export','file.read','db.query','api.call','report.generate','notes.create'], blockedTools: ['file.delete','file.delete_bulk','db.write','db.admin','user.delete','shell.admin','code.deploy','system.shutdown','finance.transfer'], confirmActions: ['data.write','api.post','user.modify','file.write'], maxActionsPerHour: 5000, blockAfterHours: false, riskLevel: 'low', agentTypes: ['Data Pipeline'], notes: 'Immutable backup mode. Source data is never modified, only copied.' },
  },
  {
    id: 'default-14', name: 'Research & Digest Bot',
    description: 'News aggregation and research summarization. Crawls, reads, and generates summaries. No write operations to external systems.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['web.search','web.browse','web.scrape','file.read','data.read','knowledge.search','report.generate','notes.create','notes.read'], blockedTools: ['email.send','file.write','db.write','shell.exec','code.deploy','user.modify','user.delete','finance.transfer','payment.process','api.post'], confirmActions: ['report.share','data.export','notes.update','api.call'], maxActionsPerHour: 1000, blockAfterHours: false, riskLevel: 'low', agentTypes: ['Digital','Browser','Data Pipeline'], notes: 'Market intelligence and competitive research. Output-only to internal knowledge base.' },
  },
  {
    id: 'default-15', name: 'Code Review Assistant',
    description: 'Automated code analysis and PR feedback. Reads repositories and generates review comments; no deployment or execution privileges.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['file.read','data.read','web.search','knowledge.search','report.generate','notes.create','api.call'], blockedTools: ['code.deploy','shell.admin','db.admin','user.delete','finance.transfer','system.shutdown','llm.finetune'], confirmActions: ['code.execute','shell.exec','file.write','api.post','data.write'], maxActionsPerHour: 800, blockAfterHours: false, riskLevel: 'low', agentTypes: ['Digital'], notes: 'GitHub/GitLab integration. PR comments auto-posted; merges always human-triggered.' },
  },
  {
    id: 'default-16', name: 'Inventory Management',
    description: 'Real-time inventory tracking and order management. DB reads and writes allowed for stock; financial transactions require approval.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['db.query','db.write','data.read','data.write','api.call','report.generate','email.read','user.lookup','notes.create','knowledge.search'], blockedTools: ['file.delete_bulk','db.admin','shell.exec','shell.admin','code.deploy','user.delete','system.shutdown'], confirmActions: ['finance.query','finance.transfer','payment.process','data.export','api.post','api.delete','user.modify'], maxActionsPerHour: 2000, blockAfterHours: false, riskLevel: 'medium', agentTypes: ['Digital','Data Pipeline'], notes: 'ERP integration mode. Purchase orders above threshold require CFO approval.' },
  },
  {
    id: 'default-17', name: 'Compliance Monitor',
    description: 'Continuous compliance monitoring and reporting. Fully read-only across all systems. Generates alerts and audit reports without modifying anything.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['data.read','db.query','file.read','api.call','report.generate','knowledge.search','user.lookup','notes.read','web.search'], blockedTools: ['data.write','db.write','db.admin','file.write','file.delete','email.send','api.post','api.delete','user.modify','user.delete','shell.exec','code.deploy','finance.transfer','system.admin'], confirmActions: ['report.share','data.export','notes.create'], maxActionsPerHour: 500, blockAfterHours: false, riskLevel: 'low', agentTypes: ['Digital','Data Pipeline'], notes: 'SOX/GDPR/HIPAA audit trail mode. Zero-write policy across all production systems.' },
  },
  {
    id: 'default-18', name: 'Robotics Lab Safety Protocol',
    description: 'Maximum safety for lab robots. Sensors and cameras allowed; all actuators, motion, and physical commands are blocked unless explicitly confirmed.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['sensor.read','camera.capture','data.read','communication.send','report.generate','notes.create'], blockedTools: ['shell.exec','shell.admin','code.deploy','finance.transfer','payment.process','user.delete','db.admin','system.shutdown'], confirmActions: ['navigation.move','navigation.plan','navigation.stop','flight.takeoff','flight.land','flight.waypoint','flight.abort','actuator.control','actuator.emergency_stop','motor.control','gripper.control','arm.move','arm.grasp','arm.release','sensor.configure','camera.stream','camera.record','communication.broadcast'], maxActionsPerHour: 100, blockAfterHours: true, riskLevel: 'high', agentTypes: ['Humanoid','Ground Robot','Drone'], notes: 'Research lab safety mode. Human supervisor must approve every physical action.' },
  },
  {
    id: 'default-19', name: 'Executive Assistant',
    description: 'High-trust personal assistant for executives. Calendar and email management with confirmations on all outbound communications.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['email.read','email.draft','calendar.read','calendar.write','task.create','task.update','notes.create','notes.read','notes.update','web.search','knowledge.search','user.lookup','report.generate'], blockedTools: ['file.delete_bulk','db.admin','shell.exec','code.deploy','user.delete','finance.transfer','payment.process','system.admin'], confirmActions: ['email.send','calendar.delete','task.delete','api.call','data.export','report.share','user.modify'], maxActionsPerHour: 400, blockAfterHours: false, riskLevel: 'medium', agentTypes: ['Digital','Voice'], notes: 'C-suite assistant. All external emails drafted and reviewed before sending.' },
  },
  {
    id: 'default-20', name: 'E-commerce Operations',
    description: 'Storefront and order management automation. Product catalog updates allowed; pricing changes, refunds, and bulk operations require approval.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['web.search','web.browse','data.read','db.query','api.call','email.read','email.draft','report.generate','task.create','notes.create','user.lookup','knowledge.search'], blockedTools: ['user.delete','db.admin','shell.exec','shell.admin','code.deploy','system.shutdown','llm.finetune'], confirmActions: ['payment.process','finance.transfer','finance.query','data.write','db.write','api.post','api.delete','email.send','data.export','user.modify'], maxActionsPerHour: 1500, blockAfterHours: false, riskLevel: 'medium', agentTypes: ['Digital','Data Pipeline'], notes: 'Shopify/WooCommerce integration. Payment and pricing changes require merchant sign-off.' },
  },
  {
    id: 'default-21', name: 'Content Creation Bot',
    description: 'AI writing and content generation assistant. Creates drafts freely; all publishing, file writes, and external shares require explicit approval.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['web.search','web.browse','web.scrape','knowledge.search','notes.create','notes.read','data.read','report.generate','calendar.read'], blockedTools: ['db.admin','shell.exec','code.deploy','user.delete','finance.transfer','payment.process','system.admin','system.shutdown'], confirmActions: ['file.write','file.delete','email.send','api.post','report.share','notes.update','data.export'], maxActionsPerHour: 600, blockAfterHours: false, riskLevel: 'low', agentTypes: ['Digital','Browser'], notes: 'Content marketing mode. Editorial team reviews all copy before publication.' },
  },
  {
    id: 'default-22', name: 'Network Security Monitor',
    description: 'Infrastructure monitoring and anomaly detection. Reads network telemetry and generates alerts; no configuration changes without approval.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['data.read','api.call','db.query','report.generate','knowledge.search','notes.create','web.search'], blockedTools: ['user.delete','finance.transfer','payment.process','llm.finetune','system.shutdown','file.delete_bulk'], confirmActions: ['system.admin','shell.exec','shell.admin','code.deploy','api.post','api.delete','db.write','user.modify','data.write'], maxActionsPerHour: 10000, blockAfterHours: false, riskLevel: 'medium', agentTypes: ['Digital'], notes: 'SOC operations mode. Incident response actions require on-call engineer approval.' },
  },
  {
    id: 'default-23', name: 'Inspection Drone',
    description: 'Autonomous inspection for infrastructure and facilities. Camera and sensor ops allowed; flight maneuvers and position changes require operator confirmation.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['sensor.read','camera.capture','camera.stream','camera.record','data.read','report.generate','communication.send','notes.create'], blockedTools: ['arm.move','arm.grasp','gripper.control','motor.control','shell.admin','code.deploy','user.delete','finance.transfer','db.admin'], confirmActions: ['flight.takeoff','flight.land','flight.waypoint','flight.abort','navigation.move','navigation.plan','actuator.control','actuator.emergency_stop','communication.broadcast','sensor.configure'], maxActionsPerHour: 3000, blockAfterHours: false, riskLevel: 'medium', agentTypes: ['Drone','Vision'], notes: 'FAA Part 107 compliance mode. BVLOS flights always require remote pilot approval.' },
  },
  {
    id: 'default-24', name: 'Data Migration Pipeline',
    description: 'Safe ETL and data migration workflows. Reads source systems freely; all writes to target systems are logged and deletions are fully blocked.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['db.query','data.read','data.export','file.read','api.call','report.generate','notes.create','knowledge.search'], blockedTools: ['file.delete','file.delete_bulk','db.admin','user.delete','system.shutdown','shell.admin','finance.transfer','payment.process'], confirmActions: ['db.write','data.write','api.post','file.write','user.modify','api.delete','db.query'], maxActionsPerHour: 5000, blockAfterHours: false, riskLevel: 'medium', agentTypes: ['Data Pipeline'], notes: 'Zero-delete migration policy. All transformations reversible; rollback scripts auto-generated.' },
  },
  {
    id: 'default-25', name: 'Voice Customer Service',
    description: 'Inbound voice support with CRM integration. Handles queries, updates tickets, and drafts follow-ups; all account changes require supervisor approval.',
    createdAt: '2025-01-01T00:00:00Z',
    rules: { allowedTools: ['email.read','email.draft','ticket.create','ticket.update','knowledge.search','user.lookup','notes.create','notes.read','calendar.read','data.read','report.generate'], blockedTools: ['finance.transfer','payment.process','user.delete','db.admin','shell.exec','code.deploy','system.admin','system.shutdown','file.delete_bulk'], confirmActions: ['email.send','ticket.close','user.modify','api.call','api.post','data.export'], maxActionsPerHour: 800, blockAfterHours: false, riskLevel: 'low', agentTypes: ['Voice','Digital'], notes: 'Contact center integration. Sensitive account actions escalate to live agent.' },
  },
];

/* ─────────────────────────────────────────────
   Main component
───────────────────────────────────────────── */
export default function Policies() {
  const [packs, setPacks] = useState<PolicyPackWithMeta[]>([]);
  const [activePolicy, setActivePolicy] = useState<string | null>(null);
  const [activating, setActivating] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [customPolicies, setCustomPolicies] = useState<CustomPolicy[]>([]);
  const [planName, setPlanName] = useState('pro');
  const { toast } = useToast();

  // Custom form state
  const [customName, setCustomName] = useState('');
  const [customDescription, setCustomDescription] = useState('');
  const [customNotes, setCustomNotes] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [rulesAllowedTools, setRulesAllowedTools] = useState<string[]>([]);
  const [rulesBlockedTools, setRulesBlockedTools] = useState<string[]>([]);
  const [rulesConfirmActions, setRulesConfirmActions] = useState<string[]>([]);
  const [rulesMaxActions, setRulesMaxActions] = useState(500);
  const [rulesBlockAfterHours, setRulesBlockAfterHours] = useState(false);
  const [rulesRiskLevel, setRulesRiskLevel] = useState<'low' | 'medium' | 'high'>('medium');
  const [rulesAgentTypes, setRulesAgentTypes] = useState<string[]>([]);

  // View Rules dialog
  const [viewRulesPack, setViewRulesPack] = useState<PolicyPackWithMeta | null>(null);
  const [viewRulesOpen, setViewRulesOpen] = useState(false);

  // Custom policy apply dialog
  const [applyCustomOpen, setApplyCustomOpen] = useState(false);
  const [applyCustomPolicy, setApplyCustomPolicy] = useState<CustomPolicy | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const plan = (localStorage.getItem(PLAN_KEY) || 'pro').toLowerCase();
    setPlanName(plan);
    const stored = localStorage.getItem(CUSTOM_POLICIES_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as CustomPolicy[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setCustomPolicies(parsed);
        } else {
          setCustomPolicies(DEFAULT_CUSTOM_POLICIES);
          localStorage.setItem(CUSTOM_POLICIES_KEY, JSON.stringify(DEFAULT_CUSTOM_POLICIES));
        }
      } catch { /* ignore */ }
    } else {
      setCustomPolicies(DEFAULT_CUSTOM_POLICIES);
      localStorage.setItem(CUSTOM_POLICIES_KEY, JSON.stringify(DEFAULT_CUSTOM_POLICIES));
    }
    const handleStorage = () => setPlanName((localStorage.getItem(PLAN_KEY) || 'pro').toLowerCase());
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  const customLimit = planName === 'starter' ? 25 : planName === 'growth' ? 50 : 100;
  const remainingCustom = Math.max(customLimit - customPolicies.length, 0);

  const persistCustomPolicies = (next: CustomPolicy[]) => {
    setCustomPolicies(next);
    if (typeof window !== 'undefined') localStorage.setItem(CUSTOM_POLICIES_KEY, JSON.stringify(next));
  };

  const resetCustomForm = () => {
    setCustomName(''); setCustomDescription(''); setCustomNotes('');
    setEditingId(null); setAdvancedOpen(false);
    setRulesAllowedTools([]); setRulesBlockedTools([]);
    setRulesConfirmActions([]); setRulesMaxActions(500);
    setRulesBlockAfterHours(false); setRulesRiskLevel('medium');
    setRulesAgentTypes([]);
  };

  const buildRules = (): CustomPolicyRules => ({
    allowedTools: rulesAllowedTools,
    blockedTools: rulesBlockedTools,
    confirmActions: rulesConfirmActions,
    maxActionsPerHour: rulesMaxActions,
    blockAfterHours: rulesBlockAfterHours,
    riskLevel: rulesRiskLevel,
    agentTypes: rulesAgentTypes,
    notes: customNotes,
  });

  const handleSaveCustom = () => {
    if (!customName.trim()) {
      toast({ title: 'Missing name', description: 'Add a policy name first.', variant: 'destructive' });
      return;
    }
    if (editingId) {
      persistCustomPolicies(customPolicies.map((p) =>
        p.id === editingId ? { ...p, name: customName.trim(), description: customDescription.trim(), rules: buildRules() } : p
      ));
      toast({ title: 'Custom policy updated' });
      resetCustomForm();
      return;
    }
    if (customPolicies.length >= customLimit) {
      toast({ title: 'Limit reached', description: `Max ${customLimit} custom policies on your plan.`, variant: 'destructive' });
      return;
    }
    persistCustomPolicies([{
      id: `custom-${Date.now()}`,
      name: customName.trim(),
      description: customDescription.trim() || 'Custom policy pack',
      createdAt: new Date().toISOString(),
      rules: buildRules(),
    }, ...customPolicies]);
    toast({ title: 'Custom policy created' });
    resetCustomForm();
  };

  const handleEditCustom = (policy: CustomPolicy) => {
    setCustomName(policy.name);
    setCustomDescription(policy.description);
    setEditingId(policy.id);
    if (policy.rules) {
      setRulesAllowedTools(policy.rules.allowedTools);
      setRulesBlockedTools(policy.rules.blockedTools);
      setRulesConfirmActions(policy.rules.confirmActions);
      setRulesMaxActions(policy.rules.maxActionsPerHour);
      setRulesBlockAfterHours(policy.rules.blockAfterHours);
      setRulesRiskLevel(policy.rules.riskLevel ?? 'medium');
      setRulesAgentTypes(policy.rules.agentTypes ?? []);
      setCustomNotes(policy.rules.notes ?? '');
      setAdvancedOpen(true);
    }
  };

  const handleRemoveCustom = (id: string) => {
    persistCustomPolicies(customPolicies.filter((p) => p.id !== id));
    toast({ title: 'Custom policy removed' });
    if (editingId === id) resetCustomForm();
  };

  // Build PolicyPackWithMeta list from the 6 real packs
  const buildBuiltinPacks = (): PolicyPackWithMeta[] =>
    Object.entries(PACK_META).map(([name, meta]) => ({
      name,
      description: meta.tagline,
      risk_level: name === 'casual_user' ? 'low'
        : name === 'market_analyst' ? 'low'
        : name === 'ops_commander' ? 'medium'
        : name === 'founder_mode' ? 'high'
        : name === 'helpdesk' ? 'medium'
        : 'very-high',
      scope_summary: { agents: 0 },
      constraints_summary: {
        allowed_tools: PACK_ALLOWED_TOOLS[name]?.length ?? 0,
        blocked_tools: PACK_BLOCKED_TOOLS[name]?.length ?? 0,
        confirm_required: (PACK_CONFIRM_ACTIONS[name]?.length ?? 0) > 0,
      },
      icon: meta.icon,
      color: meta.color,
      bgGradient: meta.bgGradient,
      borderColor: meta.borderColor,
    }));

  const fetchPacks = useCallback(async () => {
    if (isMockMode() || !getToken()) {
      setPacks(buildBuiltinPacks());
      setLoading(false);
      return;
    }
    try {
      const response = await edonApi.getPolicyPacks();
      const fromApi = Array.isArray(response) ? response : [];
      const apiNames = new Set(fromApi.map((p: PolicyPack) => p.name));
      const merged: PolicyPackWithMeta[] = buildBuiltinPacks().map((builtin) => {
        const apiMatch = fromApi.find((p: PolicyPack) => p.name === builtin.name);
        return apiMatch ? {
          ...builtin,
          description: apiMatch.description || builtin.description,
          constraints_summary: apiMatch.constraints_summary || builtin.constraints_summary,
        } : builtin;
      });
      fromApi.filter((p: PolicyPack) => !apiNames.has(p.name)).forEach((p: PolicyPack) => {
        merged.push({ ...p, icon: Shield, color: 'text-primary', bgGradient: 'from-primary/15 to-primary/5', borderColor: 'border-primary/30' });
      });
      setPacks(merged);
    } catch {
      setPacks(buildBuiltinPacks());
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchActivePolicy = useCallback(async () => {
    const saved = localStorage.getItem('edon_active_policy_pack') || localStorage.getItem('edon_policy_mode');
    if (saved) setActivePolicy(saved);
    if (isMockMode() || !getToken()) return;
    try {
      const h = await edonApi.getHealth();
      const preset = (h as { governor?: { active_preset?: { preset_name?: string } } })?.governor?.active_preset?.preset_name;
      if (preset) { setActivePolicy(preset); localStorage.setItem('edon_active_policy_pack', preset); }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchPacks(); fetchActivePolicy(); }, [fetchPacks, fetchActivePolicy]);

  const activatePolicy = async (packName: string) => {
    setActivating(packName);
    try {
      if (isMockMode() || !getToken()) {
        await new Promise((r) => setTimeout(r, 400));
        setActivePolicy(packName);
        localStorage.setItem('edon_active_policy_pack', packName);
        localStorage.setItem('edon_active_intent_id', `mock-intent-${packName}-${Date.now()}`);
        toast({ title: 'Safety Pack Applied', description: `${PACK_META[packName]?.label ?? packName} is now active` });
      } else {
        const response = await edonApi.applyPolicyPack(packName);
        setActivePolicy(packName);
        if (response?.intent_id) {
          localStorage.setItem('edon_active_policy_pack', packName);
          localStorage.setItem('edon_active_intent_id', response.intent_id);
        }
        toast({ title: 'Safety Pack Applied', description: response.message || `${packName} is now active` });
        await fetchActivePolicy();
      }
    } catch (e) {
      toast({ title: 'Failed to Apply', description: e instanceof Error ? e.message : 'Unknown error', variant: 'destructive' });
    } finally { setActivating(null); }
  };

  const getRiskColor = (level: string) => ({
    low: 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10',
    medium: 'border-amber-500/30 text-amber-400 bg-amber-500/10',
    high: 'border-red-500/30 text-red-400 bg-red-500/10',
    'very-high': 'border-red-600/40 text-red-300 bg-red-600/15',
  }[level] ?? 'border-white/20 text-muted-foreground');

  const AGENT_TYPES = ['Digital', 'Humanoid', 'Drone', 'Ground Robot', 'IoT', 'Vision', 'Voice', 'Browser', 'Data Pipeline'];

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <div className="space-y-8">

          {/* Header */}
          <div>
            <h1 className="text-2xl font-bold mb-1">Policies</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Choose a governance mode, explore all policy packs, or build custom policies for any agent type.
            </p>
          </div>

          {/* ── GOVERNANCE MODES ──────────────────────── */}
          <section>
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2 mb-4">
              <Shield className="w-4 h-4 text-primary" /> Governance Mode
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              {GOVERNANCE_MODES.map((mode) => {
                const Icon = mode.icon;
                const isActive = activePolicy === mode.packName;
                return (
                  <motion.div
                    key={mode.key}
                    initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                    className={`glass-card-hover ${mode.border} ${isActive ? 'ring-2 ring-primary' : ''}`}
                  >
                    <div className={`absolute inset-0 bg-gradient-to-br ${mode.gradient} opacity-30 pointer-events-none`} />
                    <div className="relative z-10 p-5">
                      <div className="flex items-start justify-between gap-3 mb-4">
                        <div className="p-2.5 rounded-lg bg-white/10"><Icon className="w-5 h-5" /></div>
                        {isActive && <Badge className="bg-primary/20 text-primary border-primary/30 text-xs"><Check className="w-3 h-3 mr-1" />Active</Badge>}
                      </div>
                      <h3 className="text-base font-semibold mb-3">{mode.title}</h3>
                      <dl className="space-y-2 text-xs text-muted-foreground mb-5">
                        {[['What it does', mode.what], ['Scope', mode.scope], ['Escalation', mode.escalation], ['Use case', mode.useCase]].map(([dt, dd]) => (
                          <div key={dt}>
                            <dt className="text-[10px] uppercase tracking-wider text-foreground/60 mb-0.5">{dt}</dt>
                            <dd className="leading-relaxed">{dd}</dd>
                          </div>
                        ))}
                      </dl>
                      <Button
                        onClick={() => activatePolicy(mode.packName)}
                        disabled={isActive || activating === mode.packName}
                        className="w-full gap-2 text-xs"
                        variant={isActive ? 'outline' : 'default'}
                      >
                        {activating === mode.packName ? (
                          <><div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />Applying...</>
                        ) : isActive ? (
                          <><Check className="w-3.5 h-3.5" />Currently Active</>
                        ) : (
                          <>Set {mode.title}<ChevronRight className="w-3.5 h-3.5" /></>
                        )}
                      </Button>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </section>

          {/* ── CURRENT POLICY BANNER ─────────────────── */}
          <div className="glass-card p-5 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-3 rounded-xl bg-primary/15">
                <ShieldCheck className="w-5 h-5 text-primary" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Active Safety Pack</p>
                <p className="text-lg font-semibold">
                  {activePolicy
                    ? (PACK_META[activePolicy]?.label ?? activePolicy.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase()))
                    : 'None — select a mode above'}
                </p>
                {activePolicy && PACK_META[activePolicy] && (
                  <p className="text-xs text-muted-foreground mt-0.5">{PACK_META[activePolicy].tagline}</p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => { fetchPacks(); fetchActivePolicy(); }} disabled={loading}>
                <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </Button>
              {activePolicy && <Badge className="bg-primary/20 text-primary border-primary/30">Active</Badge>}
            </div>
          </div>

          {/* ── POLICY PACKS GRID ─────────────────────── */}
          <section>
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2 mb-1">
              <ShieldCheck className="w-4 h-4 text-primary" /> Policy Packs
            </h2>
            <p className="text-xs text-muted-foreground mb-5">
              All built-in packs. Each defines exactly which tools are allowed, blocked, and require confirmation — plus rate limits and after-hours rules.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {(packs.length > 0 ? packs : buildBuiltinPacks()).filter((p) => ['casual_user','ops_commander','autonomy_mode'].includes(p.name)).map((pack, i) => {
                const Icon = pack.icon;
                const meta = PACK_META[pack.name];
                const isActive = activePolicy === pack.name;
                const allowed = PACK_ALLOWED_TOOLS[pack.name] ?? [];
                const blocked = PACK_BLOCKED_TOOLS[pack.name] ?? [];
                const confirm = PACK_CONFIRM_ACTIONS[pack.name] ?? [];
                const maxHr = PACK_MAX_PER_HOUR[pack.name];
                const afterHrs = PACK_AFTER_HOURS_BLOCK[pack.name];
                return (
                  <motion.div
                    key={pack.name}
                    initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className={`glass-card-hover ${pack.borderColor ?? 'border-white/10'} ${isActive ? 'ring-2 ring-primary/60' : ''}`}
                  >
                    <div className={`h-0.5 w-full bg-gradient-to-r ${pack.bgGradient?.replace('from-', 'from-').replace('/15', '/60').replace('/5', '/40') ?? ''}`} />
                    <div className="p-4">
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center gap-2.5">
                          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${pack.bgGradient ? `bg-gradient-to-br ${pack.bgGradient}` : 'bg-white/5'} border ${pack.borderColor ?? 'border-white/10'}`}>
                            <Icon className={`w-4 h-4 ${pack.color}`} />
                          </div>
                          <div>
                            <p className="text-sm font-semibold leading-tight">{meta?.label ?? pack.name}</p>
                            <p className={`text-[10px] font-mono ${pack.color}`}>{pack.name}</p>
                          </div>
                        </div>
                        <Badge variant="outline" className={`text-[10px] ${getRiskColor(pack.risk_level)}`}>
                          {pack.risk_level}
                        </Badge>
                      </div>

                      <p className="text-xs text-muted-foreground leading-relaxed mb-3">{pack.description}</p>

                      {/* Stats row */}
                      <div className="grid grid-cols-3 gap-2 mb-3">
                        <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-2 py-1.5 text-center">
                          <p className="text-sm font-bold text-emerald-400">{allowed.length}</p>
                          <p className="text-[9px] text-emerald-400/70 uppercase tracking-wide">Allowed</p>
                        </div>
                        <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-2 py-1.5 text-center">
                          <p className="text-sm font-bold text-red-400">{blocked.length}</p>
                          <p className="text-[9px] text-red-400/70 uppercase tracking-wide">Blocked</p>
                        </div>
                        <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 px-2 py-1.5 text-center">
                          <p className="text-sm font-bold text-amber-400">{confirm.length}</p>
                          <p className="text-[9px] text-amber-400/70 uppercase tracking-wide">Confirm</p>
                        </div>
                      </div>

                      {/* Rate limit + after hours */}
                      <div className="flex flex-wrap gap-1.5 mb-3">
                        {maxHr && (
                          <Badge variant="outline" className="text-[10px] border-white/15 text-muted-foreground">
                            {maxHr.toLocaleString()}/hr max
                          </Badge>
                        )}
                        {afterHrs && (
                          <Badge variant="outline" className="text-[10px] border-amber-500/25 text-amber-400/80">
                            blocks after hours
                          </Badge>
                        )}
                      </div>

                      {/* Agent types */}
                      {meta?.agentTypes && (
                        <div className="flex flex-wrap gap-1 mb-3">
                          {meta.agentTypes.map((t) => (
                            <span key={t} className="text-[9px] px-1.5 py-0.5 rounded-full border border-white/10 text-muted-foreground/60">{t}</span>
                          ))}
                        </div>
                      )}

                      {/* Actions */}
                      <div className="flex gap-2 pt-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="flex-1 h-7 text-xs border border-white/10"
                          onClick={() => { setViewRulesPack(pack); setViewRulesOpen(true); }}
                        >
                          View Rules
                        </Button>
                        <Button
                          size="sm"
                          className="flex-1 h-7 text-xs"
                          disabled={isActive || activating === pack.name}
                          variant={isActive ? 'outline' : 'default'}
                          onClick={() => activatePolicy(pack.name)}
                        >
                          {activating === pack.name ? (
                            <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                          ) : isActive ? (
                            <><Check className="w-3 h-3 mr-1" />Active</>
                          ) : 'Apply Pack'}
                        </Button>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </section>

          {/* ── CUSTOM POLICIES ───────────────────────── */}
          <section>

            {/* Section header */}
            <div className="flex items-center justify-between gap-4 mb-4">
              <div>
                <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <Plus className="w-4 h-4 text-primary" /> Custom Policies
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Define allowed/blocked tools, confirmation requirements, rate limits, and agent-type scoping per pack.
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Badge className="bg-primary/20 text-primary border-primary/30 text-xs">
                  {customPolicies.length}/{customLimit} used
                </Badge>
                <Button
                  size="sm" variant="outline"
                  className="gap-1.5 text-xs h-8 border-white/10"
                  onClick={() => { resetCustomForm(); setAdvancedOpen(true); }}
                >
                  <Plus className="w-3.5 h-3.5" /> New Policy
                </Button>
              </div>
            </div>

            {/* Builder form — shown when composing or editing */}
            {(advancedOpen || editingId) && (
              <div className="glass-card p-5 mb-6">
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-4">
                  {editingId ? 'Edit Policy' : 'New Custom Policy'}
                </p>
                <div className="grid md:grid-cols-2 gap-4 mb-4">
                  <div className="space-y-1.5">
                    <label className="text-[10px] uppercase tracking-widest text-muted-foreground">Pack Name *</label>
                    <Input
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                      placeholder="e.g. Drone Safe Ops"
                      className="bg-secondary/50 text-sm"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[10px] uppercase tracking-widest text-muted-foreground">Risk Level</label>
                    <div className="flex gap-1.5">
                      {(['low', 'medium', 'high'] as const).map((r) => (
                        <button
                          key={r}
                          onClick={() => setRulesRiskLevel(r)}
                          className={`flex-1 rounded-lg border py-1.5 text-[10px] font-medium capitalize transition-colors ${
                            rulesRiskLevel === r ? getRiskColor(r) : 'border-white/10 text-muted-foreground hover:bg-white/5'
                          }`}
                        >
                          {r}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="space-y-1.5 mb-4">
                  <label className="text-[10px] uppercase tracking-widest text-muted-foreground">Description</label>
                  <Textarea
                    value={customDescription}
                    onChange={(e) => setCustomDescription(e.target.value)}
                    placeholder="What does this policy allow/block and why?"
                    className="bg-secondary/50 min-h-[60px] text-sm"
                  />
                </div>

                <div className="space-y-1.5 mb-4">
                  <label className="text-[10px] uppercase tracking-widest text-muted-foreground">Apply to agent types</label>
                  <div className="flex flex-wrap gap-1.5">
                    {AGENT_TYPES.map((t) => (
                      <button
                        key={t}
                        onClick={() => setRulesAgentTypes((prev) =>
                          prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]
                        )}
                        className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                          rulesAgentTypes.includes(t)
                            ? 'border-[#64dc78]/40 bg-[#64dc78]/10 text-[#64dc78]'
                            : 'border-white/10 bg-white/5 text-muted-foreground hover:text-foreground'
                        }`}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Advanced rules */}
                <div className="rounded-xl border border-white/10 overflow-hidden mb-4">
                  <button
                    type="button"
                    onClick={() => setAdvancedOpen((v) => !v)}
                    className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium hover:bg-white/5 transition-colors"
                  >
                    <span className="flex items-center gap-2">
                      <ShieldAlert className="w-4 h-4 text-muted-foreground" />
                      Advanced Rules
                      {(rulesAllowedTools.length + rulesBlockedTools.length + rulesConfirmActions.length) > 0 && (
                        <Badge variant="outline" className="text-[10px] border-primary/30 text-primary">
                          {rulesAllowedTools.length + rulesBlockedTools.length + rulesConfirmActions.length} rules defined
                        </Badge>
                      )}
                    </span>
                    <ChevronDown className={`h-4 w-4 transition-transform ${advancedOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {advancedOpen && (
                    <div className="px-4 pb-5 pt-1 border-t border-white/10 space-y-5">
                      <ToolPicker selected={rulesAllowedTools} onChange={setRulesAllowedTools} label="Allowed Tools" accentClass="border-emerald-500/30 text-emerald-400 bg-emerald-500/10" />
                      <ToolPicker selected={rulesBlockedTools} onChange={setRulesBlockedTools} label="Blocked Tools" accentClass="border-red-500/30 text-red-400 bg-red-500/10" />
                      <div className="space-y-2">
                        <Label className="text-xs text-muted-foreground">Require human confirmation for</Label>
                        <div className="grid grid-cols-2 gap-1.5 max-h-48 overflow-y-auto rounded-lg border border-white/10 bg-white/[0.02] p-2">
                          {CONFIRM_OPTIONS.map((opt) => (
                            <label key={opt} className="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-white/5 cursor-pointer">
                              <Checkbox checked={rulesConfirmActions.includes(opt)} onCheckedChange={(v) => setRulesConfirmActions((prev) => v ? [...prev, opt] : prev.filter((a) => a !== opt))} className="w-3 h-3" />
                              <span className="text-[10px] font-mono text-muted-foreground">{opt}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">Max actions per hour</Label>
                          <Input type="number" value={rulesMaxActions} onChange={(e) => setRulesMaxActions(Number(e.target.value))} min={1} max={100000} className="bg-secondary/50 text-sm" />
                        </div>
                        <div className="flex items-end pb-1">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <Checkbox checked={rulesBlockAfterHours} onCheckedChange={(v) => setRulesBlockAfterHours(!!v)} />
                            <span className="text-xs">Block after business hours</span>
                          </label>
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">Internal notes</Label>
                        <Textarea value={customNotes} onChange={(e) => setCustomNotes(e.target.value)} placeholder="Context, compliance requirements, approval details..." className="bg-secondary/50 text-xs min-h-[60px]" />
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button onClick={handleSaveCustom} disabled={customPolicies.length >= customLimit && !editingId} className="gap-2">
                    {editingId ? 'Update Policy' : 'Create Policy'}
                  </Button>
                  <Button variant="ghost" onClick={() => { resetCustomForm(); setAdvancedOpen(false); }}>Cancel</Button>
                  <span className="text-xs text-muted-foreground self-center">{remainingCustom} slot{remainingCustom !== 1 ? 's' : ''} remaining</span>
                </div>
              </div>
            )}

            {/* Policies grid — 3 columns */}
            {customPolicies.length === 0 ? (
              <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center">
                <ShieldCheck className="w-8 h-8 text-muted-foreground/30 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No custom policies yet</p>
                <p className="text-xs text-muted-foreground/60 mt-1">Click "New Policy" to create your first pack</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {customPolicies.map((policy) => (
                  <div
                    key={policy.id}
                    className={`glass-card-hover p-4 flex flex-col ${
                      editingId === policy.id ? 'border-primary/50 ring-1 ring-primary/30' : ''
                    }`}
                  >
                    {/* Name + risk */}
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <p className="text-sm font-semibold leading-snug flex-1">{policy.name}</p>
                      {policy.rules?.riskLevel && (
                        <Badge variant="outline" className={`text-[9px] shrink-0 ${getRiskColor(policy.rules.riskLevel)}`}>
                          {policy.rules.riskLevel}
                        </Badge>
                      )}
                    </div>

                    {/* Description */}
                    <p className="text-[11px] text-muted-foreground leading-relaxed mb-3 flex-1 line-clamp-3">
                      {policy.description}
                    </p>

                    {/* Stats row */}
                    {policy.rules && (
                      <div className="grid grid-cols-3 gap-1.5 mb-3">
                        <div className="rounded-md bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-1 text-center">
                          <p className="text-xs font-bold text-emerald-400">{policy.rules.allowedTools.length}</p>
                          <p className="text-[8px] text-emerald-400/70 uppercase tracking-wide">Allow</p>
                        </div>
                        <div className="rounded-md bg-red-500/10 border border-red-500/20 px-1.5 py-1 text-center">
                          <p className="text-xs font-bold text-red-400">{policy.rules.blockedTools.length}</p>
                          <p className="text-[8px] text-red-400/70 uppercase tracking-wide">Block</p>
                        </div>
                        <div className="rounded-md bg-amber-500/10 border border-amber-500/20 px-1.5 py-1 text-center">
                          <p className="text-xs font-bold text-amber-400">{policy.rules.confirmActions.length}</p>
                          <p className="text-[8px] text-amber-400/70 uppercase tracking-wide">Confirm</p>
                        </div>
                      </div>
                    )}

                    {/* Agent type chips */}
                    {policy.rules?.agentTypes && policy.rules.agentTypes.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-3">
                        {policy.rules.agentTypes.map((t) => (
                          <span key={t} className="text-[9px] px-1.5 py-0.5 rounded-full border border-[#64dc78]/20 text-[#64dc78]/70">{t}</span>
                        ))}
                      </div>
                    )}

                    {/* Meta badges */}
                    <div className="flex flex-wrap gap-1 mb-3">
                      {policy.rules?.maxActionsPerHour && policy.rules.maxActionsPerHour !== 500 && (
                        <Badge variant="outline" className="text-[9px] border-white/15 text-muted-foreground">
                          {policy.rules.maxActionsPerHour.toLocaleString()}/hr
                        </Badge>
                      )}
                      {policy.rules?.blockAfterHours && (
                        <Badge variant="outline" className="text-[9px] border-amber-500/20 text-amber-400/80">after hrs ✕</Badge>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1.5 pt-2 border-t border-white/5 mt-auto">
                      <Button size="sm" variant="default" className="h-7 text-xs flex-1"
                        onClick={() => { setApplyCustomPolicy(policy); setApplyCustomOpen(true); }}>
                        Apply
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 text-xs px-2.5" onClick={() => handleEditCustom(policy)}>
                        Edit
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 text-xs px-2 text-red-400 hover:text-red-400 hover:bg-red-500/10" onClick={() => handleRemoveCustom(policy.id)}>
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
          </div>

        </motion.div>
      </main>

      {/* ── VIEW RULES DIALOG ─────────────────────── */}
      <Dialog open={viewRulesOpen} onOpenChange={setViewRulesOpen}>
        <DialogContent className="glass-card border-white/10 max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3 text-base">
              {viewRulesPack && (() => {
                const Icon = viewRulesPack.icon;
                return <Icon className={`w-5 h-5 ${viewRulesPack.color}`} />;
              })()}
              {viewRulesPack ? (PACK_META[viewRulesPack.name]?.label ?? viewRulesPack.name) : ''}
              {viewRulesPack && (
                <Badge variant="outline" className={`text-xs ${getRiskColor(viewRulesPack.risk_level)}`}>
                  {viewRulesPack.risk_level} risk
                </Badge>
              )}
            </DialogTitle>
          </DialogHeader>

          {viewRulesPack && (
            <ScrollArea className="max-h-[520px]">
              <div className="space-y-5 pr-2">
                <p className="text-sm text-muted-foreground">{viewRulesPack.description}</p>

                {/* Stats */}
                <div className="grid grid-cols-4 gap-2">
                  {[
                    { label: 'Allowed', val: PACK_ALLOWED_TOOLS[viewRulesPack.name]?.length ?? 0, cls: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' },
                    { label: 'Blocked', val: PACK_BLOCKED_TOOLS[viewRulesPack.name]?.length ?? 0, cls: 'bg-red-500/10 border-red-500/20 text-red-400' },
                    { label: 'Confirm', val: PACK_CONFIRM_ACTIONS[viewRulesPack.name]?.length ?? 0, cls: 'bg-amber-500/10 border-amber-500/20 text-amber-400' },
                    { label: 'Max/hr', val: PACK_MAX_PER_HOUR[viewRulesPack.name] ?? '—', cls: 'bg-white/5 border-white/10 text-foreground' },
                  ].map((s) => (
                    <div key={s.label} className={`rounded-lg border px-3 py-2 text-center ${s.cls}`}>
                      <p className="text-lg font-bold">{s.val}</p>
                      <p className="text-[9px] uppercase tracking-wide opacity-70">{s.label}</p>
                    </div>
                  ))}
                </div>

                {/* Allowed tools */}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                    <span className="w-2 h-2 bg-emerald-500 rounded-full" /> Allowed Tools
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {(PACK_ALLOWED_TOOLS[viewRulesPack.name] ?? []).map((tool) => (
                      <Badge key={tool} variant="outline" className="text-xs font-mono border-emerald-500/30 text-emerald-400 bg-emerald-500/10">{tool}</Badge>
                    ))}
                    {(PACK_ALLOWED_TOOLS[viewRulesPack.name] ?? []).length === 0 && <span className="text-xs text-muted-foreground">No tools defined</span>}
                  </div>
                </div>

                {/* Blocked tools */}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                    <span className="w-2 h-2 bg-red-500 rounded-full" /> Blocked Tools
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {(PACK_BLOCKED_TOOLS[viewRulesPack.name] ?? []).map((tool) => (
                      <Badge key={tool} variant="outline" className="text-xs font-mono border-red-500/30 text-red-400 bg-red-500/10">
                        <X className="h-2.5 w-2.5 mr-1" />{tool}
                      </Badge>
                    ))}
                  </div>
                </div>

                {/* Confirmation required */}
                {(PACK_CONFIRM_ACTIONS[viewRulesPack.name] ?? []).length > 0 && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                      <span className="w-2 h-2 bg-amber-500 rounded-full" /> Requires Human Confirmation
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {(PACK_CONFIRM_ACTIONS[viewRulesPack.name] ?? []).map((tool) => (
                        <Badge key={tool} variant="outline" className="text-xs font-mono border-amber-500/30 text-amber-400 bg-amber-500/10">{tool}</Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Rate limits */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">Rate Limit</p>
                    <p className="text-sm font-semibold">{(PACK_MAX_PER_HOUR[viewRulesPack.name] ?? 0).toLocaleString()} actions/hr</p>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">After Hours</p>
                    <p className={`text-sm font-semibold ${PACK_AFTER_HOURS_BLOCK[viewRulesPack.name] ? 'text-amber-400' : 'text-emerald-400'}`}>
                      {PACK_AFTER_HOURS_BLOCK[viewRulesPack.name] ? 'Blocked' : 'Allowed'}
                    </p>
                  </div>
                </div>

                {/* Agent types */}
                {PACK_META[viewRulesPack.name]?.agentTypes && (
                  <div>
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-2">Designed for</p>
                    <div className="flex flex-wrap gap-1.5">
                      {PACK_META[viewRulesPack.name].agentTypes.map((t) => (
                        <Badge key={t} variant="outline" className="text-xs border-[#64dc78]/25 text-[#64dc78]/80">{t}</Badge>
                      ))}
                    </div>
                  </div>
                )}

                <Button
                  onClick={() => { activatePolicy(viewRulesPack.name); setViewRulesOpen(false); }}
                  disabled={activePolicy === viewRulesPack.name || activating === viewRulesPack.name}
                  className="w-full gap-2"
                  variant={activePolicy === viewRulesPack.name ? 'outline' : 'default'}
                >
                  {activePolicy === viewRulesPack.name
                    ? <><Check className="w-4 h-4" />Currently Active</>
                    : <>Apply Pack<ChevronRight className="w-4 h-4" /></>
                  }
                </Button>
              </div>
            </ScrollArea>
          )}
        </DialogContent>
      </Dialog>

      {/* ── APPLY CUSTOM POLICY DIALOG ────────────── */}
      <Dialog open={applyCustomOpen} onOpenChange={setApplyCustomOpen}>
        <DialogContent className="glass-card border-white/10 max-w-sm">
          <DialogHeader>
            <DialogTitle>Apply Custom Policy</DialogTitle>
          </DialogHeader>
          {applyCustomPolicy && (
            <div className="space-y-4">
              <div className="rounded-lg border border-white/10 bg-white/5 p-3">
                <p className="text-sm font-medium">{applyCustomPolicy.name}</p>
                <p className="text-xs text-muted-foreground mt-1">{applyCustomPolicy.description}</p>
                {applyCustomPolicy.rules && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {applyCustomPolicy.rules.allowedTools.length > 0 && (
                      <Badge variant="outline" className="text-[10px] border-emerald-500/30 text-emerald-400">{applyCustomPolicy.rules.allowedTools.length} allowed</Badge>
                    )}
                    {applyCustomPolicy.rules.blockedTools.length > 0 && (
                      <Badge variant="outline" className="text-[10px] border-red-500/30 text-red-400">{applyCustomPolicy.rules.blockedTools.length} blocked</Badge>
                    )}
                  </div>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                Custom policies are stored locally. EDON will use these rules for decisions when this pack is active. For full gateway enforcement, configure via the API or contact your admin.
              </p>
              <div className="flex gap-2">
                <Button
                  className="flex-1"
                  onClick={() => {
                    localStorage.setItem('edon_active_policy_pack', applyCustomPolicy.name);
                    localStorage.setItem('edon_active_intent_id', `custom-intent-${Date.now()}`);
                    setActivePolicy(applyCustomPolicy.name);
                    setApplyCustomOpen(false);
                    toast({ title: 'Custom policy activated', description: `${applyCustomPolicy.name} is now active` });
                  }}
                >
                  Activate Policy
                </Button>
                <Button variant="outline" onClick={() => setApplyCustomOpen(false)}>Cancel</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
