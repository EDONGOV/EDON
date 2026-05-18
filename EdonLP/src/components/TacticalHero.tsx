import React, { useEffect, useRef } from "react";
import TypingAnimation from "./TypingAnimation";

const TacticalHero = () => {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    // Set video properties
    video.muted = true;
    video.loop = true;
    video.playsInline = true;
    video.controls = false;
    video.setAttribute("webkit-playsinline", "true");
    video.setAttribute("playsinline", "true");
    video.setAttribute("x5-playsinline", "true");

    // Function to play video
    const playVideo = () => {
      video.play().catch(() => {
        // Silently handle play errors
      });
    };

    // Try to autoplay when video is ready
    const attemptAutoplay = () => {
      playVideo();
    };

    // Try autoplay on multiple events
    if (video.readyState >= 2) {
      attemptAutoplay();
    } else {
      video.addEventListener("canplay", attemptAutoplay, { once: true });
      video.addEventListener("loadeddata", attemptAutoplay, { once: true });
    }

    // Handle video ended to ensure looping
    const handleEnded = () => {
      video.currentTime = 0;
      playVideo();
    };
    video.addEventListener("ended", handleEnded);

    // Handle touch/click anywhere on the page to start video
    const handleUserInteraction = () => {
      playVideo();
    };

    // Listen for any touch or click
    document.addEventListener("touchstart", handleUserInteraction, { once: true, passive: true });
    document.addEventListener("click", handleUserInteraction, { once: true });

    return () => {
      video.removeEventListener("canplay", attemptAutoplay);
      video.removeEventListener("loadeddata", attemptAutoplay);
      video.removeEventListener("ended", handleEnded);
      document.removeEventListener("touchstart", handleUserInteraction);
      document.removeEventListener("click", handleUserInteraction);
    };
  }, []);

  // Handle touch/click on the section itself
  const handleSectionInteraction = () => {
    const video = videoRef.current;
    if (video) {
      video.play().catch(() => {});
    }
  };

  const inlineProps: Record<string, string> = {
    "webkit-playsinline": "true",
    "x5-playsinline": "true",
  };

  return (
    <section 
      className="relative min-h-[85vh] flex items-center justify-center overflow-hidden bg-black z-0"
      onClick={handleSectionInteraction}
      onTouchStart={handleSectionInteraction}
    >
      {/* Background Video */}
      <div className="absolute inset-0 w-full h-full">
        <video
          ref={videoRef}
          autoPlay
          loop
          muted
          playsInline
          preload="auto"
          controls={false}
          disablePictureInPicture
          disableRemotePlayback
          className="absolute inset-0 w-full h-full object-cover pointer-events-none"
          style={{
            objectFit: "cover",
            objectPosition: "center center"
          }}
          {...inlineProps}
        >
          <source src="/1.mp4" type="video/mp4" />
          <source src="/1.mov" type="video/quicktime" />
          Your browser does not support the video tag.
        </video>

        {/* Dark overlay */}
        <div className="absolute inset-0 bg-black/75 pointer-events-none" />
      </div>

      {/* Foreground Content */}
      <div className="relative z-10 max-w-6xl mx-auto px-6 sm:px-8 text-center safe-area-top safe-area-bottom">
        <TypingAnimation />

        <div className="font-sans text-xs sm:text-sm text-gray-300 tracking-widest mt-8 sm:mt-10 px-4 mb-6 max-w-2xl mx-auto leading-relaxed">
          Enforce policy, manage risk, and produce audit-grade logs across tool-using AI and real-world systems.
        </div>

      </div>

    </section>
  );
};

export default TacticalHero;
