import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Truck, Package, Globe, Navigation, Warehouse, BarChart3,
  MapPin, DollarSign, Activity, AlertTriangle, Users, Headphones,
  Shield, CheckCircle, XCircle, Clock, ChevronRight, Search,
  Download, RefreshCw, Lock, Eye, EyeOff, Sun, Moon,
  Send, Bot, Layers, Zap, TrendingUp, Copy,
  MessageSquare, LogOut, Building2, Anchor,
  LayoutList, LayoutGrid, Share2, X, ChevronLeft, Plus, CheckCircle2
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

type Verdict = 'ALLOW' | 'BLOCK' | 'ESCALATE'
type DeptKey =
  | 'routing' | 'dispatch' | 'customs' | 'warehouse' | 'tracking'
  | 'forecasting' | 'lastmile' | 'freight' | 'hub' | 'supplychain'
  | 'anomaly' | 'customer'

interface LogisticsEvent {
  id: string
  verdict: Verdict
  agent: string
  department: DeptKey
  deptLabel: string
  toolOp: string
  reasonCode: string
  latencyMs: number
  ts: Date
  hash: string
  riskScore: number
  shipmentId: string
  intentId: string
  policyVersion: string
  explanation: string
  vendorId: string
  vendorName: string
  vehicleId: string
  vehicleName: string
  operationalContext: string
  priority: 'routine' | 'urgent' | 'critical'
  reviewStatus?: 'pending' | 'approved' | 'rejected'
}

interface Agent {
  id: string
  name: string
  department: DeptKey
  deptLabel: string
  status: 'active' | 'idle' | 'alert'
  decisions24h: number
  blocked24h: number
  blockRate: number
  blockRatePrev: number
  blockRateTrend: 'stable' | 'rising' | 'spiked'
  avgLatency: number
  vendor: string
  zone: string
  shipmentLoad: number
  lastAction: string
  lastActiveMin: number
  lastSeen: Date
  policyVersion: string
  riskLevel: 'low' | 'medium' | 'high'
}

interface SharedAuditRecord {
  id: string
  recordId: string
  summary: { toolOp: string; verdict: Verdict; ts: string }
  sharedBy: string
  sharedWith: string[]
  note: string
  sharedAt: string
}

interface CrossAgentChain {
  id: string
  title: string
  shipmentId: string
  severity: 'info' | 'warning' | 'critical'
  events: { agent: string; dept: DeptKey; action: string; verdict: Verdict; ts: Date }[]
  summary: string
  resolved: boolean
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  ts: Date
}

// ─── Seeded RNG ───────────────────────────────────────────────────────────────

function mulberry32(seed: number) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed)
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t
    return ((t ^ t >>> 14) >>> 0) / 4294967296
  }
}

const rng = mulberry32(20240315)
const pick = <T,>(arr: T[]) => arr[Math.floor(rng() * arr.length)]
const rand = (min: number, max: number) => min + Math.floor(rng() * (max - min + 1))
const randF = (min: number, max: number) => min + rng() * (max - min)

// ─── Department Config ────────────────────────────────────────────────────────

const DEPTS: Record<DeptKey, { label: string; color: string; agentCount: number; icon: string }> = {
  routing:     { label: 'Route Optimization',   color: 'amber',   agentCount: 50,  icon: '🗺️' },
  dispatch:    { label: 'Fleet Dispatch',        color: 'orange',  agentCount: 42,  icon: '🚛' },
  customs:     { label: 'Customs & Trade',       color: 'blue',    agentCount: 35,  icon: '🌐' },
  warehouse:   { label: 'Warehouse Ops',         color: 'purple',  agentCount: 65,  icon: '🏭' },
  tracking:    { label: 'Package Tracking',      color: 'emerald', agentCount: 80,  icon: '📦' },
  forecasting: { label: 'Demand Forecasting',    color: 'sky',     agentCount: 30,  icon: '📈' },
  lastmile:    { label: 'Last Mile Delivery',    color: 'pink',    agentCount: 55,  icon: '🏠' },
  freight:     { label: 'Freight Pricing',       color: 'violet',  agentCount: 28,  icon: '💰' },
  hub:         { label: 'Hub Operations',        color: 'teal',    agentCount: 45,  icon: '⚙️' },
  supplychain: { label: 'Supply Chain',          color: 'cyan',    agentCount: 38,  icon: '⛓️' },
  anomaly:     { label: 'Anomaly Detection',     color: 'red',     agentCount: 32,  icon: '🔍' },
  customer:    { label: 'Customer Resolution',   color: 'indigo',  agentCount: 40,  icon: '🎧' },
}

// ─── Agent Names ──────────────────────────────────────────────────────────────

const AGENT_NAMES: Record<DeptKey, string[]> = {
  routing: ['PathFinder-7', 'RouteAI-3', 'OptimAI-12', 'TrafficBot-5', 'GeoRoute-9', 'NavCore-2', 'ZoneMapper-4', 'EtaCalc-8'],
  dispatch: ['FleetBot-1', 'DispatchAI-6', 'VehicleOps-3', 'DriveCore-11', 'AssignBot-4', 'LoadOpt-7', 'DockAgent-2', 'ShiftAI-9'],
  customs: ['TradeClear-3', 'TariffBot-1', 'BorderAI-5', 'CompliBot-2', 'HSCodeBot-4', 'SanctionAI-6', 'BrokerBot-7', 'ManiBot-8'],
  warehouse: ['SortBot-Alpha', 'PickAI-3', 'ConveyorOps-7', 'DockSched-2', 'InvBot-5', 'LabelAI-9', 'SlotBot-4', 'LoadDock-6'],
  tracking: ['ScanBot-Prime', 'TrackAI-2', 'ETABot-7', 'SigReq-3', 'DelivBot-5', 'PODAgent-1', 'AddrVerify-4', 'AlertTrack-8'],
  forecasting: ['DemandAI-1', 'SurgeBot-3', 'SeasonalOps-2', 'CapPlan-5', 'WeatherAI-4', 'VolBot-6', 'TrendAI-7', 'ModelBot-8'],
  lastmile: ['RouteBot-LM1', 'AttemptAI-3', 'LockerOps-2', 'NotifyBot-5', 'ReturnAI-4', 'GeoDeliv-7', 'StopOpt-6', 'AccessBot-8'],
  freight: ['RateBot-1', 'SurchargeAI-3', 'TariffCalc-2', 'InvoiceBot-5', 'ContractAI-4', 'ZoneRate-6', 'QuoteBot-7', 'PriceOpt-8'],
  hub: ['SortPlan-Alpha', 'InboundAI-2', 'ConveyMon-5', 'DockAssign-3', 'ShiftBot-7', 'ThroughBot-4', 'HubOps-6', 'GateBot-1'],
  supplychain: ['SupplierAI-1', 'ProcureBot-3', 'LeadTime-2', 'ReplenAI-5', 'VendorMon-4', 'ChainBot-6', 'StockAI-7', 'SourcBot-8'],
  anomaly: ['FraudScan-1', 'PatternAI-3', 'RiskFlag-2', 'AlertBot-5', 'BaselineAI-4', 'TheftDet-6', 'AnomaBot-7', 'ClusterAI-8'],
  customer: ['ClaimBot-1', 'RefundAI-3', 'TicketBot-2', 'NotifyAI-5', 'EscalBot-4', 'ResolvAI-6', 'CompBot-7', 'LegalBot-8'],
}

const VENDORS = [
  { id: 'VND-AT', name: 'AtlasAI Systems' },
  { id: 'VND-RX', name: 'Robo-Express' },
  { id: 'VND-CP', name: 'ClearPath AI' },
  { id: 'VND-HB', name: 'HubBot Labs' },
  { id: 'VND-NV', name: 'NavCore AI' },
  { id: 'VND-LM', name: 'LastMile Tech' },
  { id: 'VND-OR', name: 'OpsRouter AI' },
]

const VEHICLE_TYPES = [
  { id: 'VEH-TRK', name: '18-Wheeler' },
  { id: 'VEH-VAN', name: 'Delivery Van' },
  { id: 'VEH-AIR', name: 'Air Cargo' },
  { id: 'VEH-FCK', name: 'Forklift Unit' },
  { id: 'VEH-CON', name: 'Conveyor Sys' },
  { id: 'VEH-DRN', name: 'Cargo Drone' },
  { id: 'VEH-RBT', name: 'Warehouse Bot' },
]

// ─── Operations ───────────────────────────────────────────────────────────────

const DEPT_OPS: Record<DeptKey, { allow: string[]; block: string[]; escalate: string[] }> = {
  routing: {
    allow:   ['route.plan.generate', 'traffic.data.query', 'eta.recalculate', 'zone.coverage.check', 'driver.match.query'],
    block:   ['route.bulk.override.unauth', 'routing.data.export.external', 'rate.competitor.scrape'],
    escalate:['route.emergency.reroute.critical', 'hub.overflow.declare'],
  },
  dispatch: {
    allow:   ['vehicle.status.read', 'driver.assignment.read', 'load.manifest.verify', 'fuel.level.check', 'depart.schedule.view'],
    block:   ['fleet.dispatch.override.unauth', 'driver.hours.falsify', 'vehicle.safety.bypass'],
    escalate:['vehicle.emergency.alert', 'fleet.mass.reroute.request'],
  },
  customs: {
    allow:   ['customs.docs.verify', 'tariff.lookup', 'hs.code.check', 'country.restriction.query', 'broker.notify'],
    block:   ['customs.docs.auto.approve.suspicious', 'sanctions.check.bypass', 'tariff.value.underreport'],
    escalate:['customs.hold.release.highvalue', 'import.restriction.override.request'],
  },
  warehouse: {
    allow:   ['inventory.read', 'pick.task.assign', 'sort.conveyor.status', 'dock.schedule.view', 'label.print.request'],
    block:   ['inventory.count.override.unauth', 'warehouse.data.bulk.export', 'safety.lockout.bypass'],
    escalate:['warehouse.lockdown.request', 'hazmat.incident.declare'],
  },
  tracking: {
    allow:   ['package.status.read', 'delivery.eta.query', 'scan.event.log', 'proof.of.delivery.request', 'address.verify'],
    block:   ['tracking.data.bulk.export', 'delivery.location.spoof', 'signature.falsify'],
    escalate:['package.missing.critical.alert', 'chain.of.custody.break.declare'],
  },
  forecasting: {
    allow:   ['demand.forecast.query', 'seasonal.model.run', 'capacity.plan.read', 'weather.impact.assess', 'volume.trend.analyze'],
    block:   ['forecast.data.share.external', 'model.parameters.override.unauth', 'competitor.data.scrape'],
    escalate:['demand.surge.critical.alert', 'capacity.breach.forecast'],
  },
  lastmile: {
    allow:   ['delivery.route.optimize', 'attempt.record.log', 'locker.availability.check', 'customer.notify.sms', 'return.initiate'],
    block:   ['delivery.confirm.without.scan', 'address.override.unauth', 'signature.waiver.auto.grant'],
    escalate:['delivery.access.denied.escalate', 'highvalue.delivery.unconfirmed'],
  },
  freight: {
    allow:   ['rate.quote.generate', 'fuel.surcharge.calculate', 'zone.tariff.read', 'invoice.preview', 'contract.terms.read'],
    block:   ['rate.override.below.floor', 'discount.unauth.apply', 'invoice.amount.alter'],
    escalate:['freight.rate.exception.request', 'contract.deviation.approve'],
  },
  hub: {
    allow:   ['sort.plan.read', 'inbound.manifest.scan', 'conveyor.status.monitor', 'dock.assign.read', 'staff.shift.view'],
    block:   ['sort.override.destination.unauth', 'hub.capacity.falsify', 'xray.screening.bypass'],
    escalate:['hub.critical.overflow.alert', 'sort.error.mass.recall.request'],
  },
  supplychain: {
    allow:   ['supplier.status.query', 'procurement.order.read', 'lead.time.estimate', 'inventory.replenish.suggest', 'vendor.performance.read'],
    block:   ['supplier.contract.modify.unauth', 'bulk.purchase.over.limit', 'vendor.data.share.external'],
    escalate:['supplier.failure.critical.alert', 'supply.chain.disruption.declare'],
  },
  anomaly: {
    allow:   ['anomaly.signal.read', 'pattern.scan.run', 'risk.flag.check', 'alert.generate.low', 'baseline.compare'],
    block:   ['anomaly.data.share.external', 'detection.model.disable', 'alert.suppress.unauth'],
    escalate:['fraud.cluster.detected.escalate', 'theft.pattern.critical.alert'],
  },
  customer: {
    allow:   ['claim.status.read', 'refund.eligibility.check', 'ticket.create', 'customer.notify', 'delivery.reattempt.schedule'],
    block:   ['refund.auto.approve.overlimit', 'customer.data.bulk.export', 'compensation.override.policy'],
    escalate:['complaint.highvalue.escalate', 'legal.threat.escalate'],
  },
}

const REASON_CODES: Record<Verdict, string[]> = {
  ALLOW:    ['APPROVED', 'WITHIN_POLICY', 'AUTHORIZED_OP', 'ROUTINE_QUERY', 'LOW_RISK_VERIFIED'],
  BLOCK:    ['SANCTIONS_VIOLATION', 'UNAUTHORIZED_REROUTE', 'CUSTOMS_VIOLATION', 'SAFETY_BREACH', 'DATA_EXFILTRATION', 'RATE_MANIPULATION', 'HOURS_OF_SERVICE', 'HAZMAT_RESTRICTION', 'FRAUD_SIGNAL', 'SCOPE_VIOLATION'],
  ESCALATE: ['CHAIN_OF_CUSTODY_BREAK', 'MASS_REROUTE_REQUEST', 'HIGHVALUE_HOLD_RELEASE', 'CAPACITY_BREACH', 'SUPPLIER_FAILURE', 'HUB_OVERFLOW', 'DEMAND_SURGE_CRITICAL', 'THEFT_CLUSTER_DETECTED'],
}

const SHIPMENT_IDS = Array.from({ length: 60 }, () => `SHP-${String(rand(10000, 99999)).padStart(5, '0')}`)
const INTENT_IDS   = Array.from({ length: 20 }, (_, i) => `INT-${String(i + 1).padStart(4, '0')}`)
const POLICY_VERS  = ['v2.4.1', 'v2.4.2', 'v2.5.0', 'v2.5.1', 'v2.6.0']

const OP_CONTEXTS = [
  'Peak season surge — Memphis hub at 94% capacity',
  'Hurricane Ian disruption — SE corridor reroute active',
  'Black Friday +340% volume — all hubs on alert',
  'Customs hold — LAX pharmaceutical manifest flagged',
  'Driver HOS limit approaching — route optimization active',
  'International freight — sanction screening required',
  'Warehouse outbound freeze — anomaly cluster detected',
  'Last mile SLA breach risk — ETA exceeded by 4h',
  'High-value freight — $2.4M pharmaceutical shipment',
  'Cross-border — USMCA trade agreement applies',
  'Emergency reroute — I-40 closure affecting 47k packages',
  'Demand forecast — 23% above model prediction',
]

