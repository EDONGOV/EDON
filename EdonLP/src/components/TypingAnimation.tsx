import { useState, useEffect } from "react";

const TypingAnimation = () => {
  const [displayText, setDisplayText] = useState("");
  const [phase, setPhase] = useState(0); // 0: typing "Project V2", 1: fading, 2: typing "Adaptive Intelligence Engine", 3: fading

  const text1 = "EDON";
  const text2 = "RUNTIME GOVERNANCE";

  useEffect(() => {
    let timeout: NodeJS.Timeout;

    if (phase === 0) {
      // Typing "Project V2"
      if (displayText.length < text1.length) {
        timeout = setTimeout(() => {
          setDisplayText(text1.slice(0, displayText.length + 1));
        }, 100);
      } else {
        // Finished typing, wait then fade
        timeout = setTimeout(() => {
          setPhase(1);
        }, 2000);
      }
    } else if (phase === 1) {
      // Fading out "Project V2"
      if (displayText.length > 0) {
        timeout = setTimeout(() => {
          setDisplayText(displayText.slice(0, -1));
        }, 50);
      } else {
        // Faded out, start typing next text
        setPhase(2);
      }
    } else if (phase === 2) {
      // Typing "Adaptive Intelligence Engine"
      if (displayText.length < text2.length) {
        timeout = setTimeout(() => {
          setDisplayText(text2.slice(0, displayText.length + 1));
        }, 100);
      } else {
        // Finished typing, wait then fade
        timeout = setTimeout(() => {
          setPhase(3);
        }, 2000);
      }
    } else if (phase === 3) {
      // Fading out "Adaptive Intelligence Engine"
      if (displayText.length > 0) {
        timeout = setTimeout(() => {
          setDisplayText(displayText.slice(0, -1));
        }, 50);
      } else {
        // Faded out, loop back to start
        setPhase(0);
      }
    }

    return () => {
      if (timeout) clearTimeout(timeout);
    };
  }, [displayText, phase]);

  return (
    <div className="min-h-[60px] sm:min-h-[80px] md:min-h-[100px] flex items-center justify-center px-4">
      <h1 className="font-condensed text-2xl sm:text-4xl md:text-5xl lg:text-6xl font-bold text-white tracking-widest uppercase break-words text-center">
        {displayText}
        <span className="inline-block w-0.5 sm:w-1 h-8 sm:h-12 md:h-16 bg-white ml-1 sm:ml-2 animate-pulse">|</span>
      </h1>
    </div>
  );
};

export default TypingAnimation;

