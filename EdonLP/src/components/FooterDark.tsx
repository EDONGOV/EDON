import { Link } from "react-router-dom";
import edonLogo from "@/assets/edon-logo.svg";

const FooterDark = () => {
  return (
    <footer className="bg-black border-t border-gray-800 py-12">
      <div className="max-w-7xl mx-auto px-6">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          <Link to="/" className="flex items-center">
            <img src={edonLogo} alt="EDON" className="h-8 w-8" />
          </Link>
          <div className="flex flex-wrap items-center justify-center gap-6">
            <a href="https://platform.edoncore.com" target="_blank" rel="noopener noreferrer" className="font-condensed text-xs tracking-widest text-white hover:opacity-70 transition-colors uppercase">
              Developer Platform
            </a>
            <Link to="/docs" className="font-condensed text-xs tracking-widest text-white hover:opacity-70 transition-colors uppercase">
              Docs
            </Link>
            <Link to="/contact" className="font-condensed text-xs tracking-widest text-white hover:opacity-70 transition-colors uppercase">
              Contact
            </Link>
          </div>
          <div className="text-sm text-gray-400 font-sans">
            © 2025 EDON. All rights reserved.
          </div>
        </div>
      </div>
    </footer>
  );
};

export default FooterDark;

