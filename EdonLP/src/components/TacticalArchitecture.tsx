import { Link } from "react-router-dom";

const TacticalArchitecture = () => {
  return (
    <section className="bg-[#f7f8fa] py-20 sm:py-24">
      <div className="max-w-6xl mx-auto px-6">
        <div>
          <p className="font-sans text-xs text-gray-500 tracking-widest uppercase mb-4">
            System Architecture
          </p>
          <h2 className="font-sans text-3xl md:text-4xl font-bold text-black mb-10">
            Built for mission-critical systems
          </h2>

          <div className="bg-white border border-gray-200 rounded-2xl p-6 sm:p-8 shadow-sm">
            <h3 className="font-sans text-lg font-semibold text-black mb-3">
              Runtime Governance Control Plane
            </h3>
            <p className="font-sans text-gray-700 leading-relaxed">
              Safety envelopes enforced at runtime independent of model behavior. Autonomy state machine with bounded modes and logged transitions. Audit-grade event logging and evidence capture for incident reconstruction. Operational authorization is license-enforced and tamper-resistant.
            </p>
          </div>

          <div className="mt-8">
            <Link to="/docs" className="font-sans text-tactical-cyan hover:text-tactical-cyan/80 underline text-base">
              View integration docs →
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
};

export default TacticalArchitecture;
