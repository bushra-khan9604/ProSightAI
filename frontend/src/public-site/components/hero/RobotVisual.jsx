import React, { useState, useEffect } from 'react';
import { Sparkles, CheckCircle2, AlertTriangle, FileText, Activity, ShieldAlert, Cpu } from 'lucide-react';

export const RobotVisual = ({ onStartChat }) => {
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const handleMouseMove = (e) => {
      const { innerWidth, innerHeight } = window;
      const x = (e.clientX / innerWidth - 0.5) * 20;
      const y = (e.clientY / innerHeight - 0.5) * 20;
      setMousePos({ x, y });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  return (
    <div className="relative w-full max-w-[620px] aspect-square mx-auto flex items-center justify-center select-none">
      {/* Background Architectural Blueprint Grid & Wireframes */}
      <div 
        className="absolute inset-0 rounded-3xl border border-cyan-500/20 bg-gradient-to-b from-cyan-950/20 via-blue-950/10 to-transparent backdrop-blur-sm overflow-hidden"
        style={{
          transform: `translate3d(${mousePos.x * -0.5}px, ${mousePos.y * -0.5}px, 0)`
        }}
      >
        {/* Wireframe Building Graphic Lines */}
        <svg className="absolute inset-0 w-full h-full opacity-25" viewBox="0 0 500 500" fill="none">
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#06b6d4" strokeWidth="0.8" strokeDasharray="3 3" />
          </pattern>
          <rect width="100%" height="100%" fill="url(#grid)" />
          
          {/* Construction Skyscraper Wireframe */}
          <path d="M 120 480 L 120 180 L 220 120 L 320 180 L 320 480 Z" stroke="#38bdf8" strokeWidth="1.5" strokeDasharray="6 3" />
          <path d="M 170 480 L 170 200 L 270 200 L 270 480 Z" stroke="#06b6d4" strokeWidth="1" />
          <line x1="120" y1="240" x2="320" y2="240" stroke="#06b6d4" strokeWidth="1" strokeDasharray="4 2" />
          <line x1="120" y1="300" x2="320" y2="300" stroke="#06b6d4" strokeWidth="1" strokeDasharray="4 2" />
          <line x1="120" y1="360" x2="320" y2="360" stroke="#06b6d4" strokeWidth="1" strokeDasharray="4 2" />
          <line x1="120" y1="420" x2="320" y2="420" stroke="#06b6d4" strokeWidth="1" strokeDasharray="4 2" />

          {/* Crane Wireframe Silhouette */}
          <path d="M 360 480 L 360 140 L 460 80 M 360 160 L 480 160 M 360 140 L 310 160" stroke="#60a5fa" strokeWidth="2" />
          <line x1="430" y1="160" x2="430" y2="240" stroke="#22d3ee" strokeWidth="1.5" strokeDasharray="4 4" />
          <rect x="420" y="240" width="20" height="25" stroke="#38bdf8" strokeWidth="1.5" fill="none" />
        </svg>

        {/* Outer Pulsing Glowing Ring */}
        <div className="absolute inset-8 rounded-full border border-cyan-400/20 animate-pulse-glow" />
      </div>

      {/* CENTERPIECE: 3D-styled AI Construction Robot Assistant Illustration */}
      <div 
        className="relative z-10 w-72 h-72 sm:w-80 sm:h-80 transition-transform duration-300 ease-out"
        style={{
          transform: `translate3d(${mousePos.x * 0.8}px, ${mousePos.y * 0.8}px, 0)`
        }}
      >
        {/* Soft Cyan Visor Backlight */}
        <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-blue-600/40 via-cyan-500/30 to-indigo-500/20 blur-2xl animate-pulse" />

        {/* SVG Robot Assistant Head with Construction High-Vis Helmet */}
        <svg className="w-full h-full drop-shadow-[0_0_35px_rgba(6,182,212,0.5)]" viewBox="0 0 240 240" fill="none">
          <defs>
            <linearGradient id="helmetGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#0284c7" />
              <stop offset="50%" stopColor="#06b6d4" />
              <stop offset="100%" stopColor="#3b82f6" />
            </linearGradient>
            <linearGradient id="robotFaceGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#0b2142" />
              <stop offset="100%" stopColor="#040d21" />
            </linearGradient>
            <linearGradient id="visorGlow" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#22d3ee" />
              <stop offset="50%" stopColor="#60a5fa" />
              <stop offset="100%" stopColor="#38bdf8" />
            </linearGradient>
          </defs>

          {/* Robot Head Base Base */}
          <rect x="50" y="75" width="140" height="120" rx="36" fill="url(#robotFaceGrad)" stroke="#38bdf8" strokeWidth="3" />

          {/* CONSTRUCTION HELMET Top Shell */}
          <path d="M 35 90 C 35 45, 205 45, 205 90 Z" fill="url(#helmetGrad)" stroke="#7dd3fc" strokeWidth="3" />
          {/* Construction Helmet Rim / Brim */}
          <path d="M 25 90 C 25 84, 215 84, 215 90 L 205 100 L 35 100 Z" fill="#0284c7" stroke="#38bdf8" strokeWidth="2" />
          {/* Helmet Crest Ridge */}
          <path d="M 105 47 L 135 47 L 130 90 L 110 90 Z" fill="#38bdf8" opacity="0.8" />
          
          {/* Construction AI Emblem Badge on Helmet */}
          <circle cx="120" cy="72" r="11" fill="#040d21" stroke="#22d3ee" strokeWidth="2" />
          <path d="M 115 72 L 125 72 M 120 67 L 120 77" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" />

          {/* VISOR / EYE SCREEN */}
          <rect x="68" y="112" width="104" height="54" rx="20" fill="#020817" stroke="#06b6d4" strokeWidth="2.5" />

          {/* Friendly Animated Visor Eyes (Cyan Curved Arc Glowing Expression) */}
          <path d="M 86 136 Q 96 124 106 136" stroke="url(#visorGlow)" strokeWidth="4.5" strokeLinecap="round" fill="none" />
          <path d="M 134 136 Q 144 124 154 136" stroke="url(#visorGlow)" strokeWidth="4.5" strokeLinecap="round" fill="none" />

          {/* Glowing Smile Line */}
          <path d="M 104 152 Q 120 160 136 152" stroke="#22d3ee" strokeWidth="3" strokeLinecap="round" fill="none" />

          {/* Ear Sensor Antennas with Glowing Nodes */}
          <rect x="36" y="115" width="14" height="30" rx="6" fill="#0b2142" stroke="#38bdf8" strokeWidth="2" />
          <circle cx="43" cy="130" r="4" fill="#06b6d4" className="animate-ping" />
          <circle cx="43" cy="130" r="4" fill="#22d3ee" />

          <rect x="190" y="115" width="14" height="30" rx="6" fill="#0b2142" stroke="#38bdf8" strokeWidth="2" />
          <circle cx="197" cy="130" r="4" fill="#06b6d4" className="animate-ping" />
          <circle cx="197" cy="130" r="4" fill="#22d3ee" />

          {/* Chest Collar Joint / Status LED */}
          <rect x="85" y="195" width="70" height="15" rx="7" fill="#071a35" stroke="#38bdf8" strokeWidth="1.5" />
          <circle cx="102" cy="202.5" r="3" fill="#22c55e" />
          <circle cx="120" cy="202.5" r="3" fill="#3b82f6" />
          <circle cx="138" cy="202.5" r="3" fill="#06b6d4" />
        </svg>
      </div>

      {/* FLOATING CARD 1: Top Right Speech Bubble ("Ask anything about your project...") */}
      <div 
        onClick={onStartChat}
        className="absolute top-2 sm:top-6 -right-2 sm:-right-6 z-20 cursor-pointer animate-float"
        style={{
          transform: `translate3d(${mousePos.x * 1.2}px, ${mousePos.y * 1.2}px, 0)`
        }}
      >
        <div className="relative px-4 py-3 rounded-2xl bg-[#092247]/90 backdrop-blur-md border border-cyan-400/40 text-white shadow-[0_10px_30px_rgba(6,182,212,0.3)] hover:scale-105 transition-all">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-cyan-500/20 flex items-center justify-center text-cyan-400">
              <Sparkles className="w-4 h-4" />
            </div>
            <p className="text-xs sm:text-sm font-semibold tracking-wide text-slate-100">
              Ask anything about your project...
            </p>
          </div>
          {/* Speech bubble tail indicator */}
          <div className="absolute -bottom-2 left-6 w-4 h-4 bg-[#092247] border-r border-b border-cyan-400/40 transform rotate-45" />
        </div>
      </div>

      {/* FLOATING CARD 2: Bottom Right Status Speech Bubble ("Project progress is 68%. 3 critical tasks are delayed.") */}
      <div 
        className="absolute -bottom-4 sm:bottom-4 right-0 sm:right-4 z-20 animate-float-delayed"
        style={{
          transform: `translate3d(${mousePos.x * 0.9}px, ${mousePos.y * 0.9}px, 0)`
        }}
      >
        <div className="px-4 py-3 rounded-2xl bg-[#061836]/90 backdrop-blur-md border border-cyan-500/30 text-slate-200 shadow-xl max-w-[240px] sm:max-w-[280px]">
          <div className="flex items-start gap-2.5">
            <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 mt-1.5 animate-pulse" />
            <div>
              <p className="text-xs font-semibold text-white">
                Project progress is <span className="text-cyan-400 font-bold">68%</span>.
              </p>
              <p className="text-xs text-amber-300 font-medium mt-0.5 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3 text-amber-400" />
                3 critical tasks are delayed.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* FLOATING CARD 3: Left Top Badge ("Structural Work On Track") */}
      <div 
        className="absolute top-12 -left-4 sm:-left-8 z-20 animate-float"
        style={{
          transform: `translate3d(${mousePos.x * 1.5}px, ${mousePos.y * 1.5}px, 0)`
        }}
      >
        <div className="px-3.5 py-2 rounded-xl bg-slate-900/90 backdrop-blur-md border border-emerald-500/40 text-emerald-400 shadow-lg flex items-center gap-2 text-xs font-semibold">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>Structural Work On Track</span>
        </div>
      </div>

      {/* FLOATING CARD 4: Left Bottom Metric ("Documents Analyzed 248") */}
      <div 
        className="absolute bottom-16 -left-6 sm:-left-12 z-20 animate-float-delayed"
        style={{
          transform: `translate3d(${mousePos.x * 1.1}px, ${mousePos.y * 1.1}px, 0)`
        }}
      >
        <div className="px-4 py-2.5 rounded-xl bg-[#081e42]/90 backdrop-blur-md border border-blue-500/30 text-slate-200 shadow-lg flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center text-blue-400">
            <FileText className="w-4 h-4" />
          </div>
          <div>
            <p className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Documents Analyzed</p>
            <p className="text-sm font-bold text-white">248 Synced</p>
          </div>
        </div>
      </div>
    </div>
  );
};
