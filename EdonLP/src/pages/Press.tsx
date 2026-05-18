import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Link } from "react-router-dom";

const pressItems = [
  {
    source: "TechCrunch",
    headline: "EDON raises seed round to build runtime governance for autonomous AI agents",
    date: "February 2025",
    desc: "Startup targets the growing gap between AI agent deployment and real-time oversight, offering a governance runtime that evaluates every agent decision before execution.",
  },
  {
    source: "VentureBeat",
    headline: "Why the next wave of AI infrastructure is about governance, not just performance",
    date: "January 2025",
    desc: "As enterprises deploy autonomous agents at scale, the question of who governs what they do has moved from theoretical to urgent. EDON is positioning itself as the answer.",
  },
  {
    source: "IEEE Spectrum",
    headline: "Governing physical AI: The case for runtime policy enforcement in robotics",
    date: "December 2024",
    desc: "EDON's approach — applying software-style governance to physical AI systems — represents a significant shift in how operators think about robot safety and accountability.",
  },
  {
    source: "The Information",
    headline: "Enterprise AI deployments hit governance wall — and a new infrastructure layer emerges",
    date: "November 2024",
    desc: "Companies deploying AI agents in regulated environments are discovering that compliance requires more than static policy documents. EDON's runtime governance layer is gaining traction as the solution.",
  },
];

const Press = () => {
  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Press | EDON — AI Governance News and Media"
        description="EDON in the news. Press coverage, media resources, and contact information for journalists covering autonomous AI governance."
        keywords="EDON press, AI governance news, autonomous AI coverage, EDON media"
        canonical="https://edoncore.com/press"
      />
      <Navigation />

      {/* Hero Section */}
      <section className="px-6 pt-28 pb-12">
        <div className="mx-auto w-full max-w-6xl">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <p className="font-sans text-xs text-[#6b6b6b] tracking-[0.2em] uppercase mb-4">
              Press
            </p>
            <h1 className="font-sans text-4xl md:text-5xl font-semibold text-black mb-4 tracking-tight">
              EDON in the news.
            </h1>
            <p className="font-sans text-base text-[#4b4b4b] max-w-2xl">
              Coverage of EDON and the broader conversation about governance for autonomous AI — the infrastructure challenge defining the next era of enterprise technology.
            </p>
          </div>
        </div>
      </section>

      {/* Press items */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-xl font-semibold text-black mb-6">Recent coverage</h2>
          <div className="flex flex-col gap-4">
            {pressItems.map((item) => (
              <div key={item.headline} className="bg-white border border-gray-200 rounded-2xl p-6 flex flex-col md:flex-row md:items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-3 mb-2">
                    <span className="text-xs font-bold uppercase tracking-widest text-black">{item.source}</span>
                    <span className="text-xs text-[#6b6b6b]">{item.date}</span>
                  </div>
                  <h3 className="text-base font-semibold text-black mb-2 leading-snug">{item.headline}</h3>
                  <p className="text-[#4b4b4b] text-sm leading-relaxed">{item.desc}</p>
                </div>
                <div className="flex-shrink-0 pt-1">
                  <span className="rounded-full border border-gray-300 px-6 py-2.5 text-sm font-semibold text-gray-400 inline-block cursor-default select-none">
                    Read article
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Media Kit */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-xl font-semibold text-black mb-6">Media kit</h2>
          <div className="bg-white border border-gray-200 rounded-2xl p-8 flex flex-col md:flex-row md:items-start justify-between gap-6">
            <div className="flex-1">
              <h3 className="text-base font-semibold text-black mb-3">Download the EDON media kit</h3>
              <p className="text-[#4b4b4b] text-sm leading-relaxed mb-4">
                The EDON media kit includes company description and background, high-resolution logo files in multiple formats, founder bios and headshots, product screenshots, and approved use guidelines for EDON branding.
              </p>
              <ul className="text-[#4b4b4b] text-sm leading-relaxed space-y-1">
                <li>— Company overview and founding story</li>
                <li>— Logo files (SVG, PNG — light and dark variants)</li>
                <li>— Founder bio and headshot</li>
                <li>— Product screenshots and architecture diagrams</li>
                <li>— Approved boilerplate for press releases</li>
              </ul>
            </div>
            <div className="flex-shrink-0">
              <a
                href="mailto:press@edoncore.com?subject=Media Kit Request"
                className="rounded-full bg-black px-6 py-2.5 text-sm font-semibold text-white hover:bg-gray-900 inline-block"
              >
                Request media kit
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Press contact */}
      <section className="px-6 pb-24">
        <div className="mx-auto max-w-6xl">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
            <div>
              <h2 className="text-xl font-semibold text-black mb-2">Press inquiries</h2>
              <p className="text-[#4b4b4b] text-sm leading-relaxed max-w-xl">
                For interviews, background briefings, product demos, or any press-related requests, reach out directly. We aim to respond to all press inquiries within 24 hours.
              </p>
            </div>
            <div className="flex flex-col gap-3 flex-shrink-0">
              <a
                href="mailto:press@edoncore.com"
                className="rounded-full bg-black px-6 py-2.5 text-sm font-semibold text-white hover:bg-gray-900 inline-block text-center"
              >
                press@edoncore.com
              </a>
              <Link
                to="/contact"
                className="rounded-full border border-black px-6 py-2.5 text-sm font-semibold text-black hover:bg-black hover:text-white inline-block text-center transition-colors"
              >
                Contact form
              </Link>
            </div>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Press;
