import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { SignIn } from "@clerk/clerk-react";
import { useNavigate, useLocation } from "react-router-dom";

const Login = () => {
  const navigate = useNavigate();
  const location = useLocation();
  // Default to /account instead of /console (console requires subscription)
  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || "/account";

  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Log In | EDON"
        description="Log in to your EDON account"
        canonical="https://edoncore.com/login"
      />
      <Navigation />
      
      <section className="bg-gray-50 py-24 px-8 pt-32">
        <div className="max-w-md mx-auto flex flex-col items-center">
          <h1 className="font-sans text-4xl font-bold text-black mb-2">
            Log In
          </h1>
          <p className="font-sans text-lg text-gray-600 mb-8">
            Access your EDON Console
          </p>
          <SignIn 
            routing="path"
            path="/login"
            signUpUrl="/signup"
            fallbackRedirectUrl="/account"
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

export default Login;
