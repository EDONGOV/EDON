import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Link } from "react-router-dom";

const About = () => {
  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="About EDON | Mission & Founder"
        description="EDON was founded by Charlie Biggins to solve a fundamental problem: machines can act, but they can't understand context or internal state. Learn about our mission and architecture."
        keywords="EDON founder, Charlie Biggins, adaptive intelligence, embodied AI mission"
        canonical="https://edoncore.com/about"
      />
      <Navigation />
      <section className="px-6 pt-28">
        <div className="mx-auto w-full max-w-6xl">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <h1 className="font-sans text-4xl md:text-5xl font-semibold tracking-tight text-black mb-3">
              About Us
            </h1>
            <p className="font-sans text-sm tracking-widest text-[#6b6b6b] uppercase">
              Our Mission, Our Vision and Our Team
            </p>
          </div>
        </div>
      </section>

      {/* Section 1 - Founder Introduction */}
      <section className="py-20 px-6 bg-white">
        <div className="max-w-5xl mx-auto rounded-3xl bg-white p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
          <h2 className="font-sans text-3xl md:text-4xl font-bold text-black mb-6">
            Why Governance Had to Exist
          </h2>
          <div className="space-y-6 text-base md:text-lg leading-relaxed text-gray-700 font-sans">
            <p>
              Physical AI systems are reaching deployment scale. The question is no longer whether machines can operate autonomously, but whether they can be governed, insured, and held accountable.
            </p>
            <p className="font-semibold text-black">
              I founded EDON because governance had to exist before the first disaster:
            </p>
            <ul className="space-y-2 pl-6 list-disc">
              <li>Before insurance markets collapse from uncertainty</li>
              <li>Before regulatory frameworks are established</li>
              <li>Before institutions lose confidence in autonomous deployment</li>
            </ul>
            <p>
              EDON provides the operational authorization and runtime oversight that makes physical AI deployment defensible at scale.
            </p>
            <p className="text-tactical-cyan font-semibold text-lg">
              Governance must exist before the first incident.
            </p>
          </div>
        </div>
      </section>

      {/* Section 2 - Origin Story */}
      <section className="py-12 px-6 bg-white">
        <div className="max-w-5xl mx-auto rounded-3xl bg-[#f4f4f4] p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
          <h2 className="font-sans text-3xl md:text-4xl font-bold text-black mb-6">
            Why Private Governance Before Regulation
          </h2>
          <div className="space-y-6 text-base md:text-lg leading-relaxed text-gray-700 font-sans">
            <p>
              History shows that critical technologies require governance frameworks before regulation arrives. Aviation had airworthiness standards before the FAA. Nuclear power had operational protocols before the NRC. Physical AI needs the same.
            </p>
            <p>
              The aviation comparison:
            </p>
            <ul className="space-y-2 pl-6 list-disc">
              <li>Aircraft required certification before commercial operation</li>
              <li>Pilots needed authorization before flight</li>
              <li>Systems needed continuous monitoring and incident response</li>
              <li>Private standards emerged before government regulation</li>
            </ul>
            <p>
              The nuclear comparison:
            </p>
            <ul className="space-y-2 pl-6 list-disc">
              <li>Operational authorization required before startup</li>
              <li>Runtime oversight independent of plant control</li>
              <li>Incident containment and evidence capture</li>
              <li>Clear liability boundaries between operator and system</li>
            </ul>
            <p className="font-semibold text-black">
              EDON applies these principles to physical AI:
            </p>
            <div className="pl-6 border-l-4 border-tactical-cyan">
              <p className="text-black">
                Operational authorization (EOA) before deployment<br />
                Runtime governance (RAO) during operation<br />
                Incident containment and auditability after events<br />
                Clear standards that enable insurability
              </p>
            </div>
            <p className="text-tactical-cyan font-semibold text-lg">
              Private governance enables responsible deployment before regulation arrives.
            </p>
          </div>
        </div>
      </section>

      {/* Section 3 - Why Now */}
      <section className="py-12 px-6 bg-white">
        <div className="max-w-5xl mx-auto rounded-3xl bg-white p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
          <h2 className="font-sans text-3xl md:text-4xl font-bold text-black mb-6">
            Why EDON Does Not Replace Government
          </h2>
          <div className="space-y-6 text-base md:text-lg leading-relaxed text-gray-700 font-sans">
            <p>
              EDON provides operational governance, not legal regulation. We establish deployment authorization and runtime oversight—the technical and institutional framework that enables safe operation.
            </p>
            <p>
              Government regulation will come. When it does, EDON's standards are designed to align with future regulatory requirements. But waiting for regulation means:
            </p>
            <ul className="space-y-2 pl-6 list-disc">
              <li>Deployments stall in pilot phase</li>
              <li>Insurance markets remain closed</li>
              <li>Institutional adoption is blocked</li>
              <li>First incidents occur without governance</li>
            </ul>
            <p className="font-semibold text-black">
              EDON enables responsible deployment now, while supporting future regulatory alignment.
            </p>
          </div>
        </div>
      </section>

      {/* Section 4 - Personal Philosophy */}
      <section className="py-12 px-6 bg-white">
        <div className="max-w-5xl mx-auto rounded-3xl bg-[#f4f4f4] p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
          <h2 className="font-sans text-3xl md:text-4xl font-bold text-black mb-6">
            Institutional Rationale
          </h2>
          <div className="space-y-6 text-base md:text-lg leading-relaxed text-gray-700 font-sans">
            <p>
              Physical AI systems will fail. The question is whether those failures propagate, repeat, or remain unexplained. EDON exists to ensure they do not.
            </p>
            <p>
              For institutions considering physical AI deployment, EDON answers three questions:
            </p>
            <ul className="space-y-3 pl-6 list-disc">
              <li><strong>Can this system be deployed?</strong> EOA provides binary authorization tied to governance standards.</li>
              <li><strong>Can it be insured?</strong> Runtime governance and auditability enable insurance underwriting.</li>
              <li><strong>Can it be governed after failure?</strong> Incident containment and evidence capture support accountability.</li>
            </ul>
            <p className="text-black font-semibold">
              If a page doesn't answer one of those questions, it's misaligned.
            </p>
            <p>
              EDON is the layer that decides whether machines are allowed to operate. This is not about capability—it is about permission.
            </p>
          </div>
        </div>
      </section>

      {/* Section 5 - Vision Statement */}
      <section className="py-12 px-6 bg-white">
        <div className="max-w-5xl mx-auto rounded-3xl bg-white p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
          <h2 className="font-sans text-3xl md:text-4xl font-bold text-black mb-6">
            The North Star
          </h2>
          <div className="space-y-6 text-base md:text-lg leading-relaxed font-sans">
            <p className="text-lg text-black font-semibold">
              Everything must point here:
            </p>
            <p className="text-gray-700">
              EDON is the deployment and governance layer that makes physical AI safe, insurable, and operable at scale.
            </p>
            <p className="text-gray-700 font-semibold">
              Our mission is not:
            </p>
            <ul className="space-y-2 pl-6 list-disc text-gray-600">
              <li>Adaptive intelligence</li>
              <li>State awareness</li>
              <li>High dimensional vectors</li>
            </ul>
            <p className="text-gray-700 font-semibold">
              Our mission is:
            </p>
            <p className="text-black text-lg">
              To be the deployment and governance layer that makes physical AI safe, insurable, and operable at scale.
            </p>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default About;

