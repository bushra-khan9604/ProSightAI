import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { BlueprintGrid } from './components/background/BlueprintGrid';
import { Navbar } from './components/layout/Navbar';
import { Footer } from './components/layout/Footer';
import { Home } from './pages/Home';
import { FeaturesPage } from './pages/FeaturesPage';
import { AboutPage } from './pages/AboutPage';
import { ContactPage } from './pages/ContactPage';
import { LoginPage } from './pages/LoginPage';
import { DemoModal } from './components/modals/DemoModal';
import { GetStartedModal } from './components/modals/GetStartedModal';

function MainLayout({ initialTab = 'home' }) {
  const [activeTab, setActiveTab] = useState(initialTab);
  const [demoModalOpen, setDemoModalOpen] = useState(false);
  const [getStartedModalOpen, setGetStartedModalOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const path = location.pathname.replace(/^\//, '');
    if (['features', 'about', 'contact'].includes(path)) {
      setActiveTab(path);
    } else if (location.pathname === '/' || !path) {
      setActiveTab('home');
    }
  }, [location.pathname]);

  useEffect(() => {
    if (location.hash === '#how-it-works' && activeTab === 'home') {
      const frame = requestAnimationFrame(() => document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' }));
      return () => cancelAnimationFrame(frame);
    }
  }, [location.hash, activeTab]);

  const handleStartChat = () => {
    navigate('/login');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const renderActivePage = () => {
    switch (activeTab) {
      case 'features':
        return <FeaturesPage onGetStarted={() => { navigate('/signup'); window.scrollTo({ top: 0, behavior: 'smooth' }); }} />;
      case 'about':
        return <AboutPage />;
      case 'contact':
        return <ContactPage />;
      case 'home':
      default:
        return (
          <Home
            onStartChat={handleStartChat}
            onWatchDemo={() => setDemoModalOpen(true)}
            onGetStarted={() => { navigate('/signup'); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
          />
        );
    }
  };

  return (
    <div className="prosight-public-root relative min-h-screen bg-[#f8fafc] text-slate-900 flex flex-col font-sans selection:bg-cyan-500 selection:text-white">
      {/* Background Blueprint Grid & Floating Canvas Particles */}
      <BlueprintGrid showParticles={true} />

      {/* Main Sticky Navbar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenGetStarted={() => setGetStartedModalOpen(true)}
      />

      {/* Active Page View Content */}
      <main className="flex-grow z-10 p-0 m-0 max-w-none w-auto">
        {renderActivePage()}
      </main>

      {/* Footer */}
      <Footer activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Video Demo Modal */}
      <DemoModal
        isOpen={demoModalOpen}
        onClose={() => setDemoModalOpen(false)}
        onOpenGetStarted={() => setGetStartedModalOpen(true)}
      />

      {/* Get Started / Lead Capture Modal */}
      <GetStartedModal
        isOpen={getStartedModalOpen}
        onClose={() => setGetStartedModalOpen(false)}
      />
    </div>
  );
}

export default function PublicSite({ session, recovery, onRecoveryComplete }) {
  const location = useLocation();
  return (
    <Routes>
      <Route path="/login" element={session && !recovery ? <Navigate to="/app" replace /> : <LoginPage recovery={recovery} onRecoveryComplete={onRecoveryComplete} />} />
      <Route path="/signup" element={session && !recovery ? <Navigate to="/app" replace /> : <LoginPage initialMode="signup" recovery={recovery} onRecoveryComplete={onRecoveryComplete} />} />
      <Route path="/contact" element={<MainLayout initialTab="contact" />} />
      <Route path="/how-it-works" element={<Navigate to="/#how-it-works" replace />} />
      <Route path="/features" element={<MainLayout initialTab="features" />} />
      <Route path="/about" element={<MainLayout initialTab="about" />} />
      <Route path="/" element={session && !recovery && location.hash !== '#how-it-works' ? <Navigate to="/app" replace /> : recovery ? <Navigate to="/login" replace /> : <MainLayout initialTab="home" />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