const BLOCK_EXPLANATIONS: Partial<Record<string, string>> = {
  'SANCTIONS_VIOLATION':    'Destination country flagged under OFAC sanctions list — shipment blocked pending compliance review.',
  'UNAUTHORIZED_REROUTE':   'Agent attempted bulk reroute of 12,400 packages without supervisor authorization — operation blocked.',
  'CUSTOMS_VIOLATION':      'Manifest declared value 40% below market rate — tariff underreporting detected, blocked.',
  'SAFETY_BREACH':          'Agent requested bypass of safety lockout procedure — DOT regulation violation, blocked.',
  'DATA_EXFILTRATION':      'Bulk export of 890k tracking records to external endpoint — blocked, security incident logged.',
  'RATE_MANIPULATION':      'Freight rate modified to 23% below floor price — revenue protection policy violated.',
  'HOURS_OF_SERVICE':       'Driver assignment would exceed FMCSA 11-hour HOS limit — dispatch blocked.',
  'HAZMAT_RESTRICTION':     'Hazardous material routing through residential zone — IATA regulation violation, blocked.',
  'FRAUD_SIGNAL':           'Delivery confirmation without physical scan on 23 sequential packages — fraud pattern detected.',
  'SCOPE_VIOLATION':        'Agent operating outside authorized operational scope — action blocked by policy.',
}

function genExplanation(verdict: Verdict, reasonCode: string, toolOp: string): string {
  if (verdict === 'ALLOW') return `Operation ${toolOp} evaluated against active policy. All constraints satisfied — action authorized.`
  if (verdict === 'ESCALATE') return `Action ${toolOp} exceeds autonomous authority threshold. Routed to Operations Supervisor queue for review.`
  return BLOCK_EXPLANATIONS[reasonCode] ?? `Action ${toolOp} violates active governance policy. Operation blocked and logged.`
}

// ─── Generate Events ──────────────────────────────────────────────────────────

function generateEvents(): LogisticsEvent[] {
  const events: LogisticsEvent[] = []
  const deptKeys = Object.keys(DEPTS) as DeptKey[]
  const now = new Date()

  for (let i = 0; i < 1000; i++) {
    const dept = pick(deptKeys)
    const ops = DEPT_OPS[dept]
    const roll = rng()
    let verdict: Verdict
    let toolOp: string
    if (roll < 0.58) { verdict = 'ALLOW'; toolOp = pick(ops.allow) }
    else if (roll < 0.85) { verdict = 'BLOCK'; toolOp = pick(ops.block) }
    else { verdict = 'ESCALATE'; toolOp = pick(ops.escalate) }

    const reasonCode = pick(REASON_CODES[verdict])
    const vendor = pick(VENDORS)
    const vehicle = pick(VEHICLE_TYPES)
    const agentNames = AGENT_NAMES[dept]
    const agentName = pick(agentNames)
    const tsOffset = i * 86 + rand(0, 60)
    const ts = new Date(now.getTime() - (1000 - i) * tsOffset * 1000)
    const latency = verdict === 'ALLOW' ? rand(2, 12) : rand(4, 22)
    const riskScore = verdict === 'ALLOW' ? randF(0.05, 0.35) : verdict === 'BLOCK' ? randF(0.65, 0.98) : randF(0.45, 0.75)

    events.push({
      id: `EVT-${String(i + 1).padStart(5, '0')}`,
      verdict,
      agent: agentName,
      department: dept,
      deptLabel: DEPTS[dept].label,
      toolOp,
      reasonCode,
      latencyMs: latency,
      ts,
      hash: Math.random().toString(36).slice(2, 10) + Math.random().toString(36).slice(2, 10),
      riskScore,
      shipmentId: pick(SHIPMENT_IDS),
      intentId: pick(INTENT_IDS),
      policyVersion: pick(POLICY_VERS),
      explanation: genExplanation(verdict, reasonCode, toolOp),
      vendorId: vendor.id,
      vendorName: vendor.name,
      vehicleId: vehicle.id,
      vehicleName: vehicle.name,
      operationalContext: pick(OP_CONTEXTS),
      priority: riskScore > 0.75 ? 'critical' : riskScore > 0.45 ? 'urgent' : 'routine',
      reviewStatus: verdict === 'ESCALATE' ? (rng() > 0.6 ? 'pending' : rng() > 0.5 ? 'approved' : 'rejected') : undefined,
    })
  }
  return events
}

const ZONES = [
  'Zone A — Memphis Hub', 'Zone B — Chicago Sort', 'Zone C — LA Gateway',
  'Zone D — ATL Crossdock', 'Zone E — Dallas Hub', 'Zone F — Seattle Port',
  'Zone G — Newark Int\'l', 'Zone H — Miami Customs', 'Zone I — Phoenix Dist',
  'Zone J — Denver Hub',
]

// ─── Generate Agents ─────────────────────────────────────────────────────────

function generateAgents(): Agent[] {
  const agents: Agent[] = []
  const deptKeys = Object.keys(DEPTS) as DeptKey[]
  let id = 1
  for (const dept of deptKeys) {
    const count = DEPTS[dept].agentCount
    const deptOps = DEPT_OPS[dept]
    for (let i = 0; i < count; i++) {
      const names = AGENT_NAMES[dept]
      const statusRoll = rng()
      const status: Agent['status'] = statusRoll > 0.9 ? 'alert' : statusRoll > 0.82 ? 'idle' : 'active'
      const vendor = pick(VENDORS)
      const blockRate = randF(0.02, 0.18)
      const blockRatePrev = blockRate + randF(-0.06, 0.06)
      const diff = blockRate - blockRatePrev
      const blockRateTrend: Agent['blockRateTrend'] = diff > 0.04 ? 'spiked' : diff > 0.015 ? 'rising' : 'stable'
      const decisions24h = rand(80, 2400)
      const blocked24h = Math.round(decisions24h * blockRate)
      const lastAction = pick(deptOps.allow)
      agents.push({
        id: `AGT-${String(id++).padStart(4, '0')}`,
        name: names[i % names.length] + (i >= names.length ? `-${Math.floor(i / names.length) + 1}` : ''),
        department: dept,
        deptLabel: DEPTS[dept].label,
        status,
        decisions24h,
        blocked24h,
        blockRate,
        blockRatePrev: Math.max(0.01, blockRatePrev),
        blockRateTrend,
        avgLatency: randF(3, 28),
        vendor: vendor.name,
        zone: pick(ZONES),
        shipmentLoad: rand(12, 980),
        lastAction,
        lastActiveMin: rand(0, 119),
        lastSeen: new Date(Date.now() - rand(0, 7200) * 1000),
        policyVersion: pick(POLICY_VERS),
        riskLevel: status === 'alert' ? 'high' : status === 'idle' ? 'medium' : 'low',
      })
    }
  }
  return agents
}

const ALL_EVENTS = generateEvents()
const ALL_AGENTS = generateAgents()

// ─── Cross-Agent Chain Events ─────────────────────────────────────────────────

