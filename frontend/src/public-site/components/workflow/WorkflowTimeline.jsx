import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CloudUpload, CheckCircle2, MessageSquareText, Lightbulb, ArrowRight, Sparkles } from 'lucide-react';
import { SectionHeading } from '../ui/SectionHeading';
import { WORKFLOW_STEPS } from '../../data/mockData';

const iconMap = {
  CloudUpload,
  CheckCircle2,
  MessageSquareText,
  Lightbulb
};

export const WorkflowTimeline = () => {
  const [hoveredStep, setHoveredStep] = useState(null);
  const navigate = useNavigate();

  const handleCardClick = () => {
    navigate('/how-it-works');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <section id="how-it-works" className="relative py-24 sm:py-32 overflow-hidden">
      {/* Background radial glow */}
      <div className="absolute top-1/2 right-1/4 w-[500px] h-[500px] bg-blue-600/10 blur-[150px] rounded-full pointer-events-none" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        
        {/* Section Heading */}
        <SectionHeading
          eyebrow="SIMPLE 4-STEP WORKFLOW"
          title="How It"
          highlightText="Works"
          description="From raw project data to actionable intelligent insights — in four seamless steps."
        />

        {/* TIMELINE CONTAINER */}
        <div className="relative mt-16">
          
          {/* Desktop Connected Illuminating Line */}
          <div className="hidden lg:block absolute top-1/2 left-[10%] right-[10%] -translate-y-12 h-1 bg-slate-200 rounded-full z-0 overflow-hidden">
            <div className="w-full h-full bg-gradient-to-r from-blue-600 via-cyan-400 to-teal-400 shadow-md animate-pulse" />
          </div>

          {/* Steps Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 relative z-10">
            {WORKFLOW_STEPS.map((item, index) => {
              const Icon = iconMap[item.icon] || CloudUpload;
              const isHovered = hoveredStep === index;

              return (
                <div
                  key={item.step}
                  onClick={handleCardClick}
                  onMouseEnter={() => setHoveredStep(index)}
                  onMouseLeave={() => setHoveredStep(null)}
                  className="relative group cursor-pointer"
                >
                  <div className={`p-6 sm:p-8 rounded-3xl bg-white border transition-all duration-300 h-full flex flex-col justify-between backdrop-blur-xl shadow-sm ${
                    isHovered
                      ? 'border-cyan-500 shadow-xl -translate-y-2 bg-white'
                      : 'border-slate-200/90 hover:border-cyan-500/40'
                  }`}>
                    
                    <div>
                      {/* Step Number Badge & Icon Row */}
                      <div className="flex items-center justify-between mb-6">
                        <div className={`w-12 h-12 rounded-2xl flex items-center justify-center font-extrabold text-lg transition-all duration-300 ${
                          isHovered
                            ? 'bg-gradient-to-br from-blue-600 to-cyan-500 text-white shadow-md shadow-cyan-500/30'
                            : 'bg-slate-100 text-cyan-600 border border-slate-200'
                        }`}>
                          {item.step}
                        </div>

                        <div className="p-2.5 rounded-xl bg-slate-100 border border-slate-200 text-cyan-600 group-hover:scale-110 transition-transform">
                          <Icon className="w-6 h-6" />
                        </div>
                      </div>

                      {/* Step Title */}
                      <h3 className="text-xl font-bold text-slate-900 mb-3 group-hover:text-cyan-600 transition-colors">
                        {item.title}
                      </h3>

                      {/* Description */}
                      <p className="text-sm text-slate-600 leading-relaxed">
                        {item.description}
                      </p>
                    </div>

                    {/* Step Footer Badge */}
                    <div className="mt-8 pt-4 border-t border-slate-200 flex items-center justify-between text-xs font-semibold text-cyan-600">
                      <span>{item.badge}</span>
                      <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                    </div>

                  </div>
                </div>
              );
            })}
          </div>

        </div>

      </div>
    </section>
  );
};
