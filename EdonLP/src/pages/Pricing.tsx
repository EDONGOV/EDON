import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Link } from "react-router-dom";

const STRIPE_LINK_SCALE = import.meta.env.VITE_STRIPE_LINK_SCALE || "https://checkout.edoncore.com/b/eVqaEW7i8b502RI6jefIs0b";
const STRIPE_LINK_PRO = import.meta.env.VITE_STRIPE_LINK_PRO || "https://checkout.edoncore.com/b/4gMfZg0TK8WScsi7nifIs0c";

const Pricing = () => {
  const plans = [
    {
      id: "free",
      name: "Free",
      price: "$0",
      period: "",
      rateLabel: null as string | null,
      decisionsPerMonth: "50k",
      overage: null as string | null,
      agents: "10",
      retention: "7 days",
      note: "Perfect for evaluation and prototyping",
      cta: "Get started",
      custom: false,
      checkoutUrl: "/signup",
      badge: null as string | null,
    },
    {
      id: "scale",
      name: "Scale",
      price: "$80",
      period: "/mo",
      rateLabel: "Up to 500k decisions/mo",
      decisionsPerMonth: "500k",
      overage: "$0.01–$0.02 per decision after",
      agents: "100",
      retention: "90 days",
      note: "$250k revenue potential at full usage",
      cta: "Get started",
      custom: false,
      checkoutUrl: STRIPE_LINK_SCALE,
      badge: "Most Popular",
    },
    {
      id: "pro",
      name: "Pro",
      price: "$200",
      period: "/mo",
      rateLabel: "Up to 5M decisions/mo",
      decisionsPerMonth: "5M",
      overage: "$0.01–$0.02 per decision after",
      agents: "1,000",
      retention: "1 year + compliance",
      note: "$1.25M revenue potential at full usage",
      cta: "Get started",
      custom: false,
      checkoutUrl: STRIPE_LINK_PRO,
      badge: null as string | null,
    },
    {
      id: "enterprise",
      name: "Enterprise",
      price: "Contact us",
      period: "",
      rateLabel: null,
      decisionsPerMonth: "Unlimited",
      overage: "Custom",
      agents: "Unlimited",
      retention: "Unlimited",
      note: "Regulated environments & physical AI at scale",
      cta: "Contact Sales",
      custom: true,
      checkoutUrl: undefined,
      badge: null as string | null,
    },
  ];

  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Pricing | EDON"
        description="Free, Scale $150/mo, Pro $600/mo, or Enterprise. Decisions, agents, and retention per tier."
        canonical="https://edoncore.com/pricing"
      />
      <Navigation />
      
      <section className="bg-[#fafafa] py-20 px-6 pt-28 md:px-8">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h1 className="text-3xl md:text-4xl font-semibold text-black tracking-tight mb-2">
              Pricing
            </h1>
            <p className="text-sm text-neutral-500 max-w-md mx-auto">
              Governance by tier. No capacity markup.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-5 max-w-6xl mx-auto">
            {plans.map((plan) => (
              <div
                key={plan.id}
                className={`flex flex-col rounded-2xl transition-all duration-300 ease-out hover:scale-[1.03] hover:-translate-y-1.5 hover:shadow-xl cursor-default ${
                  plan.badge
                    ? "bg-white border-2 border-green-500 shadow-md shadow-green-200/40 hover:shadow-green-200/60"
                    : "bg-white border border-neutral-200/80 hover:border-neutral-300 hover:shadow-lg"
                }`}
              >
                <div className="p-5 md:p-6 flex flex-col flex-1">
                  <div className="mb-4">
                    {plan.badge && (
                      <span className="inline-block text-[10px] uppercase tracking-widest text-green-600 font-medium mb-2">
                        {plan.badge}
                      </span>
                    )}
                    <h3
                      className="text-sm font-medium uppercase tracking-wider text-neutral-500"
                    >
                      {plan.name}
                    </h3>
                  </div>
                  <div className="mb-1">
                    <span className="text-2xl md:text-3xl font-semibold tracking-tight text-black">
                      {plan.price}
                    </span>
                    {plan.period && (
                      <span className="text-neutral-500 text-sm ml-0.5">{plan.period}</span>
                    )}
                  </div>
                  {plan.rateLabel && (
                    <p className="text-xs text-neutral-400 mb-4">{plan.rateLabel}</p>
                  )}
                  {!plan.rateLabel && <div className="mb-4" />}

                  <dl className="space-y-3 text-sm flex-1">
                    <div className="flex justify-between gap-3">
                      <dt className="text-neutral-500">Decisions/mo</dt>
                      <dd className="text-neutral-900 font-medium">{plan.decisionsPerMonth}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-neutral-500">Agents</dt>
                      <dd className="text-neutral-900 font-medium">{plan.agents}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-neutral-500">Retention</dt>
                      <dd className="text-neutral-900 font-medium">{plan.retention}</dd>
                    </div>
                  </dl>
                </div>

                <div className="p-5 md:p-6 pt-0">
                  {plan.id === "free" ? (
                    <Link to="/signup">
                      <button className="w-full py-3 rounded-xl text-sm font-medium border border-neutral-200 text-neutral-700 hover:bg-neutral-50 transition-colors">
                        {plan.cta}
                      </button>
                    </Link>
                  ) : plan.custom ? (
                    <Link to="/contact">
                      <button className="w-full py-3 rounded-xl text-sm font-medium border border-neutral-200 text-neutral-700 hover:bg-neutral-50 transition-colors">
                        {plan.cta}
                      </button>
                    </Link>
                  ) : plan.checkoutUrl ? (
                    <a href={plan.checkoutUrl} target="_blank" rel="noopener noreferrer">
                      <button
                        className={`w-full py-3 rounded-xl text-sm font-medium transition-colors ${
                          plan.badge ? "bg-green-600 text-white hover:bg-green-700" : "bg-black text-white hover:bg-neutral-800"
                        }`}
                      >
                        {plan.cta}
                      </button>
                    </a>
                  ) : null}
                </div>
              </div>
            ))}
          </div>

          <p className="mt-12 text-center text-xs text-neutral-400 max-w-xl mx-auto">
            Enterprise: autonomous agents and physical AI at scale or in regulated environments.
          </p>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Pricing;
