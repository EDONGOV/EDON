import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { sendFormSubmission } from "@/lib/emailService";
import { validateCompanyEmail } from "@/lib/emailValidation";

const Download = () => {
  const [formData, setFormData] = useState({
    email: "",
    company: "",
    region: "",
    deviceType: "",
    licenseAccepted: false,
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [emailError, setEmailError] = useState<string>("");
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [submitError, setSubmitError] = useState<string>("");

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const email = e.target.value;
    setFormData({ ...formData, email: email });
    
    // Validate email in real-time
    if (email) {
      const validation = validateCompanyEmail(email);
      if (!validation.isValid) {
        setEmailError(validation.error || "");
      } else {
        setEmailError("");
      }
    } else {
      setEmailError("");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Reset previous states
    setSubmitSuccess(false);
    setSubmitError("");
    
    // Validate email before submission
    const emailValidation = validateCompanyEmail(formData.email);
    if (!emailValidation.isValid) {
      setEmailError(emailValidation.error || "");
      return;
    }
    
    // Validate all required fields
    if (!formData.company || !formData.region || !formData.deviceType || !formData.licenseAccepted) {
      setSubmitError("Please fill in all required fields and accept the license terms.");
      return;
    }
    
    setIsSubmitting(true);
    setEmailError("");
    
    try {
      // Send email to charlie@edoncore.com
      const success = await sendFormSubmission('download', formData);
      
      if (success) {
        setSubmitSuccess(true);
        
        // Reset form
        setFormData({
          email: "",
          company: "",
          region: "",
          deviceType: "",
          licenseAccepted: false,
        });
        
        // Scroll to top to show success message
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } else {
        setSubmitError("There was an error submitting your request. Please try again or contact us directly.");
      }
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error("Error submitting download request:", error);
      }
      setSubmitError("There was an error submitting your request. Please try again or contact us directly.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Download EDON | Evaluation Bundle"
        description="Download EDON v2.0.0 OEM Evaluation Bundle. Request access to the evaluation package for qualified teams. Includes SDK, documentation, and integration support."
        keywords="EDON download, EDON evaluation bundle, OEM evaluation, EDON SDK download"
        canonical="https://edoncore.com/download"
      />
      <Navigation />
      
      {/* Hero Section */}
      <section className="bg-gray-50 py-24 px-8 pt-32">
        <div className="max-w-3xl mx-auto">
          <h1 className="font-sans text-5xl font-bold text-black mb-4">
            Deployment Evaluation Kit
          </h1>
          <p className="font-sans text-lg text-gray-600 mb-2">
            Request access to EDON v2.0.0 Deployment Evaluation Kit. A download link will be sent to your email.
          </p>
          <p className="font-sans text-base text-gray-500">
            For organizations evaluating physical AI deployment under governance and insurability constraints.
          </p>
          
          {submitSuccess && (
            <div className="mt-8 p-6 bg-green-50 border-l-4 border-green-500 rounded-sm">
              <p className="font-sans text-base text-green-800 font-semibold mb-2">
                ✓ Download request received
              </p>
              <p className="font-sans text-sm text-green-700">
                A download link will be sent to your email. Please check your inbox.
              </p>
            </div>
          )}
          
          {submitError && (
            <div className="mt-8 p-6 bg-red-50 border-l-4 border-red-500 rounded-sm">
              <p className="font-sans text-base text-red-800 font-semibold mb-2">
                Error
              </p>
              <p className="font-sans text-sm text-red-700">
                {submitError}
              </p>
            </div>
          )}
        </div>
      </section>

      {/* Form Section */}
      <section className="py-24 px-8">
        <div className="max-w-2xl mx-auto">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label className="block font-sans text-sm text-gray-700 uppercase tracking-widest mb-2">
                Email * <span className="text-xs normal-case text-gray-500">(Company email only)</span>
              </label>
              <input
                type="email"
                required
                value={formData.email}
                onChange={handleEmailChange}
                className={`w-full bg-white border text-black px-4 py-3 focus:outline-none transition-colors ${
                  emailError 
                    ? 'border-red-500 focus:border-red-500' 
                    : 'border-gray-300 focus:border-tactical-cyan'
                }`}
                placeholder="your.email@company.com"
              />
              {emailError && (
                <p className="mt-2 text-sm text-red-600">{emailError}</p>
              )}
              {!emailError && formData.email && (
                <p className="mt-2 text-xs text-gray-500">✓ Company email accepted</p>
              )}
            </div>

            <div>
              <label className="block font-sans text-sm text-gray-700 uppercase tracking-widest mb-2">
                Company *
              </label>
              <input
                type="text"
                required
                value={formData.company}
                onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                className="w-full bg-white border border-gray-300 text-black px-4 py-3 focus:outline-none focus:border-tactical-cyan transition-colors"
                placeholder="Company name"
              />
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
                Device Type *
              </label>
              <select
                required
                value={formData.deviceType}
                onChange={(e) => setFormData({ ...formData, deviceType: e.target.value })}
                className="w-full bg-white border border-gray-300 text-black px-4 py-3 focus:outline-none focus:border-tactical-cyan transition-colors"
              >
                <option value="">Select device type</option>
                <option value="humanoid">Humanoid</option>
                <option value="drone">Drone/UAV</option>
                <option value="wearable">Wearable</option>
                <option value="environment">Smart Environment</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div className="flex items-start gap-3">
              <input
                type="checkbox"
                required
                checked={formData.licenseAccepted}
                onChange={(e) => setFormData({ ...formData, licenseAccepted: e.target.checked })}
                className="mt-1 w-4 h-4 border-gray-300 text-tactical-cyan focus:ring-tactical-cyan"
              />
              <label className="font-sans text-sm text-gray-700">
                I accept the evaluation license terms and agree to use EDON v2 only for evaluation purposes.
              </label>
            </div>

            <Button
              type="submit"
              variant="tactical"
              size="lg"
              className="w-full font-sans tracking-wider"
              disabled={isSubmitting}
            >
              {isSubmitting ? "SUBMITTING..." : "REQUEST DOWNLOAD LINK"}
            </Button>
          </form>

          <div className="mt-8 p-6 bg-gray-50 border border-gray-200 rounded-sm">
            <p className="font-sans text-sm text-gray-600">
              <strong>Note:</strong> Each download link is unique and trackable. Unauthorized sharing of evaluation bundles is prohibited.
            </p>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Download;

