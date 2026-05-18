import { Card, CardContent } from "@/components/ui/card";
import humanoidIcon from "@/assets/icon-humanoid.jpg";
import droneIcon from "@/assets/icon-drone.jpg";
import wearableIcon from "@/assets/icon-wearable.jpg";
import facilityIcon from "@/assets/icon-facility.jpg";

const platforms = [
  {
    title: "Humanoids",
    description: "Full-body state tracking with real-time motion prediction and environmental awareness for bipedal autonomous systems.",
    icon: humanoidIcon,
  },
  {
    title: "Drones & UGVs",
    description: "Multi-sensor fusion for aerial and ground vehicles. Mission-critical state management for autonomous navigation.",
    icon: droneIcon,
  },
  {
    title: "Wearables & Operators",
    description: "Human-in-the-loop systems with physiological monitoring, AR overlays, and operator state classification.",
    icon: wearableIcon,
  },
  {
    title: "Smart Facilities",
    description: "Building-scale sensor networks for occupancy, environmental control, and automated facility management.",
    icon: facilityIcon,
  },
];

const Platforms = () => {
  return (
    <section id="platforms" className="py-24 bg-background">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="font-barlow text-3xl md:text-4xl font-bold text-foreground uppercase tracking-tight mb-4">
            Built for Modern Embodied Systems
          </h2>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {platforms.map((platform, index) => (
            <Card key={index} className="bg-card border-border hover:border-primary/50 transition-all">
              <CardContent className="p-6">
                <div className="mb-4 h-40 overflow-hidden rounded-md">
                  <img 
                    src={platform.icon} 
                    alt={platform.title}
                    className="w-full h-full object-cover"
                  />
                </div>
                <h3 className="font-barlow text-lg font-bold text-foreground uppercase mb-2">
                  {platform.title}
                </h3>
                <p className="text-sm text-muted-foreground font-sans leading-relaxed">
                  {platform.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Platforms;
