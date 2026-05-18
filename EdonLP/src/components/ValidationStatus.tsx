import { Badge } from "@/components/ui/badge";
import { CheckCircle2, AlertCircle } from "lucide-react";

const validationItems = [
  {
    category: "Performance Benchmarks",
    status: "verified",
    note: "< 10ms latency on reference hardware",
  },
  {
    category: "Model Validation",
    status: "verified",
    note: "Cross-validated on 15K+ hours of real-world data",
  },
  {
    category: "Load Testing",
    status: "verified",
    note: "Sustained 1000 req/s per instance",
  },
  {
    category: "Signed Artifacts",
    status: "warning",
    note: "GPG signatures for all release binaries",
  },
];

const ValidationStatus = () => {
  return (
    <section className="py-24 bg-card">
      <div className="max-w-5xl mx-auto px-6">
        <div className="text-center mb-12">
          <h2 className="font-barlow text-3xl md:text-4xl font-bold text-foreground uppercase tracking-tight mb-4">
            Validation Status
          </h2>
          <p className="text-muted-foreground font-sans">
            Transparent reporting on system validation and testing
          </p>
        </div>

        <div className="space-y-4">
          {validationItems.map((item, index) => (
            <div 
              key={index}
              className="bg-background border border-border rounded-md p-6 flex items-center justify-between gap-6"
            >
              <div className="flex items-center gap-4 flex-1">
                {item.status === "verified" ? (
                  <CheckCircle2 className="w-6 h-6 text-status-active flex-shrink-0" />
                ) : (
                  <AlertCircle className="w-6 h-6 text-status-warning flex-shrink-0" />
                )}
                <div>
                  <h3 className="font-barlow text-lg font-bold text-foreground uppercase mb-1">
                    {item.category}
                  </h3>
                  <p className="text-sm text-muted-foreground font-sans">
                    {item.note}
                  </p>
                </div>
              </div>
              <Badge 
                variant={item.status === "verified" ? "default" : "secondary"}
                className={
                  item.status === "verified" 
                    ? "bg-status-active text-white" 
                    : "bg-status-warning text-background"
                }
              >
                {item.status === "verified" ? "VERIFIED" : "IN PROGRESS"}
              </Badge>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default ValidationStatus;
