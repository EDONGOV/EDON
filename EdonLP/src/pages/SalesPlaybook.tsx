import Navigation from "@/components/Navigation";
import ScrollToTop from "@/components/ScrollToTop";

const stages = [
  {
    stage: "01",
    title: "Lead comes in",
    tag: "Inbound",
    color: "bg-blue-50 border-blue-100",
    tagColor: "bg-blue-100 text-blue-700",
    steps: [
      "Demo request lands at charlie@edoncore.com with full intake form answers",
      "Review their agent type, fleet size, use case, and primary challenge within 2 hours",
      "Research the company: what agents are they likely running, what regulations apply, what's their risk surface",
      "Identify their buyer type: CTO (technical), Head of AI (operational), or Compliance/Legal (regulatory)",
    ],
    action: "Reply within 24h to confirm Zoom. Include 2-3 time slots.",
  },
  {
    stage: "02",
    title: "Pre-demo prep",
    tag: "Internal",
    color: "bg-gray-50 border-gray-200",
    tagColor: "bg-gray-200 text-gray-700",
    steps: [
      "Build a tailored demo environment: configure agents that resemble their use case (e.g. logistics → route update agents, healthcare → data access agents)",
      "Pre-load 3-5 policy scenarios relevant to their use case and challenge",
      "Prepare 2 rogue scenarios: one obvious block, one subtle drift/boundary-probe that EDON catches",
      "Know their pain point cold — open with it, close with it",
      "Prepare ROI framing: what does one rogue agent incident cost them vs EDON monthly",
    ],
    action: "Send a 1-line calendar invite with Zoom link. No agenda doc needed — keep it lean.",
  },
  {
    stage: "03",
    title: "The demo (45 min)",
    tag: "Zoom",
    color: "bg-black border-black",
    tagColor: "bg-white/20 text-white",
    dark: true,
    steps: [
      "[0–5 min] Ask: What made you book this? What does governance look like for you today? Let them talk.",
      "[5–10 min] Frame the problem back to them — don't pitch yet. 'So you have agents doing X but no way to know when they go off-policy.' Get them nodding.",
      "[10–30 min] Live demo: show EDON govern an agent that looks like theirs. Walk through allow → block → escalate. Show the audit trail. Then trigger a rogue scenario and show EDON catch it.",
      "[30–38 min] Show the control plane: one place, all agents, fleet monitoring, behavioral baselines. Show an agent being contained in real time.",
      "[38–43 min] Fleet learning moment: 'Every decision EDON makes trains the model. The more you use it, the better it gets at predicting your specific risk surface.'",
      "[43–45 min] Close: 'Does this solve the problem you came in with?' Then ask: 'What would need to be true for you to move forward?'",
    ],
    action: "End on a specific next step — not 'I'll send you info.' Get a date for the follow-up.",
  },
  {
    stage: "04",
    title: "Post-demo follow-up",
    tag: "Sales",
    color: "bg-amber-50 border-amber-100",
    tagColor: "bg-amber-100 text-amber-700",
    steps: [
      "Send follow-up email within 2 hours: one paragraph, what you showed, what their specific problem was, one line on pricing, next step",
      "Attach nothing except a link to edoncore.com/pricing if they asked about cost",
      "Common objection: 'We need to get our team involved' → Great. Offer to do a second demo for their team, same format",
      "Common objection: 'We're evaluating other tools' → Ask what the others are. EDON's differentiator is runtime governance + fleet learning. Others do logging. We govern.",
      "Common objection: 'How long to integrate?' → One API call. You could be live today.",
    ],
    action: "Confirm the next call date in the follow-up email. Don't leave it open-ended.",
  },
  {
    stage: "05",
    title: "Negotiation and terms",
    tag: "Commercial",
    color: "bg-purple-50 border-purple-100",
    tagColor: "bg-purple-100 text-purple-700",
    steps: [
      "Start with their fleet size and risk profile — price scales with both",
      "Offer a 30-day pilot for enterprise: one use case, one agent type, full governance on. They pay at the end if they see value.",
      "Get their legal/procurement involved early — don't let it stall at signature stage",
      "Key contract points to nail: data residency, SLA on decision latency, audit log retention period, dedicated vs shared tenant",
      "Never discount the platform — offer more in terms of onboarding support, custom policy configuration, or dedicated Slack channel instead",
    ],
    action: "Get a signed order form or SOW before provisioning anything.",
  },
  {
    stage: "06",
    title: "Customer provisioning",
    tag: "Onboarding",
    color: "bg-emerald-50 border-emerald-100",
    tagColor: "bg-emerald-100 text-emerald-700",
    steps: [
      "Provision their tenant in the EDON gateway — dedicated tenant ID, API key, and governance endpoint",
      "Send their credentials: API token, gateway URL, link to integration docs at edoncore.com/build",
      "Schedule a 30-minute technical onboarding call: walk their dev team through the first agent integration live",
      "Configure their first policy pack together on the call — don't leave it to them",
      "Set up their dashboard access and walk them through the control plane",
      "Set a 7-day check-in: 'How many agents are live? Any decisions surprising you?'",
    ],
    action: "First agent should be live within 48 hours of provisioning. If it's not, chase.",
  },
  {
    stage: "07",
    title: "90-day success",
    tag: "Retention",
    color: "bg-gray-50 border-gray-200",
    tagColor: "bg-gray-200 text-gray-700",
    steps: [
      "Week 1: first agent live, first decisions streaming, first policy enforcement event",
      "Week 2: review their audit trail with them — show them something interesting EDON caught",
      "Month 1: fleet learning is running, behavioral baselines are established — show them the drift/prediction data",
      "Month 2: expand to a second use case or agent type",
      "Month 3: QBR — what did EDON prevent, what did it log, what does their risk profile look like now vs day 1. This is your expansion conversation.",
    ],
    action: "Expansion ask comes at the month 3 QBR — never sooner, always from data.",
  },
];

