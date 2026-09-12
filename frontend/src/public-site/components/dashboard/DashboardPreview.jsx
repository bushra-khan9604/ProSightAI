import React from 'react';
import { SectionHeading } from '../ui/SectionHeading';
import commandCenterImg from '../../assets/command-center-dashboard.png';

export const DashboardPreview = () => {
  return (
    <section 
      id="command-center" 
      className="relative py-24 sm:py-32 overflow-hidden bg-gradient-to-b from-[#070b14] via-[#0d1627] to-[#070b14] border-y border-slate-800/80 text-white"
    >
      {/* Background blueprint grid texture */}
      <div 
        className="absolute inset-0 pointer-events-none opacity-25"
        style={{
          backgroundImage: 'radial-gradient(rgba(56, 189, 248, 0.18) 1px, transparent 1px)',
          backgroundSize: '32px 32px'
        }}
      />

      {/* Atmospheric dark gradient glow orbs */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[850px] h-[500px] bg-gradient-to-r from-blue-600/20 via-cyan-500/20 to-teal-500/15 blur-[160px] rounded-full pointer-events-none" />
      <div className="absolute bottom-10 left-1/4 w-[500px] h-[350px] bg-indigo-600/15 blur-[140px] rounded-full pointer-events-none" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        
        {/* Section Heading with dark mode enabled */}
        <SectionHeading
          eyebrow="CONSTRUCTION COMMAND CENTER"
          title="Real-Time Project Intelligence"
          highlightText="Dashboard"
          description="Monitor schedule velocity, budget compliance, site risks, and submittal progress from a single unified AI cockpit."
          dark={true}
          className="max-w-5xl"
          titleClassName="whitespace-normal md:whitespace-nowrap"
        />

        {/* CENTER IMAGE SHOWCASE CONTAINER */}
        <div className="relative max-w-5xl mx-auto mt-10">
          
          {/* Ambient outer aura glow */}
          <div className="absolute -inset-1.5 bg-gradient-to-r from-cyan-500/35 via-blue-600/30 to-teal-400/30 rounded-3xl blur-2xl opacity-75 pointer-events-none" />

          {/* Browser / Dashboard Frame Mockup */}
          <div className="relative rounded-2xl sm:rounded-3xl bg-slate-900/90 border border-cyan-500/30 shadow-[0_25px_70px_-15px_rgba(0,0,0,0.9),0_0_50px_rgba(6,182,212,0.2)] overflow-hidden backdrop-blur-2xl">
            
            {/* Window Chrome Header */}
            <div className="flex items-center justify-between px-4 sm:px-6 py-3.5 bg-slate-950/80 border-b border-slate-800/90">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-rose-500/80 border border-rose-400/30" />
                <div className="w-3 h-3 rounded-full bg-amber-500/80 border border-amber-400/30" />
                <div className="w-3 h-3 rounded-full bg-emerald-500/80 border border-emerald-400/30" />
                <span className="hidden sm:inline-block ml-3 text-xs font-medium text-slate-400 font-mono">
                  ProSight AI • Project Controls • Creek Logistics Centre
                </span>
              </div>

              <div className="flex items-center gap-3">
                <span className="px-2.5 py-1 rounded-full bg-emerald-500/15 border border-emerald-400/30 text-emerald-300 text-[11px] font-semibold flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Live Sync
                </span>
                <span className="hidden md:inline-flex px-2.5 py-1 rounded-full bg-cyan-500/10 border border-cyan-400/30 text-cyan-300 text-[11px] font-medium">
                  PRJ-2022-009
                </span>
              </div>
            </div>

            {/* Center Image Canvas */}
            <div className="relative bg-slate-950/60 p-2 sm:p-4">
              <img 
                src={commandCenterImg} 
                alt="Construction Command Center - Project Explorer Dashboard" 
                className="w-full h-auto rounded-xl sm:rounded-2xl border border-slate-800/80 object-cover shadow-2xl block"
                loading="eager"
              />
            </div>
          </div>

        </div>

      </div>
    </section>
  );
};
