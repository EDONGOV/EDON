import React, { useState } from "react";
import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Button } from "@/components/ui/button";
import edonLogo from "@/assets/edon-logo.svg";

interface Article {
  id: string;
  title: string;
  image: string;
  date: string;
  author: string;
  excerpt: string;
  content: string;
}

const News = () => {
  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null);

  const articles: Article[] = [
    {
      id: "future-of-memphis",
      title: "FUTURE OF MEMPHIS",
      image: "/placeholder.svg",
      date: "DECEMBER 12, 2025",
      author: "Team EDON",
      excerpt: "Not the Next Silicon Valley. Something Bigger. Memphis is positioned to become something more important—the physical backbone of the modern economy.",
      content: `Not the Next Silicon Valley. Something Bigger.

Memphis isn't trying to copy Silicon Valley. Memphis is positioned to become something more important. Silicon Valley built the digital economy. Memphis can run the physical one.

Our Starting Point

Memphis already sits at the center of global movement: World's largest air cargo hub, Mississippi River shipping corridor, major rail and interstate crossroads, and a deep logistics and industrial base. The physical backbone of the modern economy already runs through this city.

The Next Layer: Physical AI

The next chapter is about building intelligence on top of that backbone: Robotics & humanoids, autonomous logistics (ground, air, river), smart ports & warehouses, energy-resilient infrastructure (batteries, microgrids, grid intelligence), and defense & disaster-response automation. Not just apps. Not just dashboards. Machines that move the real economy.

What Memphis Can Become

If we execute, Memphis becomes: A global hub for robotics and autonomy, a national center for energy-resilient infrastructure, and a frontline city for defense and disaster-response logistics. In simple terms: From moving boxes → to running the machines that move the world.

Our Belief

The future of Memphis is: Physical, autonomous, and energy-intelligent. And it's closer than most people think.`
    },
    {
      id: "humanoid-bottleneck",
      title: "A Memphis Founder May Have Just Removed the Biggest Bottleneck in Humanoid Robotics",
      image: "/placeholder.svg",
      date: "NOVEMBER 27, 2025",
      author: "Team EDON",
      excerpt: "EDON demonstrates a 97.5 percent reduction in required human safety interventions, while maintaining full system stability.",
      content: `For years, humanoid robots have promised to change the world. They can walk, carry, lift, and manipulate objects with growing precision. Yet one critical limitation has quietly held the entire industry back. Most humanoids still require constant human supervision to prevent failures in unpredictable environments.

This week, a small Memphis-based startup called EDON claims it has crossed that threshold.

In recent high-stress humanoid simulations, EDON demonstrated a 97.5 percent reduction in required human safety interventions, while maintaining full system stability. The result held consistently across multiple unseen test environments, not just a single scripted scenario.

In simple terms, robots that previously needed dozens of human takeovers per session were able to operate almost entirely on their own.

"This is the moment where supervision stops scaling linearly with robots," said EDON founder Charlie Biggins. "For the first time, we're seeing conditions where one human can realistically oversee many machines without constant intervention."

The Hidden Bottleneck in Humanoid Robotics

While public attention has focused on humanoid hardware, dexterous hands, and large AI models, operators inside the industry have faced a quieter reality. True autonomy breaks down under stress. Unexpected pushes, delays, oscillations, terrain shifts, and compounding errors force humans to step in repeatedly.

That supervision requirement makes large-scale deployment economically fragile.

"The robots look autonomous on stage," one robotics engineer familiar with the space said, "but behind the scenes, humans are still doing a lot of invisible work."

EDON's breakthrough directly targets that gap.

How EDON Works

Rather than replacing the robot's main control system, EDON acts as a real-time adaptive nervous system layered on top of existing controllers. It watches for early warning signals that instability is building and adjusts behavior before a failure occurs.

In its latest tests, EDON's system learned to recognize the patterns that normally lead to emergency human overrides and prevent them in advance. The result was a dramatic collapse in takeover events without destabilizing the robot.

"What surprised us most wasn't just the reduction," Biggins said. "It was how clean the behavior became. The system wasn't thrashing or fighting the physics. It was simply staying ahead of dangerous states."

Why the Industry Is Paying Attention

At scale, the implications are significant.

A 97.5 percent reduction in intervention means that instead of one operator babysitting one robot, a single person could supervise dozens. That shift alone could unlock massive new deployment scenarios in logistics, manufacturing, healthcare, and disaster response.

"If this holds up outside of simulation, this changes the math of humanoid robotics," said another industry source. "You go from a novelty to something that can actually scale."

What's Next for EDON

The company is now expanding testing into more extreme conditions and preparing for its first OEM pilot integrations. Hardware validation will be the next critical step.

For Biggins, the moment is both technical and personal.

"People talk about robots replacing humans," he said. "That's not what this is about. This is about removing the invisible human burden that's been propping up autonomy behind the scenes. Once that goes away, everything accelerates."

If EDON's results continue to hold as they move beyond simulation, this Memphis startup may have quietly solved one of the most stubborn problems in humanoid robotics.

And the industry is watching closely.`
    }
  ];

  // If an article is selected, show the detailed view
  if (selectedArticle) {
    return (
      <div className="min-h-screen bg-white font-sans">
        <SEOHead
          title={`${selectedArticle.title} | EDON News`}
          description={selectedArticle.excerpt}
          keywords="EDON news, humanoid robotics, adaptive intelligence, embodied AI"
          canonical={`https://edoncore.com/news/${selectedArticle.id}`}
        />
        <Navigation />
        
        <div className="pt-28 pb-20 px-6">
          <div className="max-w-7xl mx-auto">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">
              {/* Left Sidebar - Author Info */}
              <div className="lg:col-span-3">
                <div className="sticky top-24">
                  <div className="flex flex-col items-start gap-6">
                    {/* Author Icon - EDON Logo */}
                    <div className="w-16 h-16 rounded-full bg-[#f4f4f4] flex items-center justify-center p-2 border border-gray-200">
                      <img src={edonLogo} alt="EDON" className="w-full h-full object-contain" />
                    </div>
                    
                    <div className="flex flex-col gap-2">
                      <p className="font-sans text-xs tracking-widest text-gray-500 uppercase">AUTHOR</p>
                      <p className="font-sans text-lg font-medium text-black">{selectedArticle.author}</p>
                      <p className="font-sans text-xs tracking-widest text-gray-500 uppercase mt-4">{selectedArticle.date}</p>
                    </div>
                    
                    <Button
                      onClick={() => setSelectedArticle(null)}
                      className="bg-[#b8b8b8] hover:bg-[#a3a3a3] text-black rounded-full px-6 py-3 font-sans text-xs tracking-widest uppercase w-full mt-2 transition-all duration-200"
                    >
                      READ MORE
                    </Button>
                  </div>
                </div>
              </div>

              {/* Main Article Content */}
              <div className="lg:col-span-9">
                <h1 className="font-sans text-4xl md:text-5xl lg:text-6xl font-bold text-black mb-10 leading-tight">
                  {selectedArticle.title}
                </h1>
                
                <div className="prose max-w-none">
                  <div className="font-sans text-base md:text-lg text-gray-800 leading-relaxed space-y-6">
                    {selectedArticle.content.split('\n\n').map((paragraph, index) => {
                      // Check if paragraph is a heading (all caps or starts with specific patterns)
                      const isHeading = paragraph.length < 100 && (
                        paragraph === paragraph.toUpperCase() || 
                        paragraph.match(/^(How|Why|What|The|If)/)
                      );
                      
                      return (
                        <p 
                          key={index} 
                          className={isHeading ? 'font-bold text-black text-xl md:text-2xl mb-4 mt-8' : 'text-gray-700'}
                        >
                          {paragraph}
                        </p>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <Footer />
        <ScrollToTop />
      </div>
    );
  }

  // Show article cards listing
  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="EDON News & Announcements"
        description="Latest news, press releases, and updates from EDON. Stay informed about adaptive intelligence for embodied AI, product releases, and partnerships."
        keywords="EDON news, EDON announcements, embodied AI news, robotics updates"
        canonical="https://edoncore.com/news"
      />
      <Navigation />
      
      {/* Hero Section */}
      <section className="pt-28 pb-12 px-6 bg-white">
        <div className="max-w-6xl mx-auto">
          <h1 className="font-sans text-4xl md:text-5xl font-semibold text-black mb-2">
            News
          </h1>
          <p className="font-sans text-sm text-gray-500 max-w-2xl">
            Updates, analysis, and announcements from EDON.
          </p>
        </div>
      </section>

      {/* Articles List - Forbes Style */}
      <section className="pb-24 px-6 bg-white">
        <div className="max-w-5xl mx-auto">
          <div className="space-y-8">
            {articles.map((article, index) => (
              <article
                key={article.id}
                className="border-b border-gray-200 pb-8 last:border-b-0 hover:bg-[#f7f7f7] transition-colors cursor-pointer rounded-2xl px-4 py-6"
                onClick={() => setSelectedArticle(article)}
              >
                <div className="flex flex-col gap-3">
                  {/* Date */}
                  <p className="font-sans text-xs text-gray-500 uppercase tracking-wider">
                    {article.date}
                  </p>
                  
                  {/* Title */}
                  <h2 className="font-sans text-2xl md:text-3xl font-semibold text-black leading-tight">
                    {article.title}
                  </h2>
                  
                  {/* Excerpt */}
                  <p className="font-sans text-base text-gray-600 leading-relaxed">
                    {article.excerpt}
                  </p>
                  
                  {/* Read Article Link */}
                  <div className="pt-2">
                    <a
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedArticle(article);
                      }}
                      className="font-sans text-sm text-gray-700 hover:text-black underline cursor-pointer uppercase tracking-wide transition-colors inline-block"
                    >
                      READ ARTICLE →
                    </a>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default News;
