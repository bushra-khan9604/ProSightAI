import React from 'react';

export const Card = ({
  children,
  className = '',
  hoverable = true,
  glow = false,
  glowColor = 'cyan',
  ...props
}) => {
  const glowClasses = {
    cyan: 'hover:shadow-[0_10px_30px_rgba(6,182,212,0.18)] hover:border-cyan-500/40',
    blue: 'hover:shadow-[0_10px_30px_rgba(37,99,235,0.18)] hover:border-blue-500/40',
    purple: 'hover:shadow-[0_10px_30px_rgba(139,92,246,0.18)] hover:border-purple-500/40',
    emerald: 'hover:shadow-[0_10px_30px_rgba(16,185,129,0.18)] hover:border-emerald-500/40'
  };

  return (
    <div
      className={`relative rounded-2xl bg-white/95 backdrop-blur-xl border border-slate-200/90 p-6 shadow-sm shadow-slate-200/50 transition-all duration-300 ${
        hoverable ? 'hover:-translate-y-1' : ''
      } ${glow ? glowClasses[glowColor] : ''} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};
