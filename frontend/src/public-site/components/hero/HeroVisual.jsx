import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { MessageCircle, AlertCircle, FileText, CheckCircle2 } from 'lucide-react';
import { StatCard, useAnimatedCounter } from './StatCard';
import { ProgressRing } from './ProgressRing';

export const HeroVisual = ({ onStartChat }) => {
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [statusPulse, setStatusPulse] = useState(false);

  // Animated Counters
  const progressVal = useAnimatedCounter(68, 1400, 700);
  const tasksVal = useAnimatedCounter(3, 1000, 1150);
  const docsVal = useAnimatedCounter(248, 1600, 1300);

  // Mouse Parallax Response
  useEffect(() => {
    const handleMouseMove = (e) => {
      const { innerWidth, innerHeight } = window;
      const x = (e.clientX / innerWidth - 0.5) * 10;
      const y = (e.clientY / innerHeight - 0.5) * 10;
      setMousePos({ x, y });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  // Status pulse trigger after load
  useEffect(() => {
    const timer = setTimeout(() => setStatusPulse(true), 1400);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="relative w-full max-w-[720px] aspect-[4/3.8] lg:aspect-[4/3.6] mx-auto flex items-center justify-center select-none">
      
      {/* Radial Background Glow behind building area */}
      <div className="absolute inset-0 bg-radial-glow opacity-80 pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[550px] h-[550px] bg-gradient-to-r from-cyan-500/15 via-blue-600/15 to-indigo-600/10 blur-[130px] rounded-full pointer-events-none" />

      {/* SVG Architectural Blueprint & Orbit Ring Overlay */}
      <svg className="absolute inset-0 w-full h-full opacity-40 pointer-events-none" viewBox="0 0 700 600" fill="none">
        {/* LOWER BUILDING DATA ORBIT RING */}
        <ellipse cx="400" cy="450" rx="230" ry="65" stroke="url(#orbitGradient)" strokeWidth="1.5" strokeDasharray="8 6" fill="none" opacity="0.8" />
        <defs>
          <linearGradient id="orbitGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#06b6d4" />
            <stop offset="50%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>

        {/* SUBTLE CONNECTION LINES TO STAT CARDS */}
        <path d="M 210 130 L 340 180" stroke="#06b6d4" strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />
        <path d="M 210 320 L 330 320" stroke="#06b6d4" strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />
        <path d="M 540 230 L 450 230" stroke="#06b6d4" strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />
        <path d="M 540 400 L 470 400" stroke="#06b6d4" strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />

        {/* Endpoint glowing dots */}
        <circle cx="340" cy="180" r="3.5" fill="#22d3ee" className="animate-ping" />
        <circle cx="340" cy="180" r="3.5" fill="#22d3ee" />
        <circle cx="330" cy="320" r="3.5" fill="#22d3ee" />
        <circle cx="450" cy="230" r="3.5" fill="#22d3ee" />
        <circle cx="470" cy="400" r="3.5" fill="#22d3ee" />
      </svg>

      {/* ================================================== */}
      {/* 5 FLOATING STAT CARDS OVERLAY                      */}
      {/* ================================================== */}

      {/* CARD 1: Upper-Left of building -> Project Progress (68%) */}
      <div 
        className="absolute top-[8%] left-[2%] sm:left-[4%] z-20"
        style={{ transform: `translate3d(${mousePos.x * 0.7}px, ${mousePos.y * 0.7}px, 0)` }}
      >
        <StatCard delay={0.7} floatDuration={7} floatDistance={4} hasArrow={false}>
          <ProgressRing progress={68} size={42} strokeWidth={4} />
          <div>
            <p className="text-[12px] sm:text-[13px] font-semibold text-slate-300">Project Progress</p>
            <p className="text-[20px] sm:text-[22px] font-bold text-white leading-tight">
              {progressVal}%
            </p>
          </div>
        </StatCard>
      </div>

      {/* CARD 2: Middle-Left of building -> Structural Work (On Track >) */}
      <div 
        className="absolute top-[48%] left-[0%] sm:left-[2%] z-20"
        style={{ transform: `translate3d(${mousePos.x * 0.6}px, ${mousePos.y * 0.6}px, 0)` }}
      >
        <StatCard delay={0.85} floatDuration={8} floatDistance={5} hasArrow={true}>
          <div className={`w-9 h-9 rounded-full bg-emerald-500/20 border border-emerald-400/40 flex items-center justify-center text-emerald-400 shrink-0 ${statusPulse ? 'animate-pulse' : ''}`}>
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div>
            <p className="text-[12px] sm:text-[13px] font-semibold text-slate-300">Structural Work</p>
            <p className="text-[14px] sm:text-[16px] font-bold text-emerald-400 leading-tight">
              On Track
            </p>
          </div>
        </StatCard>
      </div>

      {/* CARD 3: Upper-Right of building -> Ask anything about your project... */}
      <div 
        className="absolute top-[5%] right-[2%] sm:right-[5%] z-20 cursor-pointer"
        style={{ transform: `translate3d(${mousePos.x * 0.8}px, ${mousePos.y * 0.8}px, 0)` }}
        onClick={onStartChat}
      >
        <StatCard delay={1.0} floatDuration={6.5} floatDistance={4} hasArrow={false} className="max-w-[210px] sm:max-w-[230px]">
          <div className="w-9 h-9 rounded-xl bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center text-cyan-400 shrink-0">
            <MessageCircle className="w-5 h-5" />
          </div>
          <div>
            <p className="text-[13px] sm:text-[14px] font-semibold text-slate-100 leading-snug">
              Ask anything about your project...
            </p>
          </div>
        </StatCard>
      </div>

      {/* CARD 4: Middle-Right of building -> 3 Critical Tasks (Delayed >) */}
      <div 
        className="absolute top-[38%] right-[0%] sm:right-[2%] z-20"
        style={{ transform: `translate3d(${mousePos.x * 0.75}px, ${mousePos.y * 0.75}px, 0)` }}
      >
        <StatCard delay={1.15} floatDuration={7.5} floatDistance={5} hasArrow={true}>
          <div className="w-9 h-9 rounded-full bg-rose-500/20 border border-rose-400/40 flex items-center justify-center text-rose-400 shrink-0">
            <AlertCircle className="w-5 h-5" />
          </div>
          <div>
            <p className="text-[12px] sm:text-[13px] font-semibold text-slate-300">
              {tasksVal} Critical Tasks
            </p>
            <p className="text-[14px] sm:text-[16px] font-bold text-rose-400 leading-tight">
              Delayed
            </p>
          </div>
        </StatCard>
      </div>

      {/* CARD 5: Lower-Right of building -> Documents Analyzed (248 >) */}
      <div 
        className="absolute bottom-[10%] right-[3%] sm:right-[6%] z-20"
        style={{ transform: `translate3d(${mousePos.x * 0.65}px, ${mousePos.y * 0.65}px, 0)` }}
      >
        <StatCard delay={1.3} floatDuration={8.5} floatDistance={4} hasArrow={true}>
          <div className="w-9 h-9 rounded-xl bg-blue-500/20 border border-blue-400/40 flex items-center justify-center text-cyan-400 shrink-0">
            <FileText className="w-5 h-5" />
          </div>
          <div>
            <p className="text-[12px] sm:text-[13px] font-semibold text-slate-300">Documents Analyzed</p>
            <p className="text-[18px] sm:text-[20px] font-bold text-white leading-tight">
              {docsVal}
            </p>
          </div>
        </StatCard>
      </div>

    </div>
  );
};
