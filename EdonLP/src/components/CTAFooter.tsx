import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import edonLogo from "@/assets/edon-logo.svg";

const CTAFooter = () => {
  return (
    <section className="py-20 bg-charcoal border-t border-border">
      <div className="max-w-5xl mx-auto px-6">
        <div className="flex flex-col md:flex-row items-center justify-between gap-8">
          <div className="text-center md:text-left">
            <h2 className="font-barlow text-2xl md:text-3xl font-bold text-foreground uppercase tracking-tight mb-2">
              Ready to Deploy EDON v2?
            </h2>
            <p className="text-muted-foreground font-sans">
              Request an evaluation call or download the full bundle
            </p>
          </div>

          <div className="flex flex-col sm:flex-row gap-4">
            <Button variant="military" size="lg" className="text-sm whitespace-nowrap">
              Request OEM Evaluation Call
            </Button>
            <Button variant="military-outline" size="lg" className="text-sm whitespace-nowrap">
              Get EDON V2 Bundle
            </Button>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-16 pt-8 border-t border-border flex flex-col md:flex-row items-center justify-between gap-4">
          <Link to="/" className="flex items-center">
            <img src={edonLogo} alt="EDON" className="h-8 w-8" />
          </Link>
          <div className="text-sm text-muted-foreground font-sans">
            © 2025 EDON. All rights reserved.
          </div>
        </div>
      </div>
    </section>
  );
};

export default CTAFooter;
