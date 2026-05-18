import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Link } from "react-router-dom";

const About = () => {
  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="About EDON | The Governance Layer for Autonomous AI"
        description="EDON is building the runtime governance layer for autonomous AI agents. Learn about our mission, values, and the team behind the platform."
        keywords="EDON company, AI governance company, autonomous AI safety, about EDON"
        canonical="https://edoncore.com/about"
      />
      <Navigation />

      <main className="px-6 pb-20 pt-16">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-12">
          {/* Intro: same card style as home below-video sections */}
          <section className="rounded-3xl bg-[#f4f4f4] p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <h2 className="mt-3 text-2xl font-semibold text-black md:text-3xl">
              We're building the governance layer for autonomous AI.
            </h2>
            <div className="mt-4 space-y-4 text-sm text-[#4b4b4b] md:text-base">
              <p>
                Runtime governance for every agent, physical and digital, so the world can deploy autonomous AI safely at scale.
              </p>
            </div>
          </section>

          {/* Our mission */}
          <section className="rounded-3xl bg-white p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <h2 className="mt-3 text-2xl font-semibold text-black md:text-3xl">Our mission</h2>
            <div className="mt-4 space-y-4 text-sm text-[#4b4b4b] md:text-base">
              <p>
                EDON exists because the world is deploying millions of AI agents, in hospitals, warehouses, financial systems, and physical environments, without any runtime governance. Policy gets written once, at deployment time, and then agents operate unsupervised until something goes wrong.
              </p>
              <p>
                We're fixing that. EDON is the runtime layer that sits between any autonomous agent and the world it acts in. Every decision, evaluated in real time, against live policy, before execution. Every outcome, logged, chained, and auditable.
              </p>
              <p>
                We believe autonomous AI is inevitable and profoundly valuable. The question isn't whether to deploy it; it's whether you can govern it when it scales. EDON is the answer to that question.
              </p>
            </div>
          </section>

          {/* What we believe */}
          <section className="rounded-3xl bg-[#f4f4f4] p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <h2 className="mt-3 text-2xl font-semibold text-black md:text-3xl">What we believe</h2>
            <div className="mt-4 space-y-4 text-sm text-[#4b4b4b] md:text-base">
              <div>
                <p className="font-semibold text-black">Autonomy requires accountability</p>
                <p>Every autonomous decision must be attributable, auditable, and governable. Accountability isn't a constraint on autonomy; it's what makes high-stakes autonomy possible at all.</p>
              </div>
              <div>
                <p className="font-semibold text-black">Governance must be real-time</p>
                <p>Post-hoc auditing isn't governance; it's forensics. By the time you review what an agent did, the consequences have already happened. Governance only works when it's in the critical path, evaluating decisions before execution.</p>
              </div>
              <div>
                <p className="font-semibold text-black">Physical and digital AI need the same framework</p>
                <p>A robot picking a warehouse shelf and a software agent sending an email are both making autonomous decisions with real consequences. The governance framework should be unified, not two separate toolchains for digital and physical AI.</p>
              </div>
            </div>
          </section>

          {/* Built by operators */}
          <section className="rounded-3xl bg-white p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <h2 className="mt-3 text-2xl font-semibold text-black md:text-3xl">Built by operators</h2>
            <div className="mt-4 space-y-4 text-sm text-[#4b4b4b] md:text-base">
              <p>
                EDON was founded by people who have built and operated AI systems at scale, in production environments where failures have real consequences. We've seen firsthand what happens when governance is an afterthought: incidents that should have been blocked, audits that couldn't be completed, regulators asking questions that couldn't be answered.
              </p>
              <p>
                We're building the infrastructure we wish had existed. A team with deep backgrounds in distributed systems, AI policy, physical robotics, and enterprise security, focused entirely on making autonomous AI governable.
              </p>
            </div>
          </section>

          {/* CTA: same card format as home */}
          <section className="rounded-3xl bg-[#f4f4f4] p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)] flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
            <div>
              <h2 className="mt-3 text-2xl font-semibold text-black md:text-3xl">Get in touch</h2>
              <p className="mt-4 text-sm text-[#4b4b4b] md:text-base max-w-xl">
                Whether you're evaluating EDON for deployment, exploring a partnership, or just want to talk about the future of AI governance, we'd love to hear from you.
              </p>
            </div>
            <Link
              to="/contact"
              className="rounded-full bg-black px-6 py-2.5 text-sm font-semibold text-white hover:bg-gray-900 whitespace-nowrap shrink-0"
            >
              Contact us
            </Link>
          </section>
        </div>
      </main>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default About;
