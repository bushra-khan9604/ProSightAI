import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Sparkles } from 'lucide-react';
import { Button } from '../ui/Button';

export const CTASection = ({ onGetStarted }) => {
  const navigate = useNavigate();

  const handleGetStarted = (e) => {
    if (onGetStarted) onGetStarted(e);
    navigate('/login');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  return (
    <section className="relative py-16 sm:py-24 overflow-hidden bg-[#020817] text-white">
      {/* Blueprint Grid & Radial Glow Background */}
      <div className="absolute inset-0 bg-blueprint-grid opacity-15 pointer-events-none" />
      <div className="absolute inset-0 bg-radial-gradient opacity-90 pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[400px] bg-gradient-to-r from-blue-600/20 via-cyan-500/20 to-indigo-600/20 blur-[160px] rounded-full pointer-events-none" />

      {/* Wireframe Crane Skyline SVG Backdrop */}
      <svg className="absolute bottom-0 inset-x-0 w-full h-36 opacity-20 pointer-events-none" viewBox="0 0 1200 200" fill="none">
        <path d="M 100 200 L 100 80 L 200 30 L 300 80 L 300 200" stroke="#06b6d4" strokeWidth="2" strokeDasharray="6 3" />
        <path d="M 400 200 L 400 50 L 550 50 L 550 200" stroke="#38bdf8" strokeWidth="2" />
        <path d="M 700 200 L 700 70 L 800 20 L 900 70 L 900 200" stroke="#60a5fa" strokeWidth="2" strokeDasharray="4 2" />
        <line x1="550" y1="50" x2="680" y2="20" stroke="#22d3ee" strokeWidth="3" />
        <line x1="650" y1="20" x2="650" y2="120" stroke="#06b6d4" strokeWidth="2" strokeDasharray="4 4" />
      </svg>

      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10 text-center">
        
        <div className="p-6 sm:p-10 rounded-3xl bg-slate-900/80 border border-cyan-500/30 backdrop-blur-2xl shadow-[0_0_60px_rgba(6,182,212,0.25)] space-y-4">
          
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-cyan-500/10 border border-cyan-400/30 text-cyan-400 text-xs font-semibold tracking-wider uppercase shadow-md">
            <Sparkles className="w-3.5 h-3.5 text-cyan-300" />
            <span>TRANSFORM YOUR SITE DATA</span>
          </div>

          <h2 className="text-2xl sm:text-3xl md:text-4xl font-extrabold text-white tracking-tight leading-snug">
            Experience the Future of{' '}
            <span className="gradient-text-cyan">Construction Intelligence</span>
          </h2>

          <p className="text-sm sm:text-base text-slate-300 max-w-xl mx-auto leading-relaxed">
            Upload your project documents and start getting instant, evidence-backed insights in minutes.
          </p>

          <div className="pt-2 flex flex-wrap items-center justify-center gap-4">
            <Button
              variant="glow"
              size="md"
              icon={ArrowRight}
              onClick={handleGetStarted}
              className="text-sm sm:text-base px-7 py-3 font-semibold"
            >
              Get Started Now
            </Button>
          </div>

        </div>

      </div>
    </section>
  );
};
