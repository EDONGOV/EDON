import React from "react";
import { Link } from "react-router-dom";

const TacticalPartnerships = () => {
  const platforms = [
    "HUMANOID ROBOTICS",
    "AUTONOMOUS DRONES",
    "SMART WEARABLES",
    "INDUSTRIAL AUTOMATION"
  ];

  return (
    <section className="bg-[#f7f8fa] py-20 sm:py-24">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-12">
          <p className="font-sans text-xs text-gray-500 tracking-widest uppercase mb-4">
            Deployment Anchors
          </p>
          <h2 className="font-sans text-3xl md:text-4xl font-bold text-black mb-4">
            Institutional References
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-12">
          {platforms.map((platform, i) => (
            <div key={i} className="bg-white border border-gray-200 p-6 text-center rounded-2xl shadow-sm hover:border-tactical-cyan/40 transition-colors">
              <p className="font-sans text-xs tracking-widest text-black uppercase">
                {platform}
              </p>
            </div>
          ))}
        </div>

        <div className="bg-white border border-gray-200 p-8 sm:p-10 text-center rounded-2xl shadow-sm">
          <h3 className="font-sans text-2xl sm:text-3xl font-bold text-black mb-4">
            Request OEM Evaluation
          </h3>
          <p className="font-sans text-gray-700 mb-8 max-w-2xl mx-auto">
            30-day full-feature evaluation for qualified OEMs. Includes complete SDK, documentation, and integration support.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/oem/apply">
              <button className="bg-tactical-cyan text-white font-sans tracking-wider px-8 py-3 hover:bg-tactical-cyan/90 transition-colors rounded-full">
                REQUEST ACCESS
              </button>
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
};

export default TacticalPartnerships;
