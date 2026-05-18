const TechnicalSummary = () => {
  return (
    <section className="py-24 bg-card">
      <div className="max-w-7xl mx-auto px-6">
        <div className="grid lg:grid-cols-2 gap-12">
          {/* Left: Features */}
          <div className="space-y-6">
            <h2 className="font-barlow text-2xl md:text-3xl font-bold text-foreground uppercase tracking-tight mb-8">
              Technical Overview
            </h2>
            <ul className="space-y-4 text-muted-foreground font-sans">
              <li className="flex items-start gap-3">
                <span className="text-primary mt-1">▸</span>
                <span>Multimodal fusion: physiological, motion, environmental, and task state</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-primary mt-1">▸</span>
                <span>High-dimensional CAV vectors computed in real-time with sub-10ms latency</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-primary mt-1">▸</span>
                <span>REST / gRPC / WebSocket streaming APIs</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-primary mt-1">▸</span>
                <span>License-enforced OEM evaluation available for qualified partners</span>
              </li>
            </ul>
          </div>

          {/* Right: Code Example */}
          <div>
            <div className="bg-background border border-border rounded-md p-6 font-mono text-sm overflow-x-auto">
              <pre className="text-foreground">
                <code>{`from edon import EdonClient

client = EdonClient(
    api_key="eval_...",
    endpoint="https://api.edoncore.com/v2"
)

# Stream real-time CAV vectors
for cav in client.cav():
    print(f"State: {cav.vector}")
    print(f"Confidence: {cav.confidence}")
    
    # Access fused modalities
    if cav.alert_level > 0.7:
        trigger_alert(cav)`}</code>
              </pre>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default TechnicalSummary;
