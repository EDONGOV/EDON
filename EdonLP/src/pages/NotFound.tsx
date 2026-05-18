import { useLocation, Link } from "react-router-dom";
import { useEffect } from "react";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    if (import.meta.env.DEV) {
      console.error("404 Error: User attempted to access non-existent route:", location.pathname);
    }
  }, [location.pathname]);

  return (
    <div className="flex flex-col min-h-screen bg-white font-sans">
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <h1 className="mb-4 text-4xl font-bold text-black">404</h1>
          <p className="mb-4 text-xl text-gray-700">Oops! Page not found</p>
          <Link to="/" className="text-black underline hover:text-gray-600 transition-colors">
            Return to Home
          </Link>
        </div>
      </div>
      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default NotFound;
