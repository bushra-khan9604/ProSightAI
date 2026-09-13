import React, { useState, useEffect, useRef } from 'react';
import { METRICS_DATA } from '../../data/mockData';
import { Zap, ShieldCheck, TrendingUp, Award } from 'lucide-react';

const iconList = [Zap, ShieldCheck, TrendingUp, Award];

export const StatsCounters = () => {
  const [hasAnimated, setHasAnimated] = useState(false);
  const [counts, setCounts] = useState(METRICS_DATA.map(() => 0));
  const sectionRef = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !hasAnimated) {
          setHasAnimated(true);

          const duration = 2000;
          const steps = 50;
          const stepTime = duration / steps;

          let step = 0;
          const timer = setInterval(() => {
            step++;
            const progress = step / steps;

            setCounts(
              METRICS_DATA.map((item) => Math.floor(item.value * progress))
            );

            if (step >= steps) {
              clearInterval(timer);
              setCounts(METRICS_DATA.map((item) => item.value));
            }
          }, stepTime);
        }
      },
      { threshold: 0.25 }
    );

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => observer.disconnect();
  }, [hasAnimated]);

  return (
    <section ref={sectionRef} className="relative py-20 bg-slate-100/90 border-y border-slate-200 overflow-hidden">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
          {METRICS_DATA.map((metric, index) => {
            const Icon = iconList[index] || Zap;
            const currentVal = counts[index];

            return (
              <div
                key={index}
                className="relative p-6 sm:p-8 rounded-3xl bg-white border border-slate-200 hover:border-cyan-500/50 shadow-sm hover:shadow-md transition-all duration-300 group flex flex-col justify-between"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="w-12 h-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-600 group-hover:scale-110 transition-transform">
                    <Icon className="w-6 h-6" />
                  </div>
                  <span className="text-xs font-bold text-slate-500 uppercase tracking-widest">
                    Metric #{index + 1}
                  </span>
                </div>

                <div>
                  <div className="text-4xl sm:text-5xl font-extrabold tracking-tight mb-2 flex items-baseline">
                    <span className="gradient-text-cyan">{currentVal}</span>
                    <span className="text-cyan-600 text-3xl font-bold ml-1">{metric.suffix}</span>
                  </div>

                  <h4 className="text-lg font-bold text-slate-900 mb-2 group-hover:text-cyan-600 transition-colors">
                    {metric.label}
                  </h4>

                  <p className="text-xs text-slate-600 leading-relaxed">
                    {metric.subtext}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
