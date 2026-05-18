const TacticalFounder = () => {
  return (
    <section className="bg-white py-20 sm:py-24">
      <div className="max-w-4xl mx-auto px-6">
        <div className="mb-12">
          <p className="font-sans text-xs text-gray-500 tracking-widest uppercase mb-4">
            Why Governance Had to Exist
          </p>
          <h2 className="font-sans text-3xl md:text-4xl font-bold text-black mb-4">
            Charlie Biggins
          </h2>
          <p className="font-sans text-base text-gray-600">
            Founder & Architect of EDON
          </p>
        </div>

        <div className="space-y-6 font-sans text-base md:text-lg text-gray-700 leading-relaxed">
          <p>
            Physical AI systems are reaching deployment scale. The question is no longer whether machines can operate autonomously, but whether they can be governed, insured, and held accountable.
          </p>
          
          <p>
            Before the first major incident, before regulatory frameworks are established, before insurance markets collapse, governance must exist. EDON was built to provide that layer.
          </p>

          <div className="rounded-2xl border border-gray-200 bg-[#f7f8fa] p-5 text-black font-semibold">
            Governance had to exist before the first disaster.
          </div>

          <p>
            We're working with institutions, insurers, and OEMs to establish the operational authorization and runtime oversight that makes physical AI deployment defensible at scale.
          </p>
        </div>
      </div>
    </section>
  );
};

export default TacticalFounder;
