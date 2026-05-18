import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

const ThankYou = () => {
  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Thank you | EDON"
        description="Your payment was successful."
        canonical="https://edoncore.com/thank-you"
      />
      <Navigation />

      <section className="py-32 px-8">
        <div className="max-w-2xl mx-auto text-center">
          <h1 className="font-sans text-5xl font-bold text-black mb-6">
            Thank you for your payment
          </h1>
          <p className="font-sans text-xl text-gray-700 mb-8">
            Your subscription is active. You can use your account and dashboard right away.
          </p>
          <p className="font-sans text-lg text-gray-600 mb-12">
            If you have any questions, visit your Account page or contact support.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            {/* Agent UI link points to local dev in DEV, prod domain in PROD */}
            <Link to="/">
              <Button
                variant="default"
                className="font-sans font-medium px-6 py-3 rounded-full bg-tactical-cyan text-primary-foreground hover:opacity-90 inline-flex items-center gap-2"
              >
                <ArrowLeft className="h-4 w-4" />
                Return to home
              </Button>
            </Link>
            <Link to="/account">
              <Button
                variant="outline"
                className="font-sans font-medium px-6 py-3 rounded-full border-gray-300"
              >
                Go to Account
              </Button>
            </Link>
            <Link to="/agent-ui">
              <Button
                variant="outline"
                className="font-sans font-medium px-6 py-3 rounded-full border-gray-300"
              >
                Open Agent UI
              </Button>
            </Link>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default ThankYou;
