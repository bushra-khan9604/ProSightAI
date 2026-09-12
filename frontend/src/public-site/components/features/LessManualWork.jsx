import React, { useEffect, useRef } from 'react';
import { ArrowRight, CheckCircle2, Sparkles } from 'lucide-react';
import { Button } from '../ui/Button';
import aiAssistantPreview from '../../assets/ai-assistant-preview.png';

export const LessManualWork = ({ onSeeHowItWorks }) => {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let animationFrameId;

    const resizeCanvas = () => {
      if (canvas.parentElement) {
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight;
      }
    };

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Create 45 glowing dots/particles floating floating upward in the background
    const particles = Array.from({ length: 45 }, () => ({
      x: Math.random() * (canvas.width || 1200),
      y: Math.random() * (canvas.height || 700),
      radius: Math.random() * 2 + 0.6,
      alpha: Math.random() * 0.6 + 0.25,
      vx: (Math.random() - 0.5) * 0.5,
      vy: -Math.random() * 0.5 - 0.2,
      color: Math.random() > 0.4 ? '#06b6d4' : Math.random() > 0.5 ? '#38bdf8' : '#818cf8'
    }));

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;

        if (p.y < 0) {
          p.y = canvas.height;
          p.x = Math.random() * canvas.width;
        }
        if (p.x < 0 || p.x > canvas.width) p.vx *= -1;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = p.alpha;
        ctx.shadowBlur = 10;
        ctx.shadowColor = p.color;
        ctx.fill();
      });

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <section className="relative py-24 sm:py-32 overflow-hidden bg-gradient-to-b from-[#030a1a] via-[#0b1c3d] to-[#020817] text-white">
      {/* Subtle radial cyan & blue gradient glow layers */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[850px] h-[550px] bg-gradient-to-r from-blue-600/20 via-cyan-500/20 to-indigo-600/20 blur-[170px] rounded-full pointer-events-none" />
      <div className="absolute inset-0 bg-radial-gradient opacity-80 pointer-events-none" />

      {/* Background blueprint grid & interactive floating dots canvas */}
      <div className="absolute inset-0 bg-blueprint-grid opacity-15 pointer-events-none" />
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none z-0" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-8 items-center">
          
          {/* Left Side Content */}
          <div className="lg:col-span-6 space-y-6 text-left">
            <div className="inline-flex items-center gap-2 px-3 py-1 text-xs font-semibold tracking-wider uppercase rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Sparkles className="w-3.5 h-3.5 text-cyan-300" />
              BUILT FOR CONSTRUCTION TEAMS
            </div>

            <h2 className="text-3xl sm:text-4xl md:text-5xl font-extrabold text-white leading-tight">
              Less Manual Work.{' '}
              <span className="gradient-text-cyan">More Real Insights.</span>
            </h2>

            <p className="text-left text-base sm:text-lg text-slate-300 leading-relaxed">
              No more searching through endless PDF submittals, Primavera schedules, or scattered Excel spreadsheets. ProSight AI understands your project data, answers your questions in natural language, and helps you stay on track — every single day.
            </p>

            <ul className="space-y-3 pt-2">
              {[
                'Instant cross-referencing across submittals, RFIs, and specs',
                'Automatic delay impact prediction on critical path tasks',
                'One-click executive briefing generation for project stakeholders'
              ].map((item, idx) => (
                <li key={idx} className="flex items-center gap-3 text-sm text-slate-300 font-medium">
                  <div className="w-5 h-5 rounded-full bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  </div>
                  <span>{item}</span>
                </li>
              ))}
            </ul>

            <div className="pt-4">
              <Button
                variant="glow"
                size="lg"
                icon={ArrowRight}
                onClick={onSeeHowItWorks}
              >
                SEE HOW IT WORKS
              </Button>
            </div>
          </div>

          {/* Right Side Visual: Uploaded AI Project Assistant Image with Soft Dual Inner/Outer Border Glow */}
          <div className="lg:col-span-6 relative group">
            {/* Soft cyan border halo orb */}
            <div className="absolute -inset-1 bg-gradient-to-r from-cyan-500/30 via-blue-600/25 to-cyan-400/30 rounded-3xl blur-md opacity-40 group-hover:opacity-60 transition duration-500 pointer-events-none" />

            <div className="relative rounded-3xl border border-cyan-400/35 bg-slate-900/90 backdrop-blur-2xl overflow-hidden shadow-[0_0_35px_rgba(6,182,212,0.22),_inset_0_0_20px_rgba(6,182,212,0.15)] p-2">
              <img
                src={aiAssistantPreview}
                alt="ProSight AI Project Assistant Interface"
                className="w-full h-auto rounded-2xl object-cover block"
              />
            </div>
          </div>

        </div>
      </div>
    </section>
  );
};
