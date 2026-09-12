import React from 'react';
import { X, Play, Sparkles, ShieldCheck } from 'lucide-react';
import { Button } from '../ui/Button';

export const DemoModal = ({ isOpen, onClose, onOpenGetStarted }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl rounded-3xl bg-white border border-slate-200 p-6 sm:p-8 shadow-2xl space-y-6">
        
        {/* Header Bar */}
        <div className="flex items-center justify-between border-b border-slate-200 pb-4">
          <div className="flex items-center gap-2 text-cyan-600 font-bold text-sm">
            <Sparkles className="w-4 h-4" />
            <span>ProSight AI — 3-Minute Product Tour</span>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-slate-100 border border-slate-200 text-slate-600 hover:text-slate-900 hover:border-slate-300"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Video Screen Container */}
        <div className="relative aspect-video rounded-2xl bg-slate-900 border border-slate-800 overflow-hidden flex flex-col items-center justify-center text-center p-6 group">
          
          {/* Animated Background Mesh */}
          <div className="absolute inset-0 bg-blueprint-grid opacity-30" />
          <div className="absolute inset-0 bg-gradient-to-tr from-blue-900/30 via-cyan-900/20 to-transparent" />

          {/* Interactive Play Center Button */}
          <div className="relative z-10 w-20 h-20 rounded-full bg-gradient-to-tr from-blue-600 to-cyan-500 p-1 shadow-[0_0_35px_rgba(6,182,212,0.6)] group-hover:scale-110 transition-transform cursor-pointer flex items-center justify-center">
            <div className="w-full h-full rounded-full bg-slate-950 flex items-center justify-center">
              <Play className="w-8 h-8 text-cyan-400 fill-cyan-400 ml-1" />
            </div>
          </div>

          <h3 className="relative z-10 text-xl font-bold text-white mt-6">
            Watch How ProSight AI Resolves Structural Delays in Real-Time
          </h3>
          <p className="relative z-10 text-xs text-slate-300 mt-2 max-w-md">
            Click play to see PDF blueprint ingestion, Primavera schedule cross-referencing, and automated RFI drafting in action.
          </p>

        </div>

        {/* Modal Bottom CTA */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-2">
          <div className="flex items-center gap-2 text-xs text-slate-600">
            <ShieldCheck className="w-4 h-4 text-cyan-600" />
            <span>No software download required. Runs securely in your browser.</span>
          </div>

          <Button
            variant="primary"
            size="md"
            onClick={() => {
              onClose();
              onOpenGetStarted();
            }}
          >
            Request Full Enterprise Demo
          </Button>
        </div>

      </div>
    </div>
  );
};
