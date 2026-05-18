import { Card, CardContent } from "@/components/ui/card";

const stages = [
  {
    phase: "Evaluation",
    duration: "30 Days",
    description: "Full engine access with license-enforced evaluation period. All features unlocked for testing and integration.",
  },
  {
    phase: "Production",
    duration: "Per-Device",
    description: "Production licenses with offline activation. Per-device pricing with volume discounts available.",
  },
  {
    phase: "Enterprise / Defense",
    duration: "Custom Terms",
    description: "On-device encrypted models, air-gapped deployment, and custom SLAs for defense and critical infrastructure.",
  },
];

const EvaluationPath = () => {
  return (
    <section className="py-24 bg-background">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="font-barlow text-3xl md:text-4xl font-bold text-foreground uppercase tracking-tight mb-4">
            From Evaluation to Deployment
          </h2>
        </div>

        <div className="grid md:grid-cols-3 gap-8">
          {stages.map((stage, index) => (
            <Card key={index} className="bg-card border-border relative">
              <CardContent className="p-6">
                <div className="mb-4">
                  <span className="text-primary font-barlow text-4xl font-bold">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                </div>
                <h3 className="font-barlow text-xl font-bold text-foreground uppercase mb-2">
                  {stage.phase}
                </h3>
                <p className="text-primary text-sm font-barlow mb-4 uppercase tracking-wider">
                  {stage.duration}
                </p>
                <p className="text-sm text-muted-foreground font-sans leading-relaxed">
                  {stage.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
};

export default EvaluationPath;
