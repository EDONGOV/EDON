import { Button } from "@/components/ui/button";
import heroImage from "@/assets/hero-control-room.jpg";

const Hero = () => {
  return (
    <section className="relative h-screen flex items-end">
      {/* Background Image with Overlay */}
      <div 
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: `url(${heroImage})` }}
      >
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-background/30" />
      </div>

      {/* Content */}
      <div className="relative z-10 max-w-7xl mx-auto px-6 pb-24 w-full">
        <div className="max-w-3xl">
          <h1 className="font-barlow text-5xl md:text-7xl font-bold text-foreground mb-4 tracking-tight uppercase">
            Adaptive Intelligence for Embodied Systems
          </h1>
          <p className="text-xl md:text-2xl text-muted-foreground mb-8 font-sans">
            Trusted state engine for humanoids, drones, and autonomous platforms.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 mb-6">
            <Button variant="military" size="lg" className="text-sm">
              Download V2 OEM Eval
            </Button>
            <Button variant="military-outline" size="lg" className="text-sm">
              View Integration Docs
            </Button>
          </div>

          <p className="text-xs text-muted-foreground font-sans">
            30-day evaluation • REST · gRPC · WebSocket · SDKs
          </p>
        </div>
      </div>
    </section>
  );
};

export default Hero;
