import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { sendFormSubmission } from "@/lib/emailService";
import { toast } from "sonner";

const inputBase =
  "w-full bg-gray-50 border border-gray-200 text-gray-900 px-4 py-3 rounded-xl focus:outline-none focus:border-gray-400 focus:ring-2 focus:ring-gray-200 transition-colors placeholder:text-gray-400";

const HOW_HEARD_OPTIONS = [
  "Google / search",
  "LinkedIn",
  "Twitter / X",
  "Word of mouth / referral",
  "Conference or event",
  "Press or media coverage",
  "GitHub",
  "Newsletter",
  "Other",
];

const AGENT_COUNT_OPTIONS = [
  "1–5 agents",
  "6–20 agents",
  "21–100 agents",
  "100–500 agents",
  "500+ agents",
  "Not sure yet",
];

const Contact = () => {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    organization: "",
    website: "",
    agentCount: "",
    howHeard: "",
    message: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      await sendFormSubmission("contact", {
        ...formData,
        organization: formData.organization,
        message: `${formData.message}\n\nCompany website: ${formData.website}\nAgents to govern: ${formData.agentCount}\nHow they heard about us: ${formData.howHeard}`,
      });
      toast.success("Thank you! Your request has been submitted. We'll respond within 24-48 hours.");
      setFormData({
        name: "",
        email: "",
        organization: "",
        website: "",
        agentCount: "",
        howHeard: "",
        message: "",
      });
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error("Error submitting contact form:", error);
      }
      toast.error("There was an error submitting your request. Please try again or contact us directly.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Contact EDON | Get in Touch"
        description="Contact EDON for runtime governance, OEM evaluations, and deployment inquiries. Set up a conversation with our team."
        keywords="contact EDON, OEM access, EDON evaluation, technical partnership"
        canonical="https://edoncore.com/contact"
      />
      <Navigation />

      <section className="px-6 pt-24 pb-16 md:pt-28 md:pb-20">
        <div className="mx-auto max-w-6xl">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-start">
            {/* Left: headline + copy */}
            <div className="lg:col-span-5">
              <h1 className="text-3xl font-semibold text-black tracking-tight md:text-4xl lg:text-[2.5rem]">
                Transform your operating model with EDON.
              </h1>
              <p className="mt-6 text-base text-gray-600 leading-relaxed max-w-md">
                Schedule a call with our team to see how runtime governance for autonomous agents and physical AI can fit your deployment, with enterprise-grade audit, policy, and scale built in.
              </p>
            </div>

            {/* Right: form card */}
            <div className="lg:col-span-7">
              <div className="bg-white rounded-3xl p-8 md:p-10 shadow-[0_12px_40px_rgba(0,0,0,0.08)] border border-gray-100">
                <h2 className="text-xl font-semibold text-black md:text-2xl">
                  Get in touch
                </h2>
                <p className="mt-2 text-sm text-gray-500">
                  Submit the form and our team will be in touch shortly to set up a conversation.
                </p>

                <form onSubmit={handleSubmit} className="mt-8 space-y-5">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                        Name *
                      </label>
                      <input
                        type="text"
                        required
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        className={inputBase}
                        placeholder="Full name"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                        Work email *
                      </label>
                      <input
                        type="email"
                        required
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        className={inputBase}
                        placeholder="you@company.com"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                        Company *
                      </label>
                      <input
                        type="text"
                        required
                        value={formData.organization}
                        onChange={(e) => setFormData({ ...formData, organization: e.target.value })}
                        className={inputBase}
                        placeholder="Company name"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                        Company website *
                      </label>
                      <input
                        type="url"
                        required
                        value={formData.website}
                        onChange={(e) => setFormData({ ...formData, website: e.target.value })}
                        className={inputBase}
                        placeholder="https://yourcompany.com"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                      Agents to govern *
                    </label>
                    <select
                      required
                      value={formData.agentCount}
                      onChange={(e) => setFormData({ ...formData, agentCount: e.target.value })}
                      className={inputBase}
                    >
                      <option value="">How many agents?</option>
                      {AGENT_COUNT_OPTIONS.map((opt) => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                      How did you hear about us? *
                    </label>
                    <select
                      required
                      value={formData.howHeard}
                      onChange={(e) => setFormData({ ...formData, howHeard: e.target.value })}
                      className={inputBase}
                    >
                      <option value="">Select an option...</option>
                      {HOW_HEARD_OPTIONS.map((opt) => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                      Message
                    </label>
                    <textarea
                      rows={5}
                      value={formData.message}
                      onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                      className={`${inputBase} resize-none`}
                      placeholder="Tell us about your use case and what you're looking for..."
                    />
                  </div>

                  <Button
                    type="submit"
                    className="w-full rounded-full bg-black text-white hover:bg-gray-900 font-semibold text-sm h-12 px-8 mt-2"
                    disabled={isSubmitting}
                  >
                    {isSubmitting ? "Submitting…" : "Submit"}
                  </Button>
                </form>

                <p className="mt-6 text-xs text-gray-500 leading-relaxed">
                  We use your information only to respond to your request. By submitting, you agree to our privacy policy.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Contact;