const objections = [
  {
    q: "We already have logging.",
    a: "Logging tells you what happened. EDON governs what happens — before it's too late to stop it. That's a fundamentally different layer.",
  },
  {
    q: "Our agents are well-behaved.",
    a: "They are — today. EDON is the system that ensures they stay that way at scale, as they adapt, and as your fleet grows. Governance is cheapest before something goes wrong.",
  },
  {
    q: "We'll build our own governance layer.",
    a: "You could. Most teams underestimate what that means: policy management, audit chain, behavioral baselines, fleet learning, rogue detection, deceptive alignment monitoring. That's 6-12 months of infrastructure. EDON is a one-line integration.",
  },
  {
    q: "It sounds like overhead / latency.",
    a: "Sub-50ms evaluation. Legitimate actions proceed without friction. The overhead is invisible. The value shows up when an agent tries to do something it shouldn't.",
  },
  {
    q: "We're not sure we need governance yet.",
    a: "Every company that deploys autonomous agents eventually has a governance incident. The question is whether you have EDON when it happens, or whether you're building it after.",
  },
  {
    q: "How do we know EDON won't block things it shouldn't?",
    a: "You configure the policy. EDON enforces it. Every block is logged with full reasoning and replayable. If EDON blocks something you want allowed, you update the policy — it takes 30 seconds.",
  },
];

const SalesPlaybook = () => {
  return (
    <div className="min-h-screen bg-white font-sans">
      <Navigation />

      <main className="px-6 pt-24 pb-24">
        <div className="mx-auto max-w-4xl">

          {/* Header */}
          <div className="mb-12">
            <div className="inline-block rounded-full bg-black text-white text-xs font-semibold px-3 py-1 mb-4 tracking-wider uppercase">
              Internal — Sales Team Only
            </div>
            <h1 className="text-3xl font-semibold text-black md:text-4xl tracking-tight mb-3">
              EDON Sales Playbook
            </h1>
            <p className="text-[#4b4b4b] text-base leading-relaxed max-w-2xl">
              End-to-end process from first demo request to a live, paying customer. Follow this in order. Don't improvise the close.
            </p>
          </div>

          {/* Stages */}
          <div className="flex flex-col gap-6 mb-16">
            {stages.map((s) => (
              <div
                key={s.stage}
                className={`rounded-2xl border p-7 ${s.color}`}
              >
                <div className="flex items-start justify-between gap-4 mb-5">
                  <div className="flex items-center gap-3">
                    <span className={`text-3xl font-bold tracking-tight ${s.dark ? "text-white/30" : "text-gray-200"}`}>
                      {s.stage}
                    </span>
                    <div>
                      <h2 className={`text-lg font-semibold ${s.dark ? "text-white" : "text-black"}`}>
                        {s.title}
                      </h2>
                    </div>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold shrink-0 ${s.tagColor}`}>
                    {s.tag}
                  </span>
                </div>
                <ul className="space-y-3 mb-5">
                  {s.steps.map((step, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${s.dark ? "bg-white/40" : "bg-gray-400"}`} />
                      <p className={`text-sm leading-relaxed ${s.dark ? "text-white/80" : "text-[#4b4b4b]"}`}>
                        {step}
                      </p>
                    </li>
                  ))}
                </ul>
                <div className={`rounded-xl px-4 py-3 border ${s.dark ? "bg-white/10 border-white/20" : "bg-white border-gray-200"}`}>
                  <p className={`text-xs font-semibold uppercase tracking-wider mb-1 ${s.dark ? "text-white/50" : "text-gray-400"}`}>
                    Action
                  </p>
                  <p className={`text-sm font-medium ${s.dark ? "text-white" : "text-black"}`}>
                    {s.action}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* Objection handling */}
          <div className="mb-16">
            <h2 className="text-2xl font-semibold text-black mb-6">Objection handling</h2>
            <div className="flex flex-col gap-4">
              {objections.map((obj, i) => (
                <div key={i} className="rounded-2xl bg-[#f4f4f4] border border-gray-100 p-6">
                  <p className="text-sm font-semibold text-black mb-2">"{obj.q}"</p>
                  <p className="text-sm text-[#4b4b4b] leading-relaxed">{obj.a}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Key differentiators cheat sheet */}
          <div className="rounded-3xl bg-black p-8">
            <h2 className="text-xl font-semibold text-white mb-6">EDON vs everything else — one-liner cheat sheet</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {[
                { vsWhat: "vs Logging tools", point: "We govern before execution. They record after. That's the difference between prevention and retrospective." },
                { vsWhat: "vs Static policy engines", point: "We learn from every decision. They're frozen at configuration time. Our governance improves as your fleet grows." },
                { vsWhat: "vs Build-your-own", point: "6–12 months of infrastructure vs one API call. And ours has fleet learning, rogue detection, and deceptive alignment monitoring built in." },
                { vsWhat: "vs 'We're not ready'", point: "The best time to add governance is before your first incident. The second best time is now." },
              ].map((item) => (
                <div key={item.vsWhat} className="rounded-xl bg-white/5 border border-white/10 p-5">
                  <p className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-2">{item.vsWhat}</p>
                  <p className="text-sm text-white/80 leading-relaxed">{item.point}</p>
                </div>
              ))}
            </div>
          </div>

        </div>
      </main>
      <ScrollToTop />
    </div>
  );
};

export default SalesPlaybook;