const CHAIN_EVENTS: CrossAgentChain[] = [
  {
    id: 'CHN-001',
    title: 'Hurricane Ian — SE Corridor Disruption',
    shipmentId: 'SHP-82341',
    severity: 'critical',
    summary: 'Category 3 hurricane forced emergency reroute of 47,000 packages. EDON blocked unauthorized bulk reroute attempt, escalated to Ops Supervisor, then authorized phased reroute across 6 hub corridors.',
    resolved: true,
    events: [
      { agent: 'DemandAI-1',   dept: 'forecasting', action: 'demand.surge.critical.alert',     verdict: 'ESCALATE', ts: new Date(Date.now() - 5400000) },
      { agent: 'PathFinder-7', dept: 'routing',      action: 'route.emergency.reroute.critical', verdict: 'ESCALATE', ts: new Date(Date.now() - 5100000) },
      { agent: 'FleetBot-1',   dept: 'dispatch',     action: 'fleet.dispatch.override.unauth',  verdict: 'BLOCK',    ts: new Date(Date.now() - 4800000) },
      { agent: 'HubOps-6',     dept: 'hub',          action: 'hub.critical.overflow.alert',      verdict: 'ESCALATE', ts: new Date(Date.now() - 4500000) },
      { agent: 'SortPlan-Alpha',dept: 'hub',          action: 'sort.plan.read',                  verdict: 'ALLOW',    ts: new Date(Date.now() - 4200000) },
    ],
  },
  {
    id: 'CHN-002',
    title: 'Pharmaceutical Manifest — Customs Hold',
    shipmentId: 'SHP-61097',
    severity: 'critical',
    summary: '$2.4M pharmaceutical shipment flagged by Customs AI for underdeclared value. Warehouse blocked outbound staging. Freight blocked invoice release. Escalated to Compliance Supervisor.',
    resolved: false,
    events: [
      { agent: 'TradeClear-3', dept: 'customs',   action: 'customs.docs.auto.approve.suspicious', verdict: 'BLOCK',    ts: new Date(Date.now() - 7200000) },
      { agent: 'SortBot-Alpha',dept: 'warehouse',  action: 'inventory.count.override.unauth',      verdict: 'BLOCK',    ts: new Date(Date.now() - 7000000) },
      { agent: 'RateBot-1',    dept: 'freight',    action: 'invoice.amount.alter',                 verdict: 'BLOCK',    ts: new Date(Date.now() - 6800000) },
      { agent: 'TradeClear-3', dept: 'customs',    action: 'customs.hold.release.highvalue',       verdict: 'ESCALATE', ts: new Date(Date.now() - 6600000) },
    ],
  },
  {
    id: 'CHN-003',
    title: 'Package Theft Cluster — LA Route 7',
    shipmentId: 'SHP-44782',
    severity: 'warning',
    summary: 'Anomaly Detection flagged 23 missing scans on LA Route 7. Tracking blocked delivery confirmations. Last Mile escalated 8 unconfirmed high-value deliveries. Chain of custody locked.',
    resolved: false,
    events: [
      { agent: 'FraudScan-1',  dept: 'anomaly',   action: 'fraud.cluster.detected.escalate',  verdict: 'ESCALATE', ts: new Date(Date.now() - 3600000) },
      { agent: 'ScanBot-Prime',dept: 'tracking',   action: 'signature.falsify',                verdict: 'BLOCK',    ts: new Date(Date.now() - 3400000) },
      { agent: 'TrackAI-2',    dept: 'tracking',   action: 'chain.of.custody.break.declare',   verdict: 'ESCALATE', ts: new Date(Date.now() - 3200000) },
      { agent: 'RouteBot-LM1', dept: 'lastmile',   action: 'highvalue.delivery.unconfirmed',   verdict: 'ESCALATE', ts: new Date(Date.now() - 3000000) },
    ],
  },
  {
    id: 'CHN-004',
    title: 'Black Friday Surge — Pricing Override Attempt',
    shipmentId: 'SHP-39105',
    severity: 'warning',
    summary: 'Forecasting detected 340% volume surge. Extra warehouse capacity authorized. Unauthorized pricing floor override blocked. Memphis hub overflow escalated and resolved.',
    resolved: true,
    events: [
      { agent: 'DemandAI-1',   dept: 'forecasting', action: 'demand.surge.critical.alert',   verdict: 'ESCALATE', ts: new Date(Date.now() - 86400000) },
      { agent: 'SortBot-Alpha',dept: 'warehouse',    action: 'inventory.read',                verdict: 'ALLOW',    ts: new Date(Date.now() - 86200000) },
      { agent: 'RateBot-1',    dept: 'freight',      action: 'rate.override.below.floor',     verdict: 'BLOCK',    ts: new Date(Date.now() - 86000000) },
      { agent: 'SortPlan-Alpha',dept: 'hub',          action: 'hub.critical.overflow.alert',   verdict: 'ESCALATE', ts: new Date(Date.now() - 85800000) },
      { agent: 'HubOps-6',    dept: 'hub',           action: 'sort.plan.read',                verdict: 'ALLOW',    ts: new Date(Date.now() - 85600000) },
    ],
  },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function cn(...classes: (string | undefined | false | null)[]) {
  return classes.filter(Boolean).join(' ')
}

function fmtTime(d: Date) {
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

function fmtDate(d: Date) {
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function timeAgo(d: Date) {
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

// ─── Passcode Gate ────────────────────────────────────────────────────────────

const PASSCODE_HASH = '1ee8baaaa5e66d5624b72e6fe737927bb47eef4315c6d7880571657163dd9976'

async function sha256(str: string) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

function LogisticsAccessGate({ onUnlock }: { onUnlock: () => void }) {
  const [code, setCode]       = useState('')
  const [show, setShow]       = useState(false)
  const [error, setError]     = useState(false)
  const [shaking, setShaking] = useState(false)
  const [checking, setChecking] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setChecking(true)
    const hash = await sha256(code)
    setChecking(false)
    if (hash === PASSCODE_HASH) {
      onUnlock()
    } else {
      setError(true)
      setShaking(true)
      setTimeout(() => setShaking(false), 600)
      setTimeout(() => setError(false), 2000)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background relative overflow-hidden">
      {/* Background grid */}
      <div className="absolute inset-0 opacity-[0.03]"
        style={{ backgroundImage: 'linear-gradient(hsl(38 95% 52%) 1px,transparent 1px),linear-gradient(90deg,hsl(38 95% 52%) 1px,transparent 1px)', backgroundSize: '40px 40px' }} />

      {/* Glow */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] rounded-full opacity-10 blur-[120px]"
        style={{ background: 'radial-gradient(ellipse, hsl(38 95% 52%), transparent)' }} />

      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className={cn('relative z-10 w-full max-w-md mx-4', shaking && 'animate-slideIn')}
      >
        <div className="glass-card p-8 space-y-7">
          {/* Logo */}
          <div className="text-center space-y-4">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-2"
              style={{ background: 'hsl(38 95% 52% / 0.15)', border: '1px solid hsl(38 95% 52% / 0.3)' }}>
              <Truck className="w-8 h-8" style={{ color: 'hsl(38 95% 52%)' }} />
            </div>
            <div>
              <div className="flex items-center justify-center gap-2 mb-1">
                <span className="text-xs font-semibold tracking-[0.2em] uppercase text-muted-foreground">EDON</span>
                <span className="text-xs text-muted-foreground/50">·</span>
                <span className="text-xs font-semibold tracking-[0.2em] uppercase" style={{ color: 'hsl(38 95% 52%)' }}>Logistics</span>
              </div>
              <h1 className="text-2xl font-bold text-foreground">NexRoute Operations</h1>
              <p className="text-sm text-muted-foreground mt-1">AI Governance Command Center</p>
            </div>
          </div>

          {/* Metrics preview */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: 'Agents Active', value: '521' },
              { label: 'Daily Decisions', value: '1.2M' },
              { label: 'Avg Latency', value: '7ms' },
            ].map(m => (
              <div key={m.label} className="rounded-xl p-3 text-center" style={{ background: 'hsl(220 12% 18% / 0.6)' }}>
                <div className="text-lg font-bold text-foreground">{m.value}</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">{m.label}</div>
              </div>
            ))}
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground tracking-wide uppercase">Access Code</label>
              <div className="relative">
                <input
                  type={show ? 'text' : 'password'}
                  value={code}
                  onChange={e => { setCode(e.target.value); setError(false) }}
                  placeholder=""
                  className={cn(
                    'w-full px-4 py-3 pr-11 rounded-xl text-sm font-mono bg-secondary/60 border outline-none transition-all',
                    error
                      ? 'border-red-500 text-red-400'
                      : 'border-border focus:border-amber-500/60 focus:ring-1 focus:ring-amber-500/20 text-foreground'
                  )}
                  autoFocus
                />
                <button type="button" onClick={() => setShow(s => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors">
                  {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {error && <p className="text-xs text-red-400">Incorrect access code. Try again.</p>}
            </div>

            <button
              type="submit"
              disabled={!code || checking}
              className="w-full py-3 rounded-xl text-sm font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              style={{ background: 'hsl(38 95% 52%)', color: 'hsl(20 10% 8%)' }}
            >
              {checking ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
              {checking ? 'Verifying...' : 'Enter Command Center'}
            </button>
          </form>

          <p className="text-center text-xs text-muted-foreground/60">
            EDON Governance Platform · NexRoute Global Logistics · Confidential
          </p>
        </div>
      </motion.div>
    </div>
  )
}

// ─── Verdict Badge ────────────────────────────────────────────────────────────

function VerdictBadge({ verdict, small }: { verdict: Verdict; small?: boolean }) {
  const cfg = {
    ALLOW:    { bg: 'bg-emerald-500/15', text: 'text-emerald-400', border: 'border-emerald-500/30', icon: <CheckCircle className="w-3 h-3" /> },
    BLOCK:    { bg: 'bg-red-500/15',     text: 'text-red-400',     border: 'border-red-500/30',     icon: <XCircle className="w-3 h-3" /> },
    ESCALATE: { bg: 'bg-amber-500/15',   text: 'text-amber-400',   border: 'border-amber-500/30',   icon: <AlertTriangle className="w-3 h-3" /> },
  }[verdict]
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full border font-semibold', cfg.bg, cfg.text, cfg.border, small ? 'text-[10px] px-1.5 py-0.5' : 'text-xs px-2 py-1')}>
      {cfg.icon}{verdict}
    </span>
  )
}

// ─── Dept Icon ────────────────────────────────────────────────────────────────

function DeptIcon({ dept, className }: { dept: DeptKey; className?: string }) {
  const icons: Record<DeptKey, React.ReactNode> = {
    routing:     <Navigation className={className} />,
    dispatch:    <Truck className={className} />,
    customs:     <Globe className={className} />,
    warehouse:   <Warehouse className={className} />,
    tracking:    <Package className={className} />,
    forecasting: <BarChart3 className={className} />,
    lastmile:    <MapPin className={className} />,
    freight:     <DollarSign className={className} />,
    hub:         <Activity className={className} />,
    supplychain: <Anchor className={className} />,
    anomaly:     <AlertTriangle className={className} />,
    customer:    <Headphones className={className} />,
  }
  return <>{icons[dept]}</>
}

const DEPT_COLORS: Record<DeptKey, string> = {
  routing:     'text-amber-400',
  dispatch:    'text-orange-400',
  customs:     'text-blue-400',
  warehouse:   'text-purple-400',
  tracking:    'text-emerald-400',
  forecasting: 'text-sky-400',
  lastmile:    'text-pink-400',
  freight:     'text-violet-400',
  hub:         'text-teal-400',
  supplychain: 'text-cyan-400',
  anomaly:     'text-red-400',
  customer:    'text-indigo-400',
}

// ─── Dashboard Tab ────────────────────────────────────────────────────────────

function DashboardTab({ events, liveMode, onToggleLive }: {
  events: LogisticsEvent[]
  liveMode: boolean
  onToggleLive: () => void
}) {
  const recent = events.slice(-100).reverse()
  const total  = events.length
  const allows = events.filter(e => e.verdict === 'ALLOW').length
  const blocks = events.filter(e => e.verdict === 'BLOCK').length
  const escals = events.filter(e => e.verdict === 'ESCALATE').length
  const avgLat = Math.round(events.reduce((s, e) => s + e.latencyMs, 0) / total)
  const blockRate = ((blocks / total) * 100).toFixed(1)

  const deptStats = (Object.keys(DEPTS) as DeptKey[]).map(dept => {
    const dEvts = events.filter(e => e.department === dept)
    return { dept, label: DEPTS[dept].label, total: dEvts.length, blocks: dEvts.filter(e => e.verdict === 'BLOCK').length }
  }).sort((a, b) => b.blocks - a.blocks)

  return (
    <div className="space-y-6">
      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label: 'Total Decisions', value: total.toLocaleString(), sub: 'All-time', icon: <Zap className="w-4 h-4" />, color: 'text-amber-400' },
          { label: 'Allowed', value: allows.toLocaleString(), sub: `${((allows/total)*100).toFixed(1)}% rate`, icon: <CheckCircle className="w-4 h-4" />, color: 'text-emerald-400' },
          { label: 'Blocked', value: blocks.toLocaleString(), sub: `${blockRate}% block rate`, icon: <XCircle className="w-4 h-4" />, color: 'text-red-400' },
          { label: 'Escalated', value: escals.toLocaleString(), sub: 'Ops review queue', icon: <AlertTriangle className="w-4 h-4" />, color: 'text-amber-400' },
          { label: 'Avg Latency', value: `${avgLat}ms`, sub: 'P50 enforcement', icon: <Clock className="w-4 h-4" />, color: 'text-sky-400' },
        ].map(k => (
          <div key={k.label} className="glass-card p-4 space-y-2">
            <div className={cn('flex items-center gap-1.5', k.color)}>{k.icon}<span className="text-xs font-medium opacity-80">{k.label}</span></div>
            <div className="text-2xl font-bold text-foreground">{k.value}</div>
            <div className="text-xs text-muted-foreground">{k.sub}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Live Feed */}
        <div className="lg:col-span-2 glass-card">
          <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-border/50">
            <div className="flex items-center gap-2">
              <div className={cn('w-2 h-2 rounded-full', liveMode ? 'bg-emerald-400 animate-pulse-dot' : 'bg-muted-foreground')} />
              <span className="text-sm font-semibold">Live Decision Feed</span>
            </div>
            <button onClick={onToggleLive}
              className={cn('text-xs px-2.5 py-1 rounded-full border transition-all', liveMode ? 'border-emerald-500/40 text-emerald-400 bg-emerald-500/10' : 'border-border text-muted-foreground')}>
              {liveMode ? 'LIVE' : 'PAUSED'}
            </button>
          </div>
          <div className="divide-y divide-border/30 max-h-[420px] overflow-y-auto">
            {recent.slice(0, 18).map(ev => (
              <div key={ev.id} className="flex items-center gap-3 px-5 py-2.5 hover:bg-muted/20 transition-colors">
                <VerdictBadge verdict={ev.verdict} small />
                <div className={cn('flex-shrink-0', DEPT_COLORS[ev.department])}>
                  <DeptIcon dept={ev.department} className="w-3.5 h-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-foreground truncate">{ev.agent}</span>
                    <span className="text-xs text-muted-foreground/60">·</span>
                    <span className="text-xs text-muted-foreground truncate">{ev.toolOp}</span>
                  </div>
                  <div className="text-[10px] text-muted-foreground/60">{ev.deptLabel} · {ev.shipmentId}</div>
                </div>
                <div className="flex-shrink-0 text-right">
                  <div className="text-[10px] text-muted-foreground">{ev.latencyMs}ms</div>
                  <div className="text-[10px] text-muted-foreground/50">{fmtTime(ev.ts)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Dept Block Leaderboard */}
        <div className="glass-card">
          <div className="px-5 pt-5 pb-3 border-b border-border/50">
            <span className="text-sm font-semibold">Blocks by Department</span>
          </div>
          <div className="p-5 space-y-3">
            {deptStats.slice(0, 8).map(ds => {
              const pct = ds.total ? (ds.blocks / ds.total) * 100 : 0
              const dept = ds.dept
              return (
                <div key={dept} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <span className={cn(DEPT_COLORS[dept])}><DeptIcon dept={dept} className="w-3 h-3" /></span>
                      <span className="text-foreground/80 truncate max-w-[120px]">{ds.label}</span>
                    </div>
                    <span className="text-muted-foreground font-mono">{ds.blocks} <span className="text-muted-foreground/50">({pct.toFixed(0)}%)</span></span>
                  </div>
                  <div className="h-1 rounded-full bg-muted/40">
                    <div className="h-1 rounded-full bg-red-400/70 transition-all" style={{ width: `${Math.min(pct * 4, 100)}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Cross-Agent Chains */}
      <div className="glass-card">
        <div className="px-5 pt-5 pb-3 border-b border-border/50 flex items-center justify-between">
          <span className="text-sm font-semibold">Cross-Agent Chain Events</span>
          <span className="text-xs text-muted-foreground">{CHAIN_EVENTS.filter(c => !c.resolved).length} active incidents</span>
        </div>
        <div className="divide-y divide-border/30">
          {CHAIN_EVENTS.map(chain => (
            <div key={chain.id} className="p-5">
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex items-center gap-2">
                  <span className={cn('w-2 h-2 rounded-full flex-shrink-0 mt-0.5',
                    chain.severity === 'critical' ? 'bg-red-400' : chain.severity === 'warning' ? 'bg-amber-400' : 'bg-sky-400')} />
                  <div>
                    <div className="text-sm font-semibold">{chain.title}</div>
                    <div className="text-xs text-muted-foreground">{chain.shipmentId}</div>
                  </div>
                </div>
                <span className={cn('text-xs px-2 py-0.5 rounded-full border',
                  chain.resolved ? 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10' : 'border-amber-500/30 text-amber-400 bg-amber-500/10')}>
                  {chain.resolved ? 'Resolved' : 'Active'}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mb-3">{chain.summary}</p>
              <div className="flex items-center gap-2 flex-wrap">
                {chain.events.map((ce, i) => (
                  <div key={i} className="flex items-center gap-1.5">
                    <div className="flex items-center gap-1 rounded-lg px-2 py-1 bg-muted/30 border border-border/40">
                      <span className={cn(DEPT_COLORS[ce.dept])}><DeptIcon dept={ce.dept} className="w-3 h-3" /></span>
                      <span className="text-[10px] font-medium text-foreground/80">{ce.agent}</span>
                      <VerdictBadge verdict={ce.verdict} small />
                    </div>
                    {i < chain.events.length - 1 && <ChevronRight className="w-3 h-3 text-muted-foreground/40" />}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Agents Tab ───────────────────────────────────────────────────────────────

function AgentsTab() {
  const [selectedDept, setSelectedDept] = useState<DeptKey | 'all'>('all')
  const [search, setSearch]             = useState('')
  const [page, setPage]                 = useState(0)
  const [viewMode, setViewMode]         = useState<'list' | 'grouped'>('grouped')
  const PAGE_SIZE = 25

  const statusConfig: Record<Agent['status'], { label: string; color: string; dot: string }> = {
    active: { label: 'Active', color: 'text-emerald-400',        dot: 'bg-emerald-400' },
    idle:   { label: 'Idle',   color: 'text-muted-foreground',   dot: 'bg-muted-foreground' },
    alert:  { label: 'Alert',  color: 'text-red-400',            dot: 'bg-red-400' },
  }

  const riskConfig: Record<Agent['riskLevel'], { label: string; bg: string; text: string; border: string }> = {
    low:    { label: 'Low',  bg: 'bg-emerald-500/15', text: 'text-emerald-400', border: 'border-emerald-500/30' },
    medium: { label: 'Med',  bg: 'bg-amber-500/15',   text: 'text-amber-400',   border: 'border-amber-500/30' },
    high:   { label: 'High', bg: 'bg-red-500/15',     text: 'text-red-400',     border: 'border-red-500/30' },
  }

  const deptKeys = Object.keys(DEPTS) as DeptKey[]

  const filtered = ALL_AGENTS.filter(a => {
    const matchDept = selectedDept === 'all' || a.department === selectedDept
    const matchSearch = !search ||
      a.id.toLowerCase().includes(search.toLowerCase()) ||
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.deptLabel.toLowerCase().includes(search.toLowerCase()) ||
      a.zone.toLowerCase().includes(search.toLowerCase())
    return matchDept && matchSearch
  })

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paginated  = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  const byDept = deptKeys.map(key => ({
    key, ...DEPTS[key],
    agents: filtered.filter(a => a.department === key),
  })).filter(g => g.agents.length > 0)

  useEffect(() => { setPage(0) }, [selectedDept, search])

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Agent Fleet</h1>
          <p className="text-muted-foreground text-sm mt-1">{ALL_AGENTS.length} agents across {deptKeys.length} departments</p>
        </div>
        <div className="flex items-center gap-1 p-1 rounded-xl border border-white/10 bg-white/[0.03] shrink-0">
          <button onClick={() => setViewMode('list')}
            className={cn('flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
              viewMode === 'list' ? 'bg-amber-500/20 text-amber-400' : 'text-muted-foreground hover:text-foreground')}>
            <LayoutList size={13} /> List
          </button>
          <button onClick={() => setViewMode('grouped')}
            className={cn('flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
              viewMode === 'grouped' ? 'bg-amber-500/20 text-amber-400' : 'text-muted-foreground hover:text-foreground')}>
            <LayoutGrid size={13} /> By Department
          </button>
        </div>
      </div>

      {/* Department filter pills */}
      <div className="flex flex-wrap gap-2">
        <button onClick={() => setSelectedDept('all')}
          className={cn('inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all border',
            selectedDept === 'all'
              ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
              : 'bg-secondary text-muted-foreground border-white/10 hover:border-white/20 hover:text-foreground')}>
          All · {ALL_AGENTS.length}
        </button>
        {deptKeys.map(key => {
          const d = DEPTS[key]
          return (
            <button key={key} onClick={() => setSelectedDept(key)}
              className={cn('inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all border',
                selectedDept === key
                  ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                  : 'bg-secondary text-muted-foreground border-white/10 hover:border-white/20 hover:text-foreground')}>
              <span className={selectedDept === key ? 'text-amber-400' : DEPT_COLORS[key]}>
                <DeptIcon dept={key} className="w-2.5 h-2.5" />
              </span>
              {d.label} · {d.agentCount}
            </button>
          )
        })}
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          placeholder="Search agents, departments, zones..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2 rounded-xl text-xs bg-secondary/60 border border-border outline-none focus:border-amber-500/50 text-foreground"
        />
      </div>

      <AnimatePresence mode="wait">
        {/* ── LIST VIEW ── */}
        {viewMode === 'list' && (
          <motion.div key="list" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="glass-card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-white/10 text-muted-foreground">
                      <th className="text-left px-4 py-3 font-medium">Agent ID</th>
                      <th className="text-left px-4 py-3 font-medium hidden sm:table-cell">Department</th>
                      <th className="text-left px-4 py-3 font-medium hidden md:table-cell">Zone</th>
                      <th className="text-left px-4 py-3 font-medium">Status</th>
                      <th className="text-right px-4 py-3 font-medium hidden lg:table-cell">Decisions/24h</th>
                      <th className="text-right px-4 py-3 font-medium hidden lg:table-cell">Blocked</th>
                      <th className="text-left px-4 py-3 font-medium hidden xl:table-cell">Block Rate</th>
                      <th className="text-left px-4 py-3 font-medium">Risk</th>
                      <th className="px-4 py-3 font-medium hidden md:table-cell">Last Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginated.map(agent => {
                      const s = statusConfig[agent.status]
                      const r = riskConfig[agent.riskLevel]
                      return (
                        <tr key={agent.id} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <span className={cn(DEPT_COLORS[agent.department], 'flex-shrink-0')}><DeptIcon dept={agent.department} className="w-3 h-3" /></span>
                              <div>
                                <div className="font-mono text-foreground font-medium">{agent.id}</div>
                                <div className="text-muted-foreground/70">{agent.name}</div>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3 hidden sm:table-cell">
                            <span className="text-muted-foreground">{agent.deptLabel}</span>
                          </td>
                          <td className="px-4 py-3 hidden md:table-cell">
                            <span className="font-mono text-muted-foreground text-[11px]">{agent.zone}</span>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-1.5">
                              <span className={cn('w-1.5 h-1.5 rounded-full animate-pulse-dot', s.dot)} />
                              <span className={s.color}>{s.label}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-right hidden lg:table-cell">
                            <span className="font-mono text-foreground">{agent.decisions24h.toLocaleString()}</span>
                          </td>
                          <td className="px-4 py-3 text-right hidden lg:table-cell">
                            <span className="font-mono text-red-400">{agent.blocked24h.toLocaleString()}</span>
                          </td>
                          <td className="px-4 py-3 hidden xl:table-cell">
                            <div className="flex items-center gap-2">
                              <div className="w-16 h-1 bg-secondary rounded-full overflow-hidden">
                                <div className="h-full rounded-full bg-red-400/70" style={{ width: `${Math.min(agent.blockRate * 100, 100)}%` }} />
                              </div>
                              <span className="text-muted-foreground">{(agent.blockRate * 100).toFixed(1)}%</span>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <span className={cn('inline-flex items-center gap-1 rounded-full border text-[10px] px-1.5 py-0.5 font-semibold', r.bg, r.text, r.border)}>
                              {r.label}
                            </span>
                          </td>
                          <td className="px-4 py-3 hidden md:table-cell">
                            <div>
                              <span className="text-foreground/80">{agent.lastAction.split('.').slice(-2).join(' ')}</span>
                              <span className="text-muted-foreground/50 text-[11px] ml-1.5">
                                {agent.lastActiveMin === 0 ? 'just now' : `${agent.lastActiveMin}m ago`}
                              </span>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              {/* Pagination */}
              <div className="flex items-center justify-between px-4 py-3 border-t border-white/5">
                <span className="text-xs text-muted-foreground">
                  Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
                </span>
                <div className="flex items-center gap-1">
                  <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                    className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                    <ChevronLeft className="w-3.5 h-3.5" />
                  </button>
                  <span className="text-xs text-muted-foreground px-2">{page + 1} / {totalPages}</span>
                  <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
                    className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {/* ── GROUPED VIEW ── */}
        {viewMode === 'grouped' && (
          <motion.div key="grouped" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-8">
            {byDept.map(({ key, label, agents }) => {
              const alertCount   = agents.filter(a => a.status === 'alert').length
              const avgBlockRate = agents.length ? (agents.reduce((s, a) => s + a.blockRate, 0) / agents.length * 100).toFixed(1) : '0.0'
              return (
                <motion.div key={key} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
                  {/* Dept header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={cn(DEPT_COLORS[key])}><DeptIcon dept={key} className="w-3.5 h-3.5" /></span>
                      <h3 className="text-sm font-semibold text-foreground">{label}</h3>
                      <span className="text-xs text-muted-foreground bg-white/[0.05] px-2 py-0.5 rounded-full border border-white/10">
                        {agents.length} agents
                      </span>
                      {alertCount > 0 && (
                        <span className="text-[10px] text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded-full font-semibold">
                          {alertCount} ALERT
                        </span>
                      )}
                      {(() => {
                        const spiked = agents.filter(a => a.blockRateTrend === 'spiked').length
                        const rising = agents.filter(a => a.blockRateTrend === 'rising').length
                        if (spiked > 0) return (
                          <span className="text-[10px] text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded-full font-semibold animate-pulse">
                            ↑↑ {spiked} spiked
                          </span>
                        )
                        if (rising > 0) return (
                          <span className="text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full font-semibold">
                            ↑ {rising} rising
                          </span>
                        )
                        return null
                      })()}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      Avg block rate: <span className="text-foreground font-mono">{avgBlockRate}%</span>
                    </span>
                  </div>

                  {/* Agent cards grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                    {agents.slice(0, 8).map(agent => {
                      const s = statusConfig[agent.status]
                      const r = riskConfig[agent.riskLevel]
                      return (
                        <div key={agent.id}
                          className={cn('rounded-2xl border p-4 hover:bg-white/[0.04] transition-colors space-y-3',
                            agent.status === 'alert' || agent.blockRateTrend === 'spiked'
                              ? 'border-red-500/30 bg-red-500/[0.04]'
                              : agent.blockRateTrend === 'rising'
                              ? 'border-amber-500/20 bg-white/[0.03]'
                              : 'border-white/10 bg-white/[0.03]')}>
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <div className={cn('p-1.5 rounded-lg bg-white/[0.05]', DEPT_COLORS[key])}>
                                <DeptIcon dept={key} className="w-3 h-3" />
                              </div>
                              <div className="min-w-0">
                                <div className="font-mono text-xs text-foreground font-medium truncate">{agent.id}</div>
                                <div className="text-[10px] text-muted-foreground truncate">{agent.zone.split('—')[1]?.trim() ?? agent.zone}</div>
                              </div>
                            </div>
                            <div className="flex items-center gap-1 shrink-0">
                              <span className={cn('w-1.5 h-1.5 rounded-full animate-pulse-dot', s.dot)} />
                              <span className={cn('text-[10px]', s.color)}>{s.label}</span>
                            </div>
                          </div>
                          <div className="grid grid-cols-3 gap-1 text-center">
                            <div>
                              <div className="text-xs font-mono text-foreground font-semibold">{agent.decisions24h.toLocaleString()}</div>
                              <div className="text-[10px] text-muted-foreground">24h actions</div>
                            </div>
                            <div>
                              <div className="text-xs font-mono text-red-400 font-semibold">{(agent.blockRate * 100).toFixed(1)}%</div>
                              <div className="text-[10px] text-muted-foreground">Block rate</div>
                            </div>
                            <div>
                              {agent.blockRateTrend === 'spiked' && (
                                <div className="text-xs font-semibold text-red-400 flex items-center justify-center gap-0.5 animate-pulse">↑↑ Spike</div>
                              )}
                              {agent.blockRateTrend === 'rising' && (
                                <div className="text-xs font-semibold text-amber-400 flex items-center justify-center gap-0.5">↑ Rising</div>
                              )}
                              {agent.blockRateTrend === 'stable' && (
                                <div className="text-xs font-semibold text-emerald-400 flex items-center justify-center gap-0.5">→ Stable</div>
                              )}
                              <div className="text-[10px] text-muted-foreground">
                                was {(agent.blockRatePrev * 100).toFixed(1)}%
                              </div>
                            </div>
                          </div>
                          <div className="h-0.5 bg-secondary rounded-full overflow-hidden">
                            <div className="h-full rounded-full bg-red-400/60" style={{ width: `${Math.min(agent.blockRate * 100, 100)}%` }} />
                          </div>
                          <div className="flex items-center justify-between">
                            <span className={cn('inline-flex items-center gap-1 rounded-full border text-[10px] px-1.5 py-0.5 font-semibold', r.bg, r.text, r.border)}>
                              {r.label} Risk
                            </span>
                            <span className="text-[10px] text-muted-foreground">
                              {agent.lastActiveMin === 0 ? 'just now' : `${agent.lastActiveMin}m ago`}
                            </span>
                          </div>
                        </div>
                      )
                    })}
                    {agents.length > 8 && (
                      <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4 flex items-center justify-center">
                        <span className="text-xs text-muted-foreground">
                          +{agents.length - 8} more ·{' '}
                          <button onClick={() => { setSelectedDept(key); setViewMode('list') }} className="text-amber-400 hover:underline">
                            View all
                          </button>
                        </span>
                      </div>
                    )}
                  </div>
                </motion.div>
              )
            })}

            {/* Cross-agent chain feed */}
            <div className="glass-card">
              <div className="px-5 pt-5 pb-3 border-b border-border/50 flex items-center justify-between">
                <span className="text-sm font-semibold">Cross-Department Chain Events</span>
                <span className="text-xs text-muted-foreground">{CHAIN_EVENTS.filter(c => !c.resolved).length} active incidents</span>
              </div>
              <div className="divide-y divide-border/30">
                {CHAIN_EVENTS.map(chain => (
                  <div key={chain.id} className="p-5">
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="flex items-center gap-2">
                        <span className={cn('w-2 h-2 rounded-full flex-shrink-0 mt-0.5',
                          chain.severity === 'critical' ? 'bg-red-400' : chain.severity === 'warning' ? 'bg-amber-400' : 'bg-sky-400')} />
                        <div>
                          <div className="text-sm font-semibold">{chain.title}</div>
                          <div className="text-xs text-muted-foreground">{chain.shipmentId}</div>
                        </div>
                      </div>
                      <span className={cn('text-xs px-2 py-0.5 rounded-full border shrink-0',
                        chain.resolved ? 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10' : 'border-amber-500/30 text-amber-400 bg-amber-500/10')}>
                        {chain.resolved ? 'Resolved' : 'Active'}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mb-3">{chain.summary}</p>
                    <div className="flex items-center gap-2 flex-wrap">
                      {chain.events.map((ce, i) => (
                        <div key={i} className="flex items-center gap-1.5">
                          <div className="flex items-center gap-1 rounded-lg px-2 py-1 bg-muted/30 border border-border/40">
                            <span className={cn(DEPT_COLORS[ce.dept])}><DeptIcon dept={ce.dept} className="w-3 h-3" /></span>
                            <span className="text-[10px] font-medium text-foreground/80">{ce.agent}</span>
                            <VerdictBadge verdict={ce.verdict} small />
                          </div>
                          {i < chain.events.length - 1 && <ChevronRight className="w-3 h-3 text-muted-foreground/40" />}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── Audit Tab ────────────────────────────────────────────────────────────────

const AUDIT_SHARED_KEY = 'edon_logistics_shared_audits'
const LOGISTICS_TEAM = [
  { email: 'ops@nexroute.com',        name: 'Ops Manager' },
  { email: 'compliance@nexroute.com', name: 'Compliance' },
  { email: 'customs@nexroute.com',    name: 'Customs Desk' },
  { email: 'security@nexroute.com',   name: 'Security' },
]

function loadSharedAudits(): SharedAuditRecord[] {
  try { const r = localStorage.getItem(AUDIT_SHARED_KEY); return r ? JSON.parse(r) : [] } catch { return [] }
}
function saveSharedAudits(items: SharedAuditRecord[]) {
  localStorage.setItem(AUDIT_SHARED_KEY, JSON.stringify(items))
}

function AuditTab({ events }: { events: LogisticsEvent[] }) {
  const [search, setSearch]         = useState('')
  const [verdict, setVerdict]       = useState<Verdict | 'ALL'>('ALL')
  const [dept, setDept]             = useState<DeptKey | 'all'>('all')
  const [expanded, setExpanded]     = useState<string | null>(null)
  const [copied, setCopied]         = useState<string | null>(null)
  const [filterTab, setFilterTab]   = useState<'all' | 'shared'>('all')
  const [page, setPage]             = useState(1)
  const PAGE_SIZE = 50

  const [sharedAudits, setSharedAudits] = useState<SharedAuditRecord[]>(() => loadSharedAudits())
  const [shareRecord, setShareRecord]   = useState<LogisticsEvent | null>(null)
  const [shareOpen, setShareOpen]       = useState(false)
  const [shareEmails, setShareEmails]   = useState<string[]>([])
  const [shareInput, setShareInput]     = useState('')
  const [shareNote, setShareNote]       = useState('')
  const [sharing, setSharing]           = useState(false)

  const sharedIds = new Set(sharedAudits.map(s => s.recordId))

  const filtered = events.filter(e => {
    const matchV = verdict === 'ALL' || e.verdict === verdict
    const matchD = dept === 'all' || e.department === dept
    const matchS = !search || e.agent.toLowerCase().includes(search.toLowerCase())
      || e.toolOp.toLowerCase().includes(search.toLowerCase())
      || e.shipmentId.toLowerCase().includes(search.toLowerCase())
    return matchV && matchD && matchS
  }).slice().reverse()

  const displayed  = filterTab === 'shared' ? filtered.filter(e => sharedIds.has(e.id)) : filtered
  const paged      = displayed.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const totalPages = Math.ceil(displayed.length / PAGE_SIZE)

  function copyHash(id: string, hash: string) {
    navigator.clipboard.writeText(hash)
    setCopied(id)
    setTimeout(() => setCopied(null), 1500)
  }

  function exportCsv() {
    const rows = [
      ['ID','Verdict','Agent','Department','Operation','Reason','Latency','Shipment','Risk','Timestamp'],
      ...displayed.slice(0, 500).map(e => [
        e.id, e.verdict, e.agent, e.deptLabel, e.toolOp, e.reasonCode,
        e.latencyMs, e.shipmentId, e.riskScore.toFixed(3), e.ts.toISOString(),
      ])
    ]
    const csv = rows.map(r => r.join(',')).join('\n')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    a.download = `nexroute-audit-${new Date().toISOString().split('T')[0]}.csv`
    a.click()
  }

  function addEmail(email: string) {
    const t = email.trim()
    if (!t || shareEmails.includes(t)) return
    setShareEmails(prev => [...prev, t]); setShareInput('')
  }

  async function doShare() {
    if (!shareRecord || shareEmails.length === 0) return
    setSharing(true)
    await new Promise(r => setTimeout(r, 400))
    const obj: SharedAuditRecord = {
      id: `share_${Date.now()}`,
      recordId: shareRecord.id,
      summary: { toolOp: shareRecord.toolOp, verdict: shareRecord.verdict, ts: shareRecord.ts.toISOString() },
      sharedBy: 'ops@nexroute.com',
      sharedWith: shareEmails,
      note: shareNote.trim(),
      sharedAt: new Date().toISOString(),
    }
    const next = [obj, ...sharedAudits]; saveSharedAudits(next); setSharedAudits(next)
    setSharing(false); setShareOpen(false); setShareEmails([]); setShareNote('')
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
        className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Governance Audit Trail</h1>
          <p className="text-muted-foreground text-sm mt-1">
            DOT/CBP-compliant audit log · {events.length.toLocaleString()} records · SHA-256 hash chain
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 font-semibold">
            <CheckCircle2 className="w-3 h-3" /> Chain Verified
          </span>
          <button onClick={exportCsv}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-border hover:bg-muted/40 text-muted-foreground transition-colors">
            <Download className="w-3.5 h-3.5" /> Export CSV
          </button>
          <button onClick={() => setPage(1)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-border hover:bg-muted/40 text-muted-foreground transition-colors">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>
      </motion.div>

      {/* Filter tabs */}
      <div className="flex items-center gap-1 bg-white/5 border border-white/10 rounded-xl p-1 w-fit">
        {(['all', 'shared'] as const).map(t => (
          <button key={t} onClick={() => { setFilterTab(t); setPage(1) }}
            className={cn('text-xs px-3 py-1.5 rounded-lg transition-colors',
              filterTab === t ? 'bg-white/10 text-foreground font-medium' : 'text-muted-foreground hover:text-foreground')}>
            {t === 'all' ? `All records (${events.length.toLocaleString()})` : `Shared (${sharedIds.size})`}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="glass-card p-4 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
            placeholder="Search agent, operation, shipment ID..."
            className="w-full pl-8 pr-3 py-2 rounded-lg text-xs bg-secondary/60 border border-border outline-none focus:border-amber-500/50 text-foreground" />
        </div>
        <select value={verdict} onChange={e => { setVerdict(e.target.value as Verdict | 'ALL'); setPage(1) }}
          className="px-3 py-2 rounded-lg text-xs bg-secondary/60 border border-border outline-none text-foreground">
          <option value="ALL">All Verdicts</option>
          <option value="ALLOW">ALLOW</option>
          <option value="BLOCK">BLOCK</option>
          <option value="ESCALATE">ESCALATE</option>
        </select>
        <select value={dept} onChange={e => { setDept(e.target.value as DeptKey | 'all'); setPage(1) }}
          className="px-3 py-2 rounded-lg text-xs bg-secondary/60 border border-border outline-none text-foreground">
          <option value="all">All Departments</option>
          {(Object.keys(DEPTS) as DeptKey[]).map(d => <option key={d} value={d}>{DEPTS[d].label}</option>)}
        </select>
        <span className="text-xs text-muted-foreground ml-auto">{displayed.length.toLocaleString()} records</span>
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/10 text-muted-foreground">
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider">Timestamp</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider">Verdict</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider">Operation</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider">Agent</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden md:table-cell">Reason</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden lg:table-cell">Shipment</th>
                <th className="text-right px-4 py-3 font-semibold uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {paged.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-muted-foreground">
                    {filterTab === 'shared' ? 'No shared records yet. Use the Share button on any record.' : 'No records match the selected filters.'}
                  </td>
                </tr>
              ) : paged.map(ev => {
                const isShared = sharedIds.has(ev.id)
                return (
                  <tr key={ev.id} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                    <td className="px-4 py-2.5 font-mono text-muted-foreground whitespace-nowrap">{fmtDate(ev.ts)}</td>
                    <td className="px-4 py-2.5"><VerdictBadge verdict={ev.verdict} small /></td>
                    <td className="px-4 py-2.5 text-foreground/80">{ev.toolOp}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <span className={cn(DEPT_COLORS[ev.department])}><DeptIcon dept={ev.department} className="w-3 h-3" /></span>
                        <span className="font-mono text-muted-foreground">{ev.agent}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 hidden md:table-cell">
                      {ev.reasonCode
                        ? <span className="text-amber-400 font-medium">{ev.reasonCode}</span>
                        : <span className="text-muted-foreground/30">—</span>}
                    </td>
                    <td className="px-4 py-2.5 hidden lg:table-cell">
                      <span className="font-mono text-muted-foreground/70">{ev.shipmentId}</span>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center justify-end gap-1">
                        {isShared && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-400 font-semibold mr-1">Shared</span>
                        )}
                        <button onClick={() => { setShareRecord(ev); setShareEmails([]); setShareInput(''); setShareNote(''); setShareOpen(true) }}
                          className="p-1.5 rounded-lg hover:bg-white/8 text-muted-foreground hover:text-foreground transition-colors" title="Share">
                          <Share2 className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => setExpanded(expanded === ev.id ? null : ev.id)}
                          className="flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-white/8 text-muted-foreground hover:text-foreground transition-colors">
                          <Eye className="w-3 h-3" /> View
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Expanded detail rows */}
        {paged.map(ev => expanded === ev.id && (
          <div key={`expand-${ev.id}`} className="px-5 pb-4 pt-1 space-y-4 bg-muted/10 border-t border-border/30">
            <p className="text-xs text-foreground/80 leading-relaxed">{ev.explanation}</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: 'Event ID',       value: ev.id },
                { label: 'Intent ID',      value: ev.intentId },
                { label: 'Policy Version', value: ev.policyVersion },
                { label: 'Risk Score',     value: ev.riskScore.toFixed(4) },
                { label: 'Vendor',         value: ev.vendorName },
                { label: 'Vehicle Type',   value: ev.vehicleName },
                { label: 'Priority',       value: ev.priority.toUpperCase() },
                { label: 'Shipment',       value: ev.shipmentId },
              ].map(f => (
                <div key={f.label}>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wide">{f.label}</div>
                  <div className="text-xs font-mono text-foreground/90">{f.value}</div>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <code className="text-[10px] font-mono text-muted-foreground bg-muted/30 px-2 py-1 rounded truncate flex-1">{ev.hash}</code>
              <button onClick={() => copyHash(ev.id, ev.hash)}
                className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors flex-shrink-0">
                <Copy className="w-3 h-3" />{copied === ev.id ? 'Copied!' : 'Copy hash'}
              </button>
            </div>
            <div className="text-[10px] text-muted-foreground italic">Context: {ev.operationalContext}</div>
          </div>
        ))}

        {/* Pagination */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-white/5">
          <span className="text-xs text-muted-foreground">
            Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, displayed.length)} of {displayed.length}
          </span>
          <div className="flex items-center gap-1">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <span className="text-xs text-muted-foreground px-2">{page} / {Math.max(1, totalPages)}</span>
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Share Modal */}
      <AnimatePresence>
        {shareOpen && shareRecord && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setShareOpen(false)}>
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
            <motion.div initial={{ opacity: 0, scale: 0.96, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.96, y: 8 }}
              onClick={e => e.stopPropagation()}
              className="relative glass-card w-full max-w-md p-6 z-10">
              <button onClick={() => setShareOpen(false)}
                className="absolute top-4 right-4 p-1.5 rounded-lg hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors">
                <X className="w-4 h-4" />
              </button>
              <div className="flex items-center gap-2 mb-5">
                <Share2 className="w-4 h-4" style={{ color: 'hsl(38 95% 52%)' }} />
                <h3 className="text-base font-semibold">Share Audit Record</h3>
              </div>
              {/* Record summary */}
              <div className="rounded-xl border border-white/10 bg-secondary/30 px-3 py-2.5 flex items-center gap-3 text-xs mb-4">
                <VerdictBadge verdict={shareRecord.verdict} small />
                <span className="font-mono text-foreground/80 truncate">{shareRecord.toolOp}</span>
                <span className="text-muted-foreground ml-auto shrink-0">{fmtDate(shareRecord.ts)}</span>
              </div>
              {/* Team quick-add */}
              <p className="text-xs text-muted-foreground mb-2">Share with</p>
              <div className="flex flex-wrap gap-1.5 mb-3">
                {LOGISTICS_TEAM.map(m => (
                  <button key={m.email} onClick={() => addEmail(m.email)} disabled={shareEmails.includes(m.email)}
                    className={cn('text-xs px-2.5 py-1 rounded-lg border transition-colors',
                      shareEmails.includes(m.email)
                        ? 'border-amber-500/30 bg-amber-500/10 text-amber-400 cursor-default'
                        : 'border-white/10 bg-white/5 text-muted-foreground hover:text-foreground hover:border-white/20')}>
                    {m.name}
                  </button>
                ))}
              </div>
              {/* Manual email */}
              <div className="flex gap-2 mb-3">
                <input value={shareInput} onChange={e => setShareInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addEmail(shareInput) } }}
                  placeholder="Add email address…"
                  className="flex-1 h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none" />
                <button onClick={() => addEmail(shareInput)} disabled={!shareInput.trim()}
                  className="px-3 py-1.5 rounded-xl border border-border text-xs text-muted-foreground hover:text-foreground hover:bg-muted/40 disabled:opacity-40 transition-colors">
                  Add
                </button>
              </div>
              {/* Email chips */}
              {shareEmails.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-3">
                  {shareEmails.map(email => (
                    <span key={email} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border border-white/20 bg-white/5 text-foreground/80">
                      {email}
                      <button onClick={() => setShareEmails(prev => prev.filter(e => e !== email))}
                        className="ml-0.5 text-muted-foreground hover:text-foreground">×</button>
                    </span>
                  ))}
                </div>
              )}
              {/* Note */}
              <p className="text-xs text-muted-foreground mb-1">Note (optional)</p>
              <textarea value={shareNote} onChange={e => setShareNote(e.target.value.slice(0, 200))}
                placeholder="Add context for your team…" maxLength={200} rows={3}
                className="w-full rounded-xl border border-white/15 bg-secondary/50 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none resize-none mb-1" />
              <p className="text-[10px] text-muted-foreground/50 text-right mb-4">{shareNote.length}/200</p>
              <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 flex items-center gap-2 text-xs text-muted-foreground mb-4">
                <span className="w-2.5 h-2.5 rounded-full border-2 border-amber-400 bg-amber-400/30 shrink-0" />
                Team members only · DOT/CBP compliant sharing
              </div>
              <div className="flex items-center gap-2">
                <button onClick={doShare} disabled={sharing || shareEmails.length === 0}
                  className="flex-1 py-2 rounded-xl text-sm font-semibold transition-all disabled:opacity-40 flex items-center justify-center gap-2"
                  style={{ background: 'hsl(38 95% 52%)', color: 'hsl(20 10% 8%)' }}>
                  {sharing
                    ? <><div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> Sharing…</>
                    : <><Share2 className="w-3.5 h-3.5" /> Share</>}
                </button>
                <button onClick={() => setShareOpen(false)}
                  className="px-4 py-2 rounded-xl border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors">
                  Cancel
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── Policies Tab ─────────────────────────────────────────────────────────────

interface LogisticsOp { code: string; label: string; description: string }
type RuleAction = 'allow' | 'block' | 'confirm'
interface AgentRule { id: string; agentScope: string; zone: string; operation: string; opLabel: string; action: RuleAction }

const LOGISTICS_ALLOWED_OPS: LogisticsOp[] = [
  { code: 'route.plan.generate',        label: 'Generate route plan',           description: 'Autonomous route optimization for up to 500 packages per batch — no approval needed' },
  { code: 'package.status.read',        label: 'Query package status',          description: 'Read delivery status, ETA, and scan history for any shipment in the system' },
  { code: 'customs.docs.verify',        label: 'Verify customs documents',      description: 'Cross-check manifests against declared values — read-only, no auto-approval' },
  { code: 'demand.forecast.query',      label: 'Run demand forecast',           description: 'Model volume projections for the next 30 days using historical patterns' },
  { code: 'inventory.read',             label: 'Read warehouse inventory',      description: 'View stock levels, pick queues, and dock scheduling — no modifications' },
  { code: 'vehicle.status.read',        label: 'Check vehicle telemetry',       description: 'Query GPS position, fuel level, and FMCSA hours-of-service remaining' },
  { code: 'anomaly.signal.read',        label: 'Read anomaly signals',          description: 'Access fraud detection outputs and statistical baseline deviation scores' },
  { code: 'rate.quote.generate',        label: 'Generate freight quote',        description: 'Calculate rates within contracted zone tariff ranges — floor protections apply' },
  { code: 'customer.notify',            label: 'Notify customer of ETA',        description: 'Send SMS/email delivery updates, delay notifications, and ETA changes' },
  { code: 'claim.status.read',          label: 'Check claim status',            description: 'View active claims, refund eligibility, and resolution history — read only' },
  { code: 'driver.assignment.read',     label: 'View driver assignments',       description: 'See current route assignments and driver availability for dispatch planning' },
  { code: 'sort.plan.read',             label: 'Read hub sort plan',            description: 'Access inbound manifests and sort algorithms for hub operations' },
]

const LOGISTICS_BLOCKED_OPS: LogisticsOp[] = [
  { code: 'route.bulk.override.unauth',              label: 'Unauthorized bulk reroute',           description: 'Rerouting more than 1,000 packages without supervisor approval — always prevented' },
  { code: 'customs.docs.auto.approve.suspicious',    label: 'Auto-approve flagged manifest',       description: 'Manifests with declared value discrepancies cannot be cleared by AI — always human review' },
  { code: 'tracking.data.bulk.export',               label: 'Bulk export customer data',           description: 'Mass export of shipment or customer location data to external endpoints — blocked' },
  { code: 'driver.hours.falsify',                    label: 'Falsify driver HOS records',          description: 'Modifying hours-of-service logs violates FMCSA — blocked under all conditions' },
  { code: 'rate.override.below.floor',               label: 'Set rate below contracted floor',     description: 'Freight rates cannot be set below the contractual floor price — revenue protection' },
  { code: 'signature.falsify',                       label: 'Fabricate delivery confirmation',     description: 'Creating false proof-of-delivery records constitutes fraud — always blocked' },
  { code: 'sanctions.check.bypass',                  label: 'Bypass OFAC sanctions screening',     description: 'OFAC/CBP screening cannot be skipped for any international or domestic shipment' },
  { code: 'safety.lockout.bypass',                   label: 'Bypass safety lockout procedure',     description: 'Overriding DOT-required safety lockouts on vehicles or equipment — blocked' },
]

const LOGISTICS_CONFIRM_OPS: LogisticsOp[] = [
  { code: 'route.emergency.reroute.critical',   label: 'Emergency mass reroute (>10k pkgs)',   description: 'Rerouting more than 10,000 packages due to infrastructure failure requires Ops Supervisor' },
  { code: 'customs.hold.release.highvalue',     label: 'Release high-value customs hold',      description: 'Clearing shipments above $50k value requires Compliance Officer approval' },
  { code: 'hub.critical.overflow.alert',        label: 'Authorize hub overflow diversion',     description: 'Diverting packages between hubs to manage capacity requires Hub Manager review' },
  { code: 'fraud.cluster.detected.escalate',   label: 'Lock chain of custody on route',       description: 'Freezing delivery operations on a suspected theft route requires Security Manager sign-off' },
  { code: 'supplier.failure.critical.alert',   label: 'Declare critical supplier failure',    description: 'Formally logging a supplier outage that affects 5%+ of volume triggers procurement review' },
]

const LOGISTICS_COMPLIANCE_STANDARDS = [
  { label: 'DOT FMCSA',   desc: 'Driver hours-of-service regulations' },
  { label: 'CBP Trade Act', desc: 'U.S. Customs & Border Protection' },
  { label: 'IATA DGR',    desc: 'Dangerous goods air transport rules' },
  { label: 'OFAC',        desc: 'Sanctions & embargoed country screening' },
  { label: 'C-TPAT',      desc: 'Cargo security partnership program' },
  { label: 'FCPA',        desc: 'Anti-bribery & anti-corruption' },
  { label: 'AES/EEI',     desc: 'Automated Export System declarations' },
]

const POLICY_PACKS = [
  {
    id: 'standard',
    name: 'Standard Operations Mode',
    active: true,
    description: 'Default governance for routine logistics. All agents operate within standard authority levels. Autonomous decisions up to $10k shipment value.',
    rules: ['Route optimization: autonomous up to 500 packages/batch', 'Customs: verify-only, no auto-approve', 'Dispatch: standard HOS enforcement', 'Pricing: ±5% floor variance allowed'],
    compliance: ['DOT FMCSA', 'CBP Trade Act', 'IATA DGR'],
    riskLevel: 'Standard',
    color: 'emerald',
  },
  {
    id: 'peak',
    name: 'Peak Season Override',
    active: false,
    description: 'Activated during high-volume surges (Black Friday, holiday season). Expands autonomous routing authority. Warehouse capacity limits relaxed. Enhanced monitoring active.',
    rules: ['Route optimization: autonomous up to 5,000 packages/batch', 'Hub overflow: auto-escalate at 90% capacity', 'Last mile: locker fallback auto-authorized', 'Pricing: ±8% floor variance allowed'],
    compliance: ['DOT FMCSA', 'CBP Trade Act'],
    riskLevel: 'Elevated',
    color: 'amber',
  },
  {
    id: 'international',
    name: 'International Compliance Mode',
    active: false,
    description: 'Cross-border shipment governance. Stricter customs documentation requirements. Sanctions screening mandatory on every decision. All high-value freight requires human review.',
    rules: ['Sanctions: OFAC + EU screening on every action', 'Customs: no autonomous approval above $500 declared value', 'AES/EEI filing: AI-assisted only, human signature required', 'High-value (>$50k): mandatory compliance officer review'],
    compliance: ['OFAC', 'EU Dual-Use Regulation', 'AES/EEI', 'C-TPAT', 'FCPA'],
    riskLevel: 'High',
    color: 'blue',
  },
  {
    id: 'emergency',
    name: 'Emergency Disruption Mode',
    active: false,
    description: 'Activated during natural disasters, infrastructure failures, or major supply chain disruptions. Maximizes operational flexibility while maintaining safety rails.',
    rules: ['Emergency rerouting: supervisor-approved bulk ops allowed', 'Hub overflow: dynamic capacity expansion authorized', 'Driver HOS: emergency variance with real-time tracking', 'All non-critical escalations: deferred to post-incident review'],
    compliance: ['DOT Emergency Declaration', 'FEMA Coordination Protocol'],
    riskLevel: 'Critical Override',
    color: 'red',
  },
  {
    id: 'highvalue',
    name: 'High-Value Freight Mode',
    active: false,
    description: 'For pharmaceutical, luxury, and sensitive cargo above $100k. Every routing change, customs action, and delivery confirmation requires human sign-off.',
    rules: ['All routing changes: ops supervisor approval required', 'Chain of custody: continuous cryptographic logging', 'Delivery: in-person signature + biometric verification', 'Anomaly threshold: 2x sensitivity, immediate escalation'],
    compliance: ['FDA Cold Chain', 'DEA Controlled Substance', 'Jewelers Block Protocol'],
    riskLevel: 'Maximum',
    color: 'violet',
  },
]

function PoliciesTab() {
  const [activePack, setActivePack]   = useState('standard')
  const [rules, setRules]             = useState<AgentRule[]>([])
  const [showForm, setShowForm]       = useState(false)
  const [agentScope, setAgentScope]   = useState('All agents')
  const [zoneScope, setZoneScope]     = useState('All zones')
  const [opCode, setOpCode]           = useState('')
  const [ruleAction, setRuleAction]   = useState<RuleAction>('allow')

  const allOps = [...LOGISTICS_ALLOWED_OPS, ...LOGISTICS_BLOCKED_OPS, ...LOGISTICS_CONFIRM_OPS]

  const blockSummary = Object.entries(
    ALL_EVENTS
      .filter(e => e.verdict === 'BLOCK' && e.reasonCode)
      .reduce<Record<string, { count: number; example: string }>>((acc, e) => {
        const key = e.reasonCode
        if (!acc[key]) acc[key] = { count: 0, example: e.toolOp }
        acc[key].count++
        return acc
      }, {})
  ).sort((a, b) => b[1].count - a[1].count).slice(0, 6)

  function addRule() {
    if (!opCode) return
    const op = allOps.find(o => o.code === opCode)
    if (!op) return
    setRules(prev => [...prev, {
      id: `rule-${Date.now()}`,
      agentScope, zone: zoneScope,
      operation: opCode, opLabel: op.label,
      action: ruleAction,
    }])
    setOpCode(''); setShowForm(false)
  }

  const actionColors: Record<RuleAction, { bg: string; text: string; border: string; label: string }> = {
    allow:   { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30', label: 'Allowed' },
    block:   { bg: 'bg-red-500/10',     text: 'text-red-400',     border: 'border-red-500/30',     label: 'Blocked' },
    confirm: { bg: 'bg-amber-500/10',   text: 'text-amber-400',   border: 'border-amber-500/30',   label: 'Confirm' },
  }

  const selectCls = 'w-full bg-secondary border border-white/10 rounded-xl px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-amber-500/30 transition-all'

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Policy Management</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Standard Operations Mode active · NexRoute Global Logistics · {ALL_AGENTS.length} agents enrolled
        </p>
      </div>

      {/* Active baseline */}
      <div className="glass-card p-4 flex items-center gap-3">
        <div className="w-8 h-8 rounded-xl bg-amber-500/15 flex items-center justify-center">
          <Shield className="w-4 h-4 text-amber-400" />
        </div>
        <div className="flex-1">
          <div className="text-sm font-semibold">Active Baseline: Standard Operations Mode</div>
          <div className="text-xs text-muted-foreground">Policy hash: a4f8c2e1 · Version v2.6.0 · Applied 14h ago · 521 agents governed</div>
        </div>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 font-semibold">LIVE</span>
      </div>

      {/* ── 3-column: What agents can/cannot do ── */}
      <div>
        <h2 className="text-sm font-semibold text-foreground mb-1">What agents can and cannot do</h2>
        <p className="text-xs text-muted-foreground mb-4">
          These rules apply to all {ALL_AGENTS.length} agents under the current Standard Operations policy pack.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Allowed */}
          <div className="glass-card p-4 border-emerald-500/20">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-emerald-500/15 flex items-center justify-center shrink-0">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-sm text-emerald-400 leading-tight">Agents can do this</h3>
                <p className="text-xs text-muted-foreground">No approval needed</p>
              </div>
              <span className="text-xs text-muted-foreground bg-emerald-500/10 px-2 py-0.5 rounded-full shrink-0">{LOGISTICS_ALLOWED_OPS.length}</span>
            </div>
            <div className="space-y-3.5">
              {LOGISTICS_ALLOWED_OPS.map(op => (
                <div key={op.code}>
                  <p className="text-xs font-medium text-foreground leading-tight">{op.label}</p>
                  <p className="text-xs text-muted-foreground/60 mt-0.5 leading-relaxed">{op.description}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Blocked */}
          <div className="glass-card p-4 border-red-500/20">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-red-500/15 flex items-center justify-center shrink-0">
                <XCircle className="w-3.5 h-3.5 text-red-400" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-sm text-red-400 leading-tight">Agents cannot do this</h3>
                <p className="text-xs text-muted-foreground">Always stopped — no exceptions</p>
              </div>
              <span className="text-xs text-muted-foreground bg-red-500/10 px-2 py-0.5 rounded-full shrink-0">{LOGISTICS_BLOCKED_OPS.length}</span>
            </div>
            <div className="space-y-3.5">
              {LOGISTICS_BLOCKED_OPS.map(op => (
                <div key={op.code}>
                  <p className="text-xs font-medium text-foreground leading-tight">{op.label}</p>
                  <p className="text-xs text-muted-foreground/60 mt-0.5 leading-relaxed">{op.description}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Confirm */}
          <div className="glass-card p-4 border-amber-500/20">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-amber-500/15 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-sm text-amber-400 leading-tight">Needs supervisor sign-off</h3>
                <p className="text-xs text-muted-foreground">Action paused pending human review</p>
              </div>
              <span className="text-xs text-muted-foreground bg-amber-500/10 px-2 py-0.5 rounded-full shrink-0">{LOGISTICS_CONFIRM_OPS.length}</span>
            </div>
            <div className="space-y-3.5">
              {LOGISTICS_CONFIRM_OPS.map(op => (
                <div key={op.code}>
                  <p className="text-xs font-medium text-foreground leading-tight">{op.label}</p>
                  <p className="text-xs text-muted-foreground/60 mt-0.5 leading-relaxed">{op.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── What's Being Blocked + Rule Builder ── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* What's Being Blocked */}
        <div className="lg:col-span-2 glass-card p-5 space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-foreground">What's Being Blocked</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Top block reasons across all agents · last 1,000 decisions</p>
          </div>
          <div className="space-y-3">
            {blockSummary.map(([code, info], i) => (
              <div key={code} className="flex items-start gap-3">
                <div className="w-5 h-5 rounded-full bg-red-500/15 border border-red-500/20 flex items-center justify-center shrink-0 mt-0.5">
                  <span className="text-[9px] font-bold text-red-400">{i + 1}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <p className="text-xs font-medium text-foreground/90 truncate">{code.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase())}</p>
                    <span className="text-xs font-mono text-red-400 shrink-0">{info.count}×</span>
                  </div>
                  <div className="h-1 bg-secondary rounded-full overflow-hidden">
                    <div className="h-full rounded-full bg-red-400/60 transition-all"
                      style={{ width: `${Math.min((info.count / (blockSummary[0]?.[1]?.count || 1)) * 100, 100)}%` }} />
                  </div>
                  <p className="text-[10px] text-muted-foreground/60 mt-0.5 truncate font-mono">{info.example}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Rule Builder */}
        <div className="lg:col-span-3 glass-card p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-foreground">Agent-Level Rule Builder</h2>
              <p className="text-xs text-muted-foreground mt-0.5">Add custom governance rules on top of the active policy pack</p>
            </div>
            <button onClick={() => setShowForm(!showForm)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all"
              style={{ background: showForm ? 'transparent' : 'hsl(38 95% 52% / 0.15)', color: 'hsl(38 95% 52%)', border: '1px solid hsl(38 95% 52% / 0.3)' }}>
              {showForm ? <X className="w-3 h-3" /> : <Plus className="w-3 h-3" />}
              {showForm ? 'Cancel' : 'Add Rule'}
            </button>
          </div>

          {/* Rule form */}
          <AnimatePresence>
            {showForm && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden">
                <div className="space-y-3 pt-1">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1.5">Agent Scope</label>
                      <select value={agentScope} onChange={e => setAgentScope(e.target.value)} className={selectCls}>
                        <option>All agents</option>
                        {(Object.keys(DEPTS) as DeptKey[]).map(k => (
                          <option key={k}>All {DEPTS[k].label} agents</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1.5">Zone Scope</label>
                      <select value={zoneScope} onChange={e => setZoneScope(e.target.value)} className={selectCls}>
                        <option>All zones</option>
                        {ZONES.map(z => <option key={z}>{z}</option>)}
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1.5">Operation</label>
                    <select value={opCode} onChange={e => setOpCode(e.target.value)} className={selectCls}>
                      <option value="">Select an operation…</option>
                      <optgroup label="Allowed Operations">
                        {LOGISTICS_ALLOWED_OPS.map(o => <option key={o.code} value={o.code}>{o.label}</option>)}
                      </optgroup>
                      <optgroup label="Blocked Operations">
                        {LOGISTICS_BLOCKED_OPS.map(o => <option key={o.code} value={o.code}>{o.label}</option>)}
                      </optgroup>
                      <optgroup label="Supervisor Confirm">
                        {LOGISTICS_CONFIRM_OPS.map(o => <option key={o.code} value={o.code}>{o.label}</option>)}
                      </optgroup>
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1.5">Governance Action</label>
                    <div className="flex gap-2">
                      {(['allow', 'block', 'confirm'] as RuleAction[]).map(a => {
                        const c = actionColors[a]
                        return (
                          <button key={a} onClick={() => setRuleAction(a)}
                            className={cn('flex-1 py-2 rounded-xl text-xs font-semibold border transition-all',
                              ruleAction === a ? cn(c.bg, c.text, c.border) : 'border-white/10 text-muted-foreground hover:text-foreground hover:bg-white/5')}>
                            {c.label}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                  <button onClick={addRule} disabled={!opCode}
                    className="w-full py-2.5 rounded-xl text-sm font-semibold transition-all disabled:opacity-40"
                    style={{ background: 'hsl(38 95% 52%)', color: 'hsl(20 10% 8%)' }}>
                    Add Rule to Policy
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Rules list */}
          {rules.length === 0 ? (
            <div className="rounded-xl border border-dashed border-white/15 py-8 text-center">
              <p className="text-sm text-muted-foreground">No custom rules yet</p>
              <p className="text-xs text-muted-foreground/60 mt-1">Click "Add Rule" to layer custom governance on top of the active policy</p>
            </div>
          ) : (
            <div className="space-y-2">
              {rules.map(rule => {
                const c = actionColors[rule.action]
                return (
                  <div key={rule.id} className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2.5">
                    <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full border font-semibold shrink-0', c.bg, c.text, c.border)}>
                      {c.label}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-foreground font-medium truncate">{rule.opLabel}</p>
                      <p className="text-[10px] text-muted-foreground">{rule.agentScope} · {rule.zone}</p>
                    </div>
                    <button onClick={() => setRules(prev => prev.filter(r => r.id !== rule.id))}
                      className="text-muted-foreground hover:text-red-400 transition-colors shrink-0">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Compliance Standards Grid */}
      <div>
        <h2 className="text-sm font-semibold text-foreground mb-3">Regulatory Compliance Coverage</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
          {LOGISTICS_COMPLIANCE_STANDARDS.map(std => (
            <div key={std.label} className="glass-card p-3 text-center space-y-1">
              <div className="w-6 h-6 rounded-full bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center mx-auto">
                <CheckCircle className="w-3 h-3 text-emerald-400" />
              </div>
              <div className="text-xs font-bold text-foreground">{std.label}</div>
              <div className="text-[10px] text-muted-foreground leading-snug">{std.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Policy Packs */}
      <div>
        <h2 className="text-sm font-semibold text-foreground mb-3">Policy Packs</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {POLICY_PACKS.map(pack => {
            const isActive = activePack === pack.id
            const borderColor = {
              emerald: 'border-emerald-500/40', amber: 'border-amber-500/40',
              blue: 'border-blue-500/40', red: 'border-red-500/40', violet: 'border-violet-500/40',
            }[pack.color]
            const accentColor = {
              emerald: 'text-emerald-400', amber: 'text-amber-400',
              blue: 'text-blue-400', red: 'text-red-400', violet: 'text-violet-400',
            }[pack.color]
            const bgColor = {
              emerald: 'bg-emerald-500/10', amber: 'bg-amber-500/10',
              blue: 'bg-blue-500/10', red: 'bg-red-500/10', violet: 'bg-violet-500/10',
            }[pack.color]
            return (
              <div key={pack.id}
                className={cn('glass-card p-5 space-y-4 border-2 transition-all cursor-pointer', isActive ? borderColor : 'border-border/30 hover:border-border/60')}
                onClick={() => setActivePack(pack.id)}>
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className={cn('text-sm font-semibold', accentColor)}>{pack.name}</span>
                      {pack.active && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">ACTIVE</span>}
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">{pack.description}</p>
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Governance Rules</div>
                  {pack.rules.map(r => (
                    <div key={r} className="flex items-start gap-1.5">
                      <ChevronRight className={cn('w-3 h-3 mt-0.5 flex-shrink-0', accentColor)} />
                      <span className="text-[11px] text-foreground/80">{r}</span>
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-between pt-1">
                  <div className="flex flex-wrap gap-1">
                    {pack.compliance.map(c => (
                      <span key={c} className={cn('text-[10px] px-1.5 py-0.5 rounded border font-mono', bgColor, accentColor)}>{c}</span>
                    ))}
                  </div>
                  <span className={cn('text-[10px] font-semibold', accentColor)}>{pack.riskLevel}</span>
                </div>
                {isActive && (
                  <button onClick={e => { e.stopPropagation(); alert(`Policy "${pack.name}" applied. Hash recorded in audit vault.`) }}
                    className={cn('w-full py-2 rounded-lg text-xs font-semibold transition-all', bgColor, accentColor, 'border', borderColor)}>
                    Apply This Policy Pack
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ─── Review Queue Tab ─────────────────────────────────────────────────────────

type ReviewStatus = 'pending' | 'approved' | 'rejected'

const REVIEW_ITEMS: Array<{
  id: string; title: string; agent: string; dept: DeptKey; shipmentId: string; action: string;
  reason: string; context: string; riskScore: number; priority: 'critical' | 'urgent'; ts: Date;
  status: ReviewStatus; supervisor: string;
}> = [
  {
    id: 'RVW-001',
    title: 'Emergency Mass Reroute — I-40 Closure',
    agent: 'PathFinder-7', dept: 'routing',
    shipmentId: 'SHP-82341', action: 'route.emergency.reroute.critical',
    reason: 'Agent requests bulk reroute of 47,200 packages across 6 hub corridors. I-40 closure at mile marker 287 (vehicle accident). Estimated 18h delay on current route.',
    context: 'Hurricane-adjacent road closure. Memphis hub at 91% capacity. Alternate route adds $0.38/package in fuel cost.',
    riskScore: 0.71, priority: 'critical', ts: new Date(Date.now() - 900000),
    status: 'pending', supervisor: 'Ops Supervisor — Region 4',
  },
  {
    id: 'RVW-002',
    title: 'Customs Hold Release — Pharmaceutical Shipment',
    agent: 'TradeClear-3', dept: 'customs',
    shipmentId: 'SHP-61097', action: 'customs.hold.release.highvalue',
    reason: 'LAX customs flagged pharmaceutical manifest for declared value discrepancy. Shipper has provided corrected documentation. Agent requests release of $2.4M cold-chain shipment.',
    context: 'Temperature-sensitive cargo. 6h hold window remaining before cold chain integrity compromised. Legal counsel on call.',
    riskScore: 0.68, priority: 'critical', ts: new Date(Date.now() - 3600000),
    status: 'pending', supervisor: 'Compliance Officer',
  },
  {
    id: 'RVW-003',
    title: 'Theft Cluster — Chain of Custody Lock (Route 7-LA)',
    agent: 'TrackAI-2', dept: 'tracking',
    shipmentId: 'SHP-44782', action: 'chain.of.custody.break.declare',
    reason: '23 sequential delivery confirmations on Route 7-LA without physical scan. Anomaly Detection flagged as potential theft cluster. Agent requests chain-of-custody lockdown on 8 high-value packages.',
    context: 'Similar pattern detected on same route 3 weeks ago. Security team has been notified. 8 packages valued at $340k total.',
    riskScore: 0.82, priority: 'critical', ts: new Date(Date.now() - 1800000),
    status: 'pending', supervisor: 'Security Manager',
  },
  {
    id: 'RVW-004',
    title: 'Hub Overflow — Memphis Sort Facility',
    agent: 'SortPlan-Alpha', dept: 'hub',
    shipmentId: 'SHP-39105', action: 'hub.critical.overflow.alert',
    reason: 'Memphis hub at 96% capacity due to Black Friday surge. Agent requests authorization to divert 8,400 packages to Nashville and Little Rock hubs.',
    context: 'Black Friday surge. Nashville hub at 78% capacity — has headroom. Diversion adds ~40 min avg delivery time.',
    riskScore: 0.58, priority: 'urgent', ts: new Date(Date.now() - 7200000),
    status: 'approved', supervisor: 'Hub Ops Manager',
  },
  {
    id: 'RVW-005',
    title: 'Critical Supplier Failure — DHL Ground Partner',
    agent: 'SupplierAI-1', dept: 'supplychain',
    shipmentId: 'SHP-71234', action: 'supplier.failure.critical.alert',
    reason: 'DHL Ground partner has declared force majeure for 3 SE states. 18,400 packages affected. Agent requests formal supplier failure declaration to trigger backup carrier contracts.',
    context: 'Backup carrier capacity confirmed available at 12% premium. SLA risk: 4,200 packages will breach 2-day delivery SLA if not acted on within 4h.',
    riskScore: 0.74, priority: 'urgent', ts: new Date(Date.now() - 5400000),
    status: 'pending', supervisor: 'Supply Chain Director',
  },
]

function ReviewQueueTab() {
  const [decisions, setDecisions] = useState<Record<string, 'approved' | 'rejected'>>({})
  const [notes, setNotes]         = useState<Record<string, string>>({})
  const [confirmItem, setConfirmItem] = useState<typeof REVIEW_ITEMS[0] | null>(null)
  const [confirmVerdict, setConfirmVerdict] = useState<'approved' | 'rejected' | null>(null)
  const [confirming, setConfirming]   = useState(false)

  function requestDecision(id: string, verdict: 'approved' | 'rejected') {
    const item = REVIEW_ITEMS.find(r => r.id === id)
    if (!item) return
    setConfirmItem(item)
    setConfirmVerdict(verdict)
  }

  async function finalizeDecision() {
    if (!confirmItem || !confirmVerdict) return
    setConfirming(true)
    await new Promise(r => setTimeout(r, 500))
    setDecisions(d => ({ ...d, [confirmItem.id]: confirmVerdict }))
    setConfirming(false)
    setConfirmItem(null)
    setConfirmVerdict(null)
  }

  const criticalItems = REVIEW_ITEMS.filter(r => r.priority === 'critical')
  const urgentItems   = REVIEW_ITEMS.filter(r => r.priority === 'urgent')
  const pendingCount  = REVIEW_ITEMS.filter(r => r.status === 'pending' && !decisions[r.id]).length
  const reviewedThisSession = Object.keys(decisions)

  return (
    <div className="space-y-5">
      {/* Header banner */}
      <div className="glass-card p-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse-dot" />
          <span className="text-sm font-semibold">{pendingCount} actions pending ops supervisor review</span>
        </div>
        <div className="flex gap-3 text-xs text-muted-foreground">
          <span className="text-emerald-400">{Object.values(decisions).filter(d => d === 'approved').length} approved this session</span>
          <span>·</span>
          <span className="text-red-400">{Object.values(decisions).filter(d => d === 'rejected').length} rejected</span>
          <span>·</span>
          <span>{REVIEW_ITEMS.filter(r => r.status === 'approved').length} pre-resolved</span>
        </div>
      </div>

      {/* Critical group */}
      {criticalItems.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-red-400 animate-pulse" />
            <h2 className="text-sm font-semibold text-red-400">Critical — Immediate Action Required</h2>
            <span className="text-xs text-muted-foreground bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded-full">{criticalItems.length} items</span>
          </div>
          <div className="space-y-4">
            {criticalItems.map(item => <ReviewCard key={item.id} item={item} localDecision={decisions[item.id]} note={notes[item.id] ?? ''} onNote={v => setNotes(n => ({ ...n, [item.id]: v }))} onDecide={requestDecision} />)}
          </div>
        </div>
      )}

      {/* Urgent group */}
      {urgentItems.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-amber-400" />
            <h2 className="text-sm font-semibold text-amber-400">Urgent — Action Required Today</h2>
            <span className="text-xs text-muted-foreground bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full">{urgentItems.length} items</span>
          </div>
          <div className="space-y-4">
            {urgentItems.map(item => <ReviewCard key={item.id} item={item} localDecision={decisions[item.id]} note={notes[item.id] ?? ''} onNote={v => setNotes(n => ({ ...n, [item.id]: v }))} onDecide={requestDecision} />)}
          </div>
        </div>
      )}

      {/* Reviewed this session */}
      {reviewedThisSession.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground">Reviewed This Session</h2>
          <div className="glass-card divide-y divide-border/30">
            {reviewedThisSession.map(id => {
              const item = REVIEW_ITEMS.find(r => r.id === id)
              if (!item) return null
              const verdict = decisions[id]
              return (
                <div key={id} className="flex items-center gap-3 px-4 py-3">
                  <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full border font-semibold shrink-0',
                    verdict === 'approved' ? 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10' : 'border-red-500/30 text-red-400 bg-red-500/10')}>
                    {verdict === 'approved' ? '✓ Approved' : '✗ Rejected'}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-foreground/80 truncate">{item.title}</p>
                    <p className="text-[10px] text-muted-foreground">{item.agent} · {item.shipmentId} · {timeAgo(item.ts)}</p>
                  </div>
                  {notes[id] && (
                    <p className="text-[10px] text-muted-foreground/60 italic truncate max-w-[180px] hidden md:block">"{notes[id]}"</p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Confirm Modal */}
      <AnimatePresence>
        {confirmItem && confirmVerdict && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => { setConfirmItem(null); setConfirmVerdict(null) }}>
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
            <motion.div
              initial={{ opacity: 0, scale: 0.94, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.94, y: 16 }}
              transition={{ type: 'spring', damping: 22, stiffness: 300 }}
              onClick={e => e.stopPropagation()}
              className="relative glass-card w-full max-w-md p-6 z-10">
              <button onClick={() => { setConfirmItem(null); setConfirmVerdict(null) }}
                className="absolute top-4 right-4 p-1.5 rounded-lg hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors">
                <X className="w-4 h-4" />
              </button>
              <div className="flex items-center gap-3 mb-4">
                <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center',
                  confirmVerdict === 'approved' ? 'bg-emerald-500/15' : 'bg-red-500/15')}>
                  {confirmVerdict === 'approved'
                    ? <CheckCircle className="w-5 h-5 text-emerald-400" />
                    : <XCircle className="w-5 h-5 text-red-400" />}
                </div>
                <div>
                  <h3 className="text-base font-semibold">
                    {confirmVerdict === 'approved' ? 'Approve Action?' : 'Reject Action?'}
                  </h3>
                  <p className="text-xs text-muted-foreground">This decision will be logged in the governance audit trail</p>
                </div>
              </div>
              {/* Summary */}
              <div className="rounded-xl border border-white/10 bg-secondary/30 px-3 py-2.5 space-y-1.5 mb-4">
                <p className="text-sm font-semibold text-foreground">{confirmItem.title}</p>
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                  <span className={cn(DEPT_COLORS[confirmItem.dept])}><DeptIcon dept={confirmItem.dept} className="w-3 h-3 inline mr-0.5" /></span>
                  <span>{confirmItem.agent}</span>
                  <span>·</span>
                  <span className="font-mono">{confirmItem.shipmentId}</span>
                  <span>·</span>
                  <span>Risk {(confirmItem.riskScore * 100).toFixed(0)}/100</span>
                </div>
              </div>
              <div className={cn('rounded-xl border px-3 py-2.5 text-xs mb-5',
                confirmVerdict === 'approved'
                  ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-300'
                  : 'border-red-500/20 bg-red-500/5 text-red-300')}>
                {confirmVerdict === 'approved'
                  ? `Approving will authorize ${confirmItem.agent} to execute "${confirmItem.action}". This action will be logged under your credentials.`
                  : `Rejecting will halt "${confirmItem.action}" and notify ${confirmItem.supervisor}. The agent will not be able to retry without a new escalation.`}
              </div>
              <div className="flex items-center gap-2">
                <button onClick={finalizeDecision} disabled={confirming}
                  className={cn('flex-1 py-2.5 rounded-xl text-sm font-semibold transition-all disabled:opacity-40 flex items-center justify-center gap-2',
                    confirmVerdict === 'approved' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30' : 'bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30')}>
                  {confirming
                    ? <><div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" /> Processing…</>
                    : confirmVerdict === 'approved' ? <><CheckCircle className="w-4 h-4" /> Confirm Approve</> : <><XCircle className="w-4 h-4" /> Confirm Reject</>}
                </button>
                <button onClick={() => { setConfirmItem(null); setConfirmVerdict(null) }}
                  className="px-4 py-2.5 rounded-xl border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors">
                  Cancel
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}

function ReviewCard({
  item, localDecision, note, onNote, onDecide,
}: {
  item: typeof REVIEW_ITEMS[0]
  localDecision: 'approved' | 'rejected' | undefined
  note: string
  onNote: (v: string) => void
  onDecide: (id: string, verdict: 'approved' | 'rejected') => void
}) {
  const finalStatus = (localDecision ?? item.status) as ReviewStatus
  return (
    <div className={cn('glass-card p-5 space-y-4', finalStatus !== 'pending' && 'opacity-75')}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className={cn('w-2 h-2 rounded-full mt-1.5 flex-shrink-0',
            item.priority === 'critical' ? 'bg-red-400' : 'bg-amber-400')} />
          <div>
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-sm font-semibold">{item.title}</span>
              <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full border font-semibold',
                item.priority === 'critical' ? 'border-red-500/30 text-red-400 bg-red-500/10' : 'border-amber-500/30 text-amber-400 bg-amber-500/10')}>
                {item.priority.toUpperCase()}
              </span>
            </div>
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground flex-wrap">
              <span className={cn(DEPT_COLORS[item.dept])}><DeptIcon dept={item.dept} className="w-3 h-3 inline mr-0.5" /></span>
              <span>{item.agent}</span><span>·</span>
              <span className="font-mono">{item.shipmentId}</span><span>·</span>
              <span>{timeAgo(item.ts)}</span>
            </div>
          </div>
        </div>
        {finalStatus === 'pending' ? (
          <div className="flex gap-2 flex-shrink-0">
            <button onClick={() => onDecide(item.id, 'approved')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25 transition-colors">
              <CheckCircle className="w-3.5 h-3.5" />Approve
            </button>
            <button onClick={() => onDecide(item.id, 'rejected')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25 transition-colors">
              <XCircle className="w-3.5 h-3.5" />Reject
            </button>
          </div>
        ) : (
          <span className={cn('text-xs px-2 py-1 rounded-full border font-semibold shrink-0',
            finalStatus === 'approved' ? 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10' : 'border-red-500/30 text-red-400 bg-red-500/10')}>
            {finalStatus === 'approved' ? '✓ Approved' : '✗ Rejected'}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-semibold">Agent Request</div>
          <p className="text-xs text-foreground/80 leading-relaxed">{item.reason}</p>
        </div>
        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-semibold">Operational Context</div>
          <p className="text-xs text-foreground/80 leading-relaxed">{item.context}</p>
        </div>
      </div>

      <div className="flex items-center justify-between pt-1 border-t border-border/40">
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground flex-wrap">
          <span>Risk: <span className={item.riskScore > 0.7 ? 'text-red-400' : 'text-amber-400'}>{(item.riskScore * 100).toFixed(0)}/100</span></span>
          <span>·</span>
          <span className="font-mono">{item.action}</span>
          <span>·</span>
          <span>{item.supervisor}</span>
        </div>
        {finalStatus === 'pending' && (
          <input value={note} onChange={e => onNote(e.target.value)}
            placeholder="Add decision note..."
            className="px-2 py-1 rounded text-[10px] bg-secondary/60 border border-border outline-none focus:border-amber-500/40 text-foreground w-48" />
        )}
      </div>
    </div>
  )
}

// ─── AI Chat Panel ────────────────────────────────────────────────────────────

function AIChatPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [msgs, setMsgs] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: "Hello! I'm EDON's logistics governance assistant. I can answer questions about NexRoute's AI agent activity, policy compliance, decision patterns, fleet status, or any cross-agent incidents. What would you like to know?",
      ts: new Date(),
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [msgs])

  const CANNED: Record<string, string> = {
    'block': `In the last 1,000 decisions, EDON blocked **${ALL_EVENTS.filter(e=>e.verdict==='BLOCK').length} operations** across the NexRoute fleet. Top block reasons: UNAUTHORIZED_REROUTE, DATA_EXFILTRATION, SAFETY_BREACH, and RATE_MANIPULATION. Customs & Trade and Anomaly Detection have the highest per-agent block rates.`,
    'hurricane': `EDON detected and managed the Hurricane Ian disruption chain (SHP-82341). DemandAI-1 escalated the surge alert, PathFinder-7 requested emergency reroute (escalated to Ops Supervisor), FleetBot-1's unauthorized bulk dispatch was blocked, and HubOps-6 expanded Memphis hub capacity. The incident affected 47,200 packages across 6 corridors.`,
    'customs': `The pharmaceutical customs hold (SHP-61097) is still active. TradeClear-3 blocked the auto-approval due to a 40% declared value discrepancy. Warehouse outbound is frozen, freight invoice is held, and the Compliance Officer has an escalation in the review queue. The cold-chain window closes in ~6 hours.`,
    'latency': `Current P50 decision latency is **7ms**, P99 is under 22ms. ALLOW decisions average 6ms, BLOCK decisions average 12ms (additional policy evaluation), and ESCALATE decisions route within 1 second to the supervisor queue. All within SLA.`,
    'agents': `NexRoute has **${ALL_AGENTS.length} AI agents** enrolled across 12 operational departments. ${ALL_AGENTS.filter(a=>a.status==='active').length} are active, ${ALL_AGENTS.filter(a=>a.status==='idle').length} idle, ${ALL_AGENTS.filter(a=>a.status==='alert').length} on alert. Tracking has the largest fleet (80 agents), followed by Warehouse Ops (65) and Last Mile Delivery (55).`,
  }

  async function sendMessage() {
    if (!input.trim() || loading) return
    const userMsg: ChatMessage = { role: 'user', content: input.trim(), ts: new Date() }
    setMsgs(m => [...m, userMsg])
    setInput('')
    setLoading(true)

    await new Promise(r => setTimeout(r, 900))

    const lower = input.toLowerCase()
    let reply = "I can help with that. Based on current NexRoute governance data: block rates are within normal operating range, all active cross-agent chains are being monitored, and the review queue has items awaiting supervisor decision. Try asking about specific incidents, agent status, or policy configurations."
    for (const [key, val] of Object.entries(CANNED)) {
      if (lower.includes(key)) { reply = val; break }
    }

    setMsgs(m => [...m, { role: 'assistant', content: reply, ts: new Date() }])
    setLoading(false)
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
          transition={{ type: 'spring', damping: 28, stiffness: 300 }}
          className="fixed right-0 top-0 bottom-0 w-80 z-50 glass-card rounded-none flex flex-col border-l border-border"
          style={{ borderLeft: '1px solid hsl(var(--border))' }}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-amber-400" />
              <span className="text-sm font-semibold">EDON Assistant</span>
            </div>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
              <XCircle className="w-4 h-4" />
            </button>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
            {msgs.map((m, i) => (
              <div key={i} className={cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
                <div className={cn('max-w-[85%] rounded-xl px-3 py-2 text-xs leading-relaxed',
                  m.role === 'user'
                    ? 'bg-amber-500/20 text-foreground border border-amber-500/30'
                    : 'bg-muted/40 text-foreground/90 border border-border/40')}>
                  {m.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-muted/40 border border-border/40 rounded-xl px-3 py-2 text-xs text-muted-foreground">
                  Analyzing governance data...
                </div>
              </div>
            )}
          </div>

          <div className="p-3 border-t border-border/50">
            <div className="flex gap-2 mb-2 flex-wrap">
              {['block rates', 'hurricane', 'customs hold', 'agents'].map(s => (
                <button key={s} onClick={() => setInput(s)}
                  className="text-[10px] px-2 py-0.5 rounded-full border border-border hover:border-amber-500/40 text-muted-foreground hover:text-foreground transition-colors">
                  {s}
                </button>
              ))}
            </div>
            <form onSubmit={e => { e.preventDefault(); sendMessage() }} className="flex gap-2">
              <input value={input} onChange={e => setInput(e.target.value)}
                placeholder="Ask about decisions, agents, policies..."
                className="flex-1 px-3 py-2 rounded-lg text-xs bg-secondary/60 border border-border outline-none focus:border-amber-500/40 text-foreground" />
              <button type="submit" disabled={!input.trim() || loading}
                className="p-2 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30 transition-colors disabled:opacity-40">
                <Send className="w-3.5 h-3.5" />
              </button>
            </form>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ─── Top Nav ──────────────────────────────────────────────────────────────────

type TabId = 'dashboard' | 'agents' | 'audit' | 'policies' | 'review'

function TopNav({ tab, setTab, chatOpen, setChatOpen, onLogout }: {
  tab: TabId
  setTab: (t: TabId) => void
  chatOpen: boolean
  setChatOpen: (v: boolean) => void
  onLogout: () => void
}) {
  const [theme, setTheme] = useState<'dark' | 'light'>(
    document.documentElement.classList.contains('light') ? 'light' : 'dark'
  )

  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    document.documentElement.classList.remove('dark', 'light')
    document.documentElement.classList.add(next)
    localStorage.setItem('edon_theme', next)
  }

  const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: 'dashboard', label: 'Dashboard',    icon: <TrendingUp className="w-3.5 h-3.5" /> },
    { id: 'agents',    label: 'Agent Fleet',  icon: <Bot className="w-3.5 h-3.5" /> },
    { id: 'audit',     label: 'Audit Trail',  icon: <Layers className="w-3.5 h-3.5" /> },
    { id: 'policies',  label: 'Policies',     icon: <Shield className="w-3.5 h-3.5" /> },
    { id: 'review',    label: 'Ops Review',   icon: <Users className="w-3.5 h-3.5" /> },
  ]

  const pendingReviews = REVIEW_ITEMS.filter(r => r.status === 'pending').length

  return (
    <nav className="sticky top-0 z-40 border-b border-border/50 bg-background/80 backdrop-blur-xl">
      <div className="max-w-screen-xl mx-auto px-4">
        <div className="flex items-center gap-4 h-14">
          {/* Logo */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'hsl(38 95% 52% / 0.2)', border: '1px solid hsl(38 95% 52% / 0.4)' }}>
              <Truck className="w-4 h-4" style={{ color: 'hsl(38 95% 52%)' }} />
            </div>
            <div className="hidden sm:block">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-bold tracking-[0.15em] text-foreground/90">EDON</span>
                <span className="text-xs text-muted-foreground/50">·</span>
                <span className="text-xs font-semibold" style={{ color: 'hsl(38 95% 52%)' }}>Logistics</span>
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex items-center gap-1 flex-1 overflow-x-auto">
            {tabs.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={cn('nav-item relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium flex-shrink-0 transition-all', tab === t.id && 'nav-item-active text-foreground')}>
                {t.icon}{t.label}
                {t.id === 'review' && pendingReviews > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-amber-500 text-[9px] font-bold text-black flex items-center justify-center">{pendingReviews}</span>
                )}
              </button>
            ))}
          </div>

          {/* Right */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="hidden md:flex items-center gap-1.5 text-[10px] text-muted-foreground px-2 py-1 rounded-lg bg-muted/30">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot" />
              <span>521 agents · 7ms</span>
            </div>
            <button onClick={() => setChatOpen(!chatOpen)}
              className={cn('p-1.5 rounded-lg transition-colors', chatOpen ? 'bg-amber-500/20 text-amber-400' : 'text-muted-foreground hover:text-foreground hover:bg-muted/40')}>
              <MessageSquare className="w-4 h-4" />
            </button>
            <button onClick={toggleTheme} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors">
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            <button onClick={onLogout} className="p-1.5 rounded-lg text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </nav>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [unlocked, setUnlocked]   = useState(() => sessionStorage.getItem('edon_logistics_unlocked') === '1')
  const [tab, setTab]             = useState<TabId>('dashboard')
  const [chatOpen, setChatOpen]   = useState(false)
  const [liveMode, setLiveMode]   = useState(true)
  const [events, setEvents]       = useState<LogisticsEvent[]>(ALL_EVENTS)
  const [tick, setTick]           = useState(0)
  const tickRef = useRef(tick)
  tickRef.current = tick

  const toggleLive = useCallback(() => setLiveMode(m => !m), [])

  useEffect(() => {
    if (!liveMode) return
    const interval = setInterval(() => {
      setTick(t => t + 1)
      setEvents(prev => {
        const base = ALL_EVENTS[tickRef.current % ALL_EVENTS.length]
        const fresh: LogisticsEvent = {
          ...base,
          id: `LVE-${Date.now()}`,
          ts: new Date(),
          hash: Math.random().toString(36).slice(2, 18),
        }
        return [...prev.slice(-999), fresh]
      })
    }, 2800)
    return () => clearInterval(interval)
  }, [liveMode])

  function handleUnlock() {
    sessionStorage.setItem('edon_logistics_unlocked', '1')
    setUnlocked(true)
  }

  function handleLogout() {
    sessionStorage.removeItem('edon_logistics_unlocked')
    setUnlocked(false)
  }

  if (!unlocked) return <LogisticsAccessGate onUnlock={handleUnlock} />

  return (
    <div className="min-h-screen bg-background">
      <TopNav tab={tab} setTab={setTab} chatOpen={chatOpen} setChatOpen={setChatOpen} onLogout={handleLogout} />

      <main className="max-w-screen-xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-1">
            <Building2 className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">NexRoute Global Logistics · EDON AI Governance</span>
            <span className="text-xs text-muted-foreground/40">·</span>
            <span className="text-xs text-emerald-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot inline-block" />All systems operational
            </span>
          </div>
          <h1 className="text-xl font-bold text-foreground">
            {tab === 'dashboard' ? 'Operations Command Center'
              : tab === 'agents' ? 'AI Agent Fleet'
              : tab === 'audit' ? 'Governance Audit Trail'
              : tab === 'policies' ? 'Policy Management'
              : 'Ops Supervisor Review Queue'}
          </h1>
        </div>

        {/* Tab Content */}
        <AnimatePresence mode="wait">
          <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
            {tab === 'dashboard'  && <DashboardTab events={events} liveMode={liveMode} onToggleLive={toggleLive} />}
            {tab === 'agents'    && <AgentsTab />}
            {tab === 'audit'     && <AuditTab events={events} />}
            {tab === 'policies'  && <PoliciesTab />}
            {tab === 'review'    && <ReviewQueueTab />}
          </motion.div>
        </AnimatePresence>
      </main>

      <AIChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />

      {/* Overlay for chat on mobile */}
      {chatOpen && (
        <div className="fixed inset-0 bg-black/40 z-40 md:hidden" onClick={() => setChatOpen(false)} />
      )}
    </div>
  )
}
