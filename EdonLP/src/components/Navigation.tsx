import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { useState, useEffect, useRef } from "react";
import { Menu, X, User, LogIn, LogOut, ChevronDown } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useAuth } from "@clerk/clerk-react";

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

/** Set to true to hide Account and Sign in from the nav. */
const HIDE_ACCOUNT_SIGNIN = true;

const companyLinks = [
  { to: "/about", title: "About" },
];

const HOVER_DELAY_MS = 120;

function NavDropdown({
  label,
  open,
  onOpenChange,
  wide,
  children,
}: {
  label: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  wide?: boolean;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const leaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearLeaveTimer = () => {
    if (leaveTimerRef.current) {
      clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
  };

  const handleEnter = () => {
    clearLeaveTimer();
    onOpenChange(true);
  };

  const handleLeave = () => {
    leaveTimerRef.current = setTimeout(() => onOpenChange(false), HOVER_DELAY_MS);
  };

  useEffect(() => {
    return () => clearLeaveTimer();
  }, []);

  return (
    <div
      ref={ref}
      className="relative"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      <button
        type="button"
        className="flex items-center gap-1 px-3 py-2 text-sm font-medium text-black hover:text-gray-600 transition-colors min-h-[44px]"
        aria-expanded={open}
        aria-haspopup="true"
      >
        {label}
        <ChevronDown className={`h-4 w-4 transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      {open && wide ? (
        <div
          className="fixed left-0 right-0 top-16 z-40 pt-2"
          onMouseEnter={handleEnter}
          onMouseLeave={handleLeave}
        >
          <div className="bg-white w-full py-8 shadow-[0_4px_20px_rgba(0,0,0,0.08)]">
            <div className="mx-auto max-w-6xl px-6">{children}</div>
          </div>
        </div>
      ) : open ? (
        <div className="absolute left-0 top-full pt-2 z-50">
          <div className="rounded-xl border border-gray-200/90 bg-white py-5 px-5 min-w-[200px] shadow-[0_20px_50px_-12px_rgba(0,0,0,0.15)]">
            {children}
          </div>
        </div>
      ) : null}
    </div>
  );
}
type NavUIProps = { isLoaded: boolean; isSignedIn: boolean; onSignOut?: () => void };

function NavUI({ isLoaded, isSignedIn, onSignOut }: NavUIProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [companyOpen, setCompanyOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!mobileMenuOpen && menuButtonRef.current) {
      setTimeout(() => menuButtonRef.current?.blur(), 100);
    }
  }, [mobileMenuOpen]);

  return (
    <nav className="fixed top-0 left-0 z-50 w-full safe-area-top bg-white/80 backdrop-blur-sm border-b border-gray-100">
      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-1">
          <Link to="/" className="font-space text-sm font-semibold tracking-wide min-h-[44px] flex items-center text-black pr-2">
            EDON
          </Link>

          {/* Desktop: Company dropdown (hover to open) */}
          <div className="hidden md:flex items-center gap-0">
            <NavDropdown label="Company" open={companyOpen} onOpenChange={setCompanyOpen}>
              <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 block mb-3">Company</span>
              <div className="flex flex-col gap-0.5 min-w-[200px]">
                {companyLinks.map((l) => (
                  <Link key={l.to} to={l.to} onClick={() => setCompanyOpen(false)} className="py-2.5 text-sm font-medium text-black hover:text-gray-600 rounded-lg px-2 -mx-2 hover:bg-gray-50 transition-colors">
                    {l.title}
                  </Link>
                ))}
              </div>
            </NavDropdown>
          </div>
        </div>

        {/* Desktop: Get in touch + Account / Sign In */}
        <div className="hidden md:flex items-center gap-3">
          <Button asChild variant="outline" size="sm" className="rounded-full border-gray-300 bg-white text-black hover:bg-gray-50 hover:border-gray-400 font-medium text-sm h-10 px-5 transition-all">
            <Link to="/contact">Get in touch</Link>
          </Button>
          {!HIDE_ACCOUNT_SIGNIN && (
          <>
          {isLoaded && isSignedIn ? (
            <>
              <Link to="/account" className="p-2 text-black hover:text-gray-600 transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center" aria-label="Account">
                <User className="h-4 w-4" />
              </Link>
              <Button variant="ghost" size="icon" className="text-gray-700 hover:bg-gray-100 min-h-[44px] min-w-[44px]" onClick={() => onSignOut?.()} aria-label="Sign out">
                <LogOut className="h-4 w-4" />
              </Button>
            </>
          ) : (
            <Link to="/login" className={`px-3 py-2 text-sm font-medium text-black hover:text-gray-600 transition-colors min-h-[44px] flex items-center gap-2${!isLoaded ? " pointer-events-none opacity-50" : ""}`} aria-label="Sign in">
              <LogIn className="h-4 w-4" />
              Sign in
            </Link>
          )}
          </>
          )}
        </div>

        {/* Mobile Menu */}
        <div className="md:hidden flex items-center gap-1">
          <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
            <SheetTrigger asChild>
              <Button
                ref={menuButtonRef}
                variant="ghost"
                size="icon"
                className={`text-gray-700 hover:bg-gray-100 min-h-[44px] min-w-[44px] transition-opacity ${mobileMenuOpen ? 'pointer-events-none opacity-0' : 'pointer-events-auto opacity-100'}`}
                aria-label="Toggle menu"
              >
                <Menu className="h-6 w-6" />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-[85vw] max-w-sm bg-white border-gray-200 p-0 [&>button]:!hidden">
            <div className="flex flex-col h-full">
              <div className="flex items-center justify-between p-6 border-b border-gray-200">
                <span className="font-space text-xl font-semibold tracking-wide text-black">EDON</span>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setMobileMenuOpen(false)}
                  className="text-gray-700 hover:bg-gray-100 min-h-[44px] min-w-[44px]"
                  aria-label="Close menu"
                >
                  <X className="h-6 w-6" />
                </Button>
              </div>
              <nav className="flex-1 flex flex-col p-6 gap-1">
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 px-4 pt-2 pb-1">Company</span>
                {companyLinks.map((l) => (
                  <Link key={l.to} to={l.to} onClick={() => setMobileMenuOpen(false)} className="font-sans text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-50 py-3 px-4 rounded-lg flex items-center">
                    {l.title}
                  </Link>
                ))}
                <Link to="/contact" onClick={() => setMobileMenuOpen(false)} className="font-sans text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-50 py-4 px-4 rounded-lg mt-2 flex items-center">
                  Contact
                </Link>
                {!HIDE_ACCOUNT_SIGNIN && (isLoaded && isSignedIn ? (
                  <>
                    <Link
                      to="/account"
                      onClick={() => setMobileMenuOpen(false)}
                      className="font-sans text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-50 transition-colors py-4 px-4 rounded-lg min-h-[44px] flex items-center gap-3"
                      aria-label="Account"
                    >
                      <User className="h-5 w-5 shrink-0" />
                      Account
                    </Link>
                    <Button
                      variant="ghost"
                      className="font-sans text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-50 justify-start gap-3 py-4 px-4 rounded-lg min-h-[44px] w-full"
                      onClick={() => { onSignOut?.(); setMobileMenuOpen(false); }}
                      aria-label="Sign out"
                    >
                      <LogOut className="h-5 w-5 shrink-0" />
                      Sign out
                    </Button>
                  </>
                ) : (
                  <Link
                    to="/login"
                    onClick={() => setMobileMenuOpen(false)}
                    className={`font-sans text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-50 transition-colors py-4 px-4 rounded-lg min-h-[44px] flex items-center gap-3${!isLoaded ? " opacity-50 pointer-events-none" : ""}`}
                  >
                    <LogIn className="h-5 w-5 shrink-0" />
                    Sign in
                  </Link>
                ))}
              </nav>
            </div>
          </SheetContent>
        </Sheet>
        </div>
      </div>
    </nav>
  );
}

function NavWithClerk() {
  const { isLoaded, isSignedIn, signOut } = useAuth();
  return (
    <NavUI
      isLoaded={isLoaded}
      isSignedIn={isSignedIn}
      onSignOut={signOut ? () => signOut({ redirectUrl: "/" }) : undefined}
    />
  );
}

const Navigation = () =>
  PUBLISHABLE_KEY ? <NavWithClerk /> : <NavUI isLoaded={true} isSignedIn={false} />;

export default Navigation;
