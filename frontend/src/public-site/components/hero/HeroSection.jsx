import React, { useEffect } from 'react';
import { HeroContent } from './HeroContent';
import { HeroVisual } from './HeroVisual';
import heroBg from '../../assets/hero-bg.png';

export const HeroSection = ({ onStartChat, onWatchDemo }) => {
  // Ensure the page loads starting right from the top of the hero section
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <section 
      id="hero"
      className="relative pt-[100px] sm:pt-[110px] pb-16 lg:pb-24 min-h-[calc(100vh-84px)] flex items-center justify-center overflow-hidden bg-no-repeat bg-cover bg-right lg:bg-center"
      style={{
        backgroundImage: `url(${heroBg})`,
        backgroundColor: '#020817'
      }}
    >

      {/* Blueprint Grid Accent Lines */}
      <div className="absolute inset-0 bg-blueprint-grid opacity-15 pointer-events-none" />

      <div className="w-full max-w-[1640px] mx-auto px-6 lg:px-12 relative z-10">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-8 items-center">
          
          {/* LEFT SIDE: Typography + CTA Buttons */}
          <div className="lg:col-span-6 flex justify-start">
            <HeroContent onStartChat={onStartChat} onWatchDemo={onWatchDemo} />
          </div>

          {/* RIGHT SIDE: 5 Floating Stat Cards positioned around background building */}
          <div className="lg:col-span-6 flex justify-center lg:justify-end">
            <HeroVisual onStartChat={onStartChat} />
          </div>

        </div>
      </div>

    </section>
  );
};
