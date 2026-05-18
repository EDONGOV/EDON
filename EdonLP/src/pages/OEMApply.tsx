import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { sendFormSubmission } from "@/lib/emailService";

const OEMApply = () => {
  const [formData, setFormData] = useState({
    companyName: "",
    role: "",
    deploymentType: "",
    useCase: "",
    deploymentTimeline: "",
    region: "",
    workEmail: "",
    termsAccepted: false,
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [emailError, setEmailError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    setIsSubmitting(true);
    setEmailError("");
    
    try {
      // Send email to charlie@edoncore.com
      await sendFormSubmission('oem', formData);
      
      // Redirect to confirmation page
      window.location.href = "/oem/confirmation";
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error("Error submitting form:", error);
      }
      alert("There was an error submitting your application. Please try again or contact us directly.");
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Request Access | EDON for Agents and Physical AI"
        description="Request access to EDON. For autonomous agents, physical AI deployments, and enterprise governance evaluations."
        keywords="EDON access, autonomous agents, physical AI, enterprise governance, evaluation access"
        canonical="https://edoncore.com/oem/apply"
      />
      <Navigation />
      
      {/* Hero Section */}
      <section className="bg-gray-50 py-24 px-8 pt-32">
        <div className="max-w-3xl mx-auto">
          <h1 className="font-sans text-5xl font-bold text-black mb-4">
            Request Access
          </h1>
          <p className="font-sans text-lg text-gray-600 mb-2">
            For autonomous agents, physical AI deployments, and enterprise governance evaluations.
          </p>
          <p className="font-sans text-base text-gray-700 font-medium">
            We'll review your application and respond within 2-3 business days.
          </p>
        </div>
      </section>

      {/* Form Section */}
      <section className="py-24 px-8">
        <div className="max-w-2xl mx-auto">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label className="block font-sans text-sm text-gray-700 uppercase tracking-widest mb-2">
                Company Name *
              </label>
              <input
                type="text"
                required
                value={formData.companyName}
                onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                className="w-full bg-white border border-gray-300 text-black px-4 py-3 focus:outline-none focus:border-tactical-cyan transition-colors"
                placeholder="Your company name"
              />
            </div>

            <div>
              <label className="block font-sans text-sm text-gray-700 uppercase tracking-widest mb-2">
                Role *
              </label>
              <input
                type="text"
                required
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                className="w-full bg-white border border-gray-300 text-black px-4 py-3 focus:outline-none focus:border-tactical-cyan transition-colors"
                placeholder="Your role/title"
              />
            </div>

            <div>
              <label className="block font-sans text-sm text-gray-700 uppercase tracking-widest mb-2">
                Deployment Type *
              </label>
              <select
                required
                value={formData.deploymentType}
                onChange={(e) => setFormData({ ...formData, deploymentType: e.target.value })}
                className="w-full bg-white border border-gray-300 text-black px-4 py-3 focus:outline-none focus:border-tactical-cyan transition-colors"
              >
                <option value="">Select deployment type</option>
                <option value="autonomous-agent">Autonomous agent</option>
                <option value="physical-ai">Physical AI / robotics</option>
                <option value="both">Both</option>
              </select>
            </div>

            <div>
              <label className="block font-sans text-sm text-gray-700 uppercase tracking-widest mb-2">
                Use Case *
              </label>
              <select
                required
                value={formData.useCase}
                onChange={(e) => setFormData({ ...formData, useCase: e.target.value })}
                className="w-full bg-white border border-gray-300 text-black px-4 py-3 focus:outline-none focus:border-tactical-cyan transition-colors"
              >
                <option value="">Select use case</option>
                <option value="humanoid">Humanoid</option>
                <option value="drone">Drone</option>
                <option value="wearable">Wearable</option>
                <option value="environment">Environment</option>
                <option value="agent">Autonomous Agent</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div>
              <label className="block font-sans text-sm text-gray-700 uppercase tracking-widest mb-2">
                Deployment Timeline *
              </label>
              <select
                required
                value={formData.deploymentTimeline}
                onChange={(e) => setFormData({ ...formData, deploymentTimeline: e.target.value })}
                className="w-full bg-white border border-gray-300 text-black px-4 py-3 focus:outline-none focus:border-tactical-cyan transition-colors"
              >
                <option value="">Select timeline</option>
                <option value="immediate">Immediate (0-3 months)</option>
                <option value="short">Short-term (3-6 months)</option>
                <option value="medium">Medium-term (6-12 months)</option>
                <option value="long">Long-term (12+ months)</option>
              </select>
            </div>

            <div>
              <label className="block font-sans text-sm text-gray-700 uppercase tracking-widest mb-2">
                Region *
              </label>
              <select
                required
                value={formData.region}
                onChange={(e) => setFormData({ ...formData, region: e.target.value })}
                className="w-full bg-white border border-gray-300 text-black px-4 py-3 focus:outline-none focus:border-tactical-cyan transition-colors"
              >
                <option value="">Select country/region</option>
                <option value="United States">United States</option>
                <option value="Canada">Canada</option>
                <option value="United Kingdom">United Kingdom</option>
                <option value="Germany">Germany</option>
                <option value="France">France</option>
                <option value="Italy">Italy</option>
                <option value="Spain">Spain</option>
                <option value="Netherlands">Netherlands</option>
                <option value="Belgium">Belgium</option>
                <option value="Switzerland">Switzerland</option>
                <option value="Austria">Austria</option>
                <option value="Sweden">Sweden</option>
                <option value="Norway">Norway</option>
                <option value="Denmark">Denmark</option>
                <option value="Finland">Finland</option>
                <option value="Poland">Poland</option>
                <option value="Czech Republic">Czech Republic</option>
                <option value="Portugal">Portugal</option>
                <option value="Ireland">Ireland</option>
                <option value="Greece">Greece</option>
                <option value="Japan">Japan</option>
                <option value="South Korea">South Korea</option>
                <option value="China">China</option>
                <option value="India">India</option>
                <option value="Singapore">Singapore</option>
                <option value="Australia">Australia</option>
                <option value="New Zealand">New Zealand</option>
                <option value="Israel">Israel</option>
                <option value="United Arab Emirates">United Arab Emirates</option>
                <option value="Saudi Arabia">Saudi Arabia</option>
                <option value="Brazil">Brazil</option>
                <option value="Mexico">Mexico</option>
                <option value="Argentina">Argentina</option>
                <option value="Chile">Chile</option>
                <option value="South Africa">South Africa</option>
                <option value="Turkey">Turkey</option>
                <option value="Russia">Russia</option>
                <option value="Other">Other</option>
              </select>
            </div>

            <div>
              <label className="block font-sans text-sm text-gray-700 uppercase tracking-widest mb-2">
                Email *
              </label>
              <input
                type="email"
                required
                value={formData.workEmail}
                onChange={(e) => setFormData({ ...formData, workEmail: e.target.value })}
                className="w-full bg-white border border-gray-300 text-black px-4 py-3 focus:outline-none focus:border-tactical-cyan transition-colors"
                placeholder="your.email@example.com"
              />
            </div>

            <div className="flex items-start gap-3">
              <input
                type="checkbox"
                required
                checked={formData.termsAccepted}
                onChange={(e) => setFormData({ ...formData, termsAccepted: e.target.checked })}
                className="mt-1 w-4 h-4 border-gray-300 text-tactical-cyan focus:ring-tactical-cyan"
              />
              <label className="font-sans text-sm text-gray-700">
                I agree to the terms and conditions and understand that this is an evaluation request subject to approval.
              </label>
            </div>

            <Button
              type="submit"
              variant="tactical"
              size="lg"
              className="w-full font-sans tracking-wider"
              disabled={isSubmitting}
            >
              {isSubmitting ? "SUBMITTING..." : "SUBMIT APPLICATION"}
            </Button>
          </form>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default OEMApply;

