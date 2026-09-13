import React from 'react';
import { HeroSection } from './HeroSection';

export const Hero = ({ onStartChat, onWatchDemo }) => {
  return <HeroSection onStartChat={onStartChat} onWatchDemo={onWatchDemo} />;
};
