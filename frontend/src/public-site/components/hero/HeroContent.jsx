import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Play } from 'lucide-react';

export const HeroContent = ({ onStartChat, onWatchDemo }) => {
  const navigate = useNavigate();

  const handleStartTrial = () => {
    if (onStartChat) onStartChat();
    navigate('/login');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8 }}
      className="text-left space-y-6 max-w-[720px]"
    >
      {/* 1. Small Eyebrow above heading */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1 }}
        className="flex items-center gap-2.5 text-[#22d3ee] text-[13px] sm:text-[14px] font-semibold tracking-[0.2em] uppercase"
      >
        <span className="flex items-center gap-1 text-cyan-400">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
          <span className="w-3 h-[2px] bg-cyan-400" />
        </span>
        <span>AI-POWERED CONSTRUCTION INSIGHTS</span>
      </motion.div>

      {/* 2. Main Title */}
      <motion.h1
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="font-extrabold tracking-tight leading-[1.05]"
      >
        <span className="block text-[54px] sm:text-[70px] lg:text-[84px] text-white">
          ProSight{' '}
          <span className="bg-gradient-to-r from-cyan-400 via-blue-400 to-cyan-300 bg-clip-text text-transparent">
            AI
          </span>
        </span>
      </motion.h1>

      {/* 3. Secondary Hero Heading */}
      <motion.h2
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.3 }}
        className="text-[32px] sm:text-[42px] lg:text-[50px] font-bold text-white leading-[1.15]"
      >
        <span className="block">Your Construction Project</span>
        <span className="block">Intelligence Chatbot</span>
      </motion.h2>

      {/* 4. Hero Description */}
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.4 }}
        className="text-[#B4C2D6] text-[16px] sm:text-[18px] lg:text-[19px] leading-[1.6] max-w-[620px]"
      >
        <span className="block sm:inline">Upload your project data, ask questions, and get instant, </span>
        <span className="block sm:inline">accurate insights — powered by AI.</span>
      </motion.p>

      {/* 5. Hero Buttons */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.5 }}
        className="pt-3 flex flex-wrap items-center gap-4 sm:gap-5"
      >
        {/* Primary CTA */}
        <button
          type="button"
          onClick={handleStartTrial}
          className="group relative inline-flex items-center justify-center w-[230px] sm:w-[240px] h-[56px] sm:h-[58px] rounded-full bg-gradient-to-r from-cyan-500 via-blue-600 to-indigo-600 text-white font-semibold text-[17px] shadow-[0_0_30px_rgba(6,182,212,0.4)] hover:shadow-[0_0_40px_rgba(6,182,212,0.6)] transition-all duration-300 hover:-translate-y-0.5 border border-cyan-300/40 cursor-pointer"
        >
          <span>Start Free Trial</span>
          <ArrowRight className="w-5 h-5 ml-2 transition-transform duration-300 group-hover:translate-x-1" />
        </button>

        {/* Secondary CTA */}
        <button
          type="button"
          onClick={onWatchDemo}
          className="group inline-flex items-center justify-center w-[190px] sm:w-[200px] h-[56px] sm:h-[58px] rounded-full bg-blue-950/20 hover:bg-blue-900/30 text-white font-semibold text-[16px] border border-blue-500/40 hover:border-cyan-400 transition-all duration-300 hover:-translate-y-0.5 backdrop-blur-md cursor-pointer"
        >
          <div className="w-8 h-8 rounded-full bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center mr-2.5 group-hover:scale-105 transition-transform">
            <Play className="w-4 h-4 text-cyan-300 fill-cyan-300/50 ml-0.5" />
          </div>
          <span>Watch Demo</span>
        </button>
      </motion.div>

    </motion.div>
  );
};
