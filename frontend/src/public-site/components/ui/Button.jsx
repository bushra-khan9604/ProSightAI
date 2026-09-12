import React from 'react';
import { ArrowRight, Play } from 'lucide-react';

export const Button = ({
  children,
  variant = 'primary',
  size = 'md',
  icon: Icon,
  iconPosition = 'right',
  onClick,
  className = '',
  type = 'button',
  disabled = false,
  ...props
}) => {
  const baseStyles = 'relative inline-flex items-center justify-center font-medium transition-all duration-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-cyan-500/50 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer select-none';

  const variants = {
    primary: 'bg-gradient-to-r from-blue-600 via-cyan-600 to-blue-700 text-white shadow-md shadow-cyan-500/20 hover:shadow-cyan-500/35 hover:-translate-y-0.5 border border-cyan-400/30 hover:border-cyan-300/60',
    secondary: 'bg-white hover:bg-slate-50 text-slate-800 hover:text-cyan-700 border border-slate-300 hover:border-cyan-500/50 shadow-sm backdrop-blur-md hover:-translate-y-0.5',
    outline: 'bg-transparent text-slate-700 hover:text-slate-900 border border-slate-300 hover:border-cyan-500/50 hover:bg-cyan-50 hover:-translate-y-0.5',
    glow: 'bg-gradient-to-r from-cyan-500 via-blue-600 to-indigo-600 text-white shadow-[0_4px_20px_rgba(6,182,212,0.3)] hover:shadow-[0_6px_25px_rgba(6,182,212,0.45)] hover:-translate-y-1 border border-cyan-300/50',
    play: 'bg-white text-slate-900 border border-cyan-500/40 hover:border-cyan-500 hover:bg-cyan-50 shadow-md hover:-translate-y-0.5 group'
  };

  const sizes = {
    sm: 'px-4 py-2 text-xs gap-1.5',
    md: 'px-5 py-2.5 text-sm gap-2',
    lg: 'px-7 py-3.5 text-base font-semibold gap-2.5'
  };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {Icon && iconPosition === 'left' && <Icon className="w-4 h-4 transition-transform group-hover:-translate-x-0.5" />}
      <span>{children}</span>
      {Icon && iconPosition === 'right' && <Icon className="w-4 h-4 transition-transform group-hover:translate-x-1" />}
    </button>
  );
};
