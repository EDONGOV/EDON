import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import { Link } from "react-router-dom";

const OEMConfirmation = () => {
  return (
    <div className="min-h-screen bg-white font-sans">
      <Navigation />
      
      <section className="py-32 px-8">
        <div className="max-w-2xl mx-auto text-center">
          <h1 className="font-sans text-5xl font-bold text-black mb-6">
            Application Received
          </h1>
          <p className="font-sans text-xl text-gray-700 mb-8">
            Thank you for your interest in EDON v2. We've received your application and will review it within 2-3 business days.
          </p>
          <p className="font-sans text-lg text-gray-600 mb-12">
            You'll receive an email confirmation shortly with next steps.
          </p>
          <Link
            to="/"
            className="inline-block bg-tactical-cyan text-white font-sans tracking-wider px-8 py-3 hover:bg-tactical-cyan/90 transition-colors"
          >
            RETURN TO HOME
          </Link>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default OEMConfirmation;

