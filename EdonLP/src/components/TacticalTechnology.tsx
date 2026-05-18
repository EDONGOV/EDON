import { useRef } from "react";

const TacticalTechnology = () => {
  const sectionRef = useRef<HTMLDivElement>(null);

  const specs = [
    { 
      label: "RUNTIME ENFORCEMENT", 
      value: "Active", 
      unit: "Continuous governance",
      type: "text" as const
    },
    { 
      label: "AUTONOMY STATE CONTROL", 
      value: "Dynamic", 
      unit: "Risk modulation",
      type: "text" as const
    },
    { 
      label: "INCIDENT CONTAINMENT", 
      value: "Auditable", 
      unit: "Post-failure reconstruction",
      type: "text" as const
    },
    { 
      label: "OPERATIONAL AUTHORIZATION", 
      value: "Binary", 
      unit: "EOA deployment-level",
      type: "text" as const
    },
  ];


  return (
    <section ref={sectionRef} className="bg-white py-12 sm:py-16 md:py-24">
      <div className="max-w-6xl mx-auto px-6 sm:px-8">
        <div className="mb-8 sm:mb-12 md:mb-16">
          <p className="font-sans text-xs text-gray-500 tracking-widest uppercase mb-3 sm:mb-4">
            Governance Controls
          </p>
          <h2 className="font-sans text-3xl sm:text-4xl font-bold text-black mb-4">
            Runtime Enforcement
          </h2>
          <p className="font-sans text-base sm:text-lg text-gray-700 mb-6">
            Autonomy state control, incident containment, and continuous risk modulation.
          </p>
          <p className="font-sans text-sm text-gray-500 mb-8">
            Technical capabilities enable governance:
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
          {specs.map((spec, i) => (
            <div key={i} className="bg-white border border-gray-200 p-6 rounded-2xl shadow-sm hover:border-tactical-cyan/40 transition-colors">
              <p className="font-sans text-xs tracking-widest text-gray-500 mb-3 uppercase">
                {spec.label}
              </p>
              <p className="font-sans text-3xl sm:text-4xl font-bold text-tactical-cyan mb-2">
                {spec.value}
              </p>
              <p className="font-sans text-xs sm:text-sm text-gray-500">
                {spec.unit}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default TacticalTechnology;
