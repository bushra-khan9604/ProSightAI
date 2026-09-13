import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronRight } from 'lucide-react';

export const StatCard = ({
  children,
  className = '',
  style = {},
  delay = 0,
  floatDuration = 6,
  floatDistance = 4,
  hasArrow = true,
  onClick
}) => {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.94, y: 12 }}
      animate={{
        opacity: 1,
        scale: 1,
        y: [0, -floatDistance, 0]
      }}
      transition={{
        opacity: { duration: 0.6, delay },
        scale: { duration: 0.6, delay },
        y: {
          duration: floatDuration,
          repeat: Infinity,
          ease: 'easeInOut',
          delay: delay + 0.6
        }
      }}
      onClick={onClick}
      style={{
        background: 'rgba(5, 20, 40, 0.90)',
        border: '1px solid rgba(0, 170, 255, 0.55)',
        boxShadow: '0 0 25px rgba(0, 170, 255, 0.25), inset 0 0 15px rgba(0, 170, 255, 0.1)',
        ...style
      }}
      className={`relative px-4 py-3 sm:px-5 sm:py-3.5 rounded-2xl backdrop-blur-md transition-all duration-300 hover:border-cyan-400 hover:shadow-[0_0_35px_rgba(6,182,212,0.4)] ${className}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {children}
        </div>
        {hasArrow && (
          <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-cyan-300 group-hover:translate-x-0.5 transition-all" />
        )}
      </div>
    </motion.div>
  );
};

// Counter Hook for Number Animation
export const useAnimatedCounter = (endValue, duration = 1500, delay = 700) => {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let startTimestamp = null;
    let animationFrame = null;

    const timer = setTimeout(() => {
      const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        setCount(Math.floor(progress * endValue));

        if (progress < 1) {
          animationFrame = requestAnimationFrame(step);
        } else {
          setCount(endValue);
        }
      };

      animationFrame = requestAnimationFrame(step);
    }, delay);

    return () => {
      clearTimeout(timer);
      if (animationFrame) cancelAnimationFrame(animationFrame);
    };
  }, [endValue, duration, delay]);

  return count;
};
