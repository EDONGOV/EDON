import { Link } from "react-router-dom";
import edonLogo from "@/assets/edon-logo.svg";

const companyLinks = [
  { to: "/about", title: "About" },
];

const Footer = () => {
  return (
    <footer className="bg-white border-t border-gray-200 py-16 md:py-20 text-gray-700">
      <div className="max-w-6xl mx-auto px-6">
        <div className="flex flex-col md:flex-row md:items-start gap-12 md:gap-16 lg:gap-20">
          {/* Brand */}
          <div className="shrink-0 md:min-w-[180px]">
            <Link to="/" className="inline-flex items-center gap-3 mb-5">
              <img src={edonLogo} alt="EDON" className="h-8 w-8" />
              <span className="font-space text-lg font-semibold tracking-wide text-black">EDON</span>
            </Link>
          </div>

          {/* Link columns — more spacing between columns */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-12 gap-y-10 md:ml-0 md:flex-1 md:justify-end max-w-md md:max-w-none">
            <div className="min-w-0">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-5">Company</h3>
              <ul className="space-y-3">
                {companyLinks.map((link) => (
                  <li key={link.to}>
                    <Link to={link.to} className="text-sm text-gray-600 hover:text-black transition-colors">
                      {link.title}
                    </Link>
                  </li>
                ))}
                <li>
                  <Link to="/contact" className="text-sm text-gray-600 hover:text-black transition-colors">
                    Contact
                  </Link>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <div className="mt-14 pt-8 border-t border-gray-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 text-xs text-gray-500 font-sans">
          <span>© 2025 EDON. All rights reserved.</span>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
