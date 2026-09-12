import React, { useEffect } from 'react';
import { HeroSection } from '../components/hero/HeroSection';
import { ArchitectureFlow } from '../components/architecture/ArchitectureFlow';
import { LessManualWork } from '../components/features/LessManualWork';
import { WorkflowTimeline } from '../components/workflow/WorkflowTimeline';
import { DashboardPreview } from '../components/dashboard/DashboardPreview';
import { StatsCounters } from '../components/stats/StatsCounters';
import { CTASection } from '../components/cta/CTASection';

export const Home = ({ onStartChat, onWatchDemo, onGetStarted }) => {
  useEffect(() => {
    // Scroll to top immediately on page load
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, []);

  return (
    <div className="space-y-0">
      <HeroSection onStartChat={onStartChat} onWatchDemo={onWatchDemo} />
      <ArchitectureFlow />
      <LessManualWork onSeeHowItWorks={() => {
        const el = document.getElementById('how-it-works');
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      }} />
      <WorkflowTimeline />
      <DashboardPreview />
      <StatsCounters />
      <CTASection onGetStarted={onGetStarted} />
    </div>
  );
};
