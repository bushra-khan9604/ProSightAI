import React from 'react';

export const SectionHeading = ({
  eyebrow,
  title,
  highlightText,
  description,
  align = 'center',
  className = '',
  titleClassName = '',
  dark = false
}) => {
  const alignmentClass = align === 'left' ? 'text-left' : align === 'right' ? 'text-right' : 'text-center mx-auto';
  const maxWidthClass = className.includes('max-w-') ? '' : 'max-w-3xl';

  return (
    <div className={`${maxWidthClass} mb-12 sm:mb-16 ${alignmentClass} ${className}`.trim()}>
      {eyebrow && (
        <div className={`inline-flex items-center gap-2 px-3.5 py-1.5 mb-4 text-xs font-semibold tracking-wider uppercase rounded-full border ${
          dark 
            ? 'bg-cyan-500/15 border-cyan-400/40 text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.2)]' 
            : 'bg-cyan-500/10 border-cyan-500/30 text-cyan-600'
        }`}>
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          {eyebrow}
        </div>
      )}
      
      {title && (
        <h2 className={`text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight mb-4 leading-tight ${
          dark ? 'text-white' : 'text-slate-900'
        } ${titleClassName}`.trim()}>
          {title}{' '}
          {highlightText && (
            <span className="gradient-text-cyan">{highlightText}</span>
          )}
        </h2>
      )}

      {description && (
        <p className={`text-center text-base sm:text-lg leading-relaxed max-w-2xl mx-auto ${
          dark ? 'text-slate-300' : 'text-slate-600'
        }`}>
          {description}
        </p>
      )}
    </div>
  );
};
