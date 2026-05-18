import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { SignUp } from "@clerk/clerk-react";
import { useSearchParams } from "react-router-dom";

const Signup = () => {
  const [searchParams] = useSearchParams();
  // Default to free so every signup gets free trial without clicking a plan
  const plan = searchParams.get("plan") || "free";
  const fallbackRedirectUrl = `/onboarding/success?plan=${plan}`;

  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Sign Up | EDON"
        description="Create your EDON account and start using physical AI governance"
        canonical="https://edoncore.com/signup"
      />
      <Navigation />
      
      <section className="bg-gray-50 py-24 px-8 pt-32">
        <div className="max-w-md mx-auto flex flex-col items-center">
          <h1 className="font-sans text-4xl font-bold text-black mb-2">
            Get Started
          </h1>
          <p className="font-sans text-lg text-gray-600 mb-8">
            Create your account to access EDON Console
          </p>
          <SignUp 
            routing="path"
            path="/signup"
            signInUrl="/login"
            fallbackRedirectUrl={fallbackRedirectUrl}
            afterSignUpUrl={fallbackRedirectUrl}
            appearance={{
              elements: {
                rootBox: "mx-auto",
                card: "shadow-lg",
              }
            }}
          />
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Signup;
