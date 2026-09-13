import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ChevronRight, Menu, X } from 'lucide-react';
import { Button } from '../ui/Button';

export const Navbar = ({ activeTab, setActiveTab, onOpenGetStarted }) => {
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const handleScroll = () => {
      if (window.scrollY > 20) {
        setScrolled(true);
      } else {
        setScrolled(false);
      }
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const navItems = [
    { id: 'home', label: 'Home' },
    { id: 'features', label: 'Features' },
    { id: 'about', label: 'About' },
    { id: 'contact', label: 'Contact' }
  ];

  const handleNavClick = (id) => {
    setActiveTab(id);
    setMobileMenuOpen(false);
    
    if (id === 'home') {
      navigate('/');
    } else {
      navigate(`/${id}`);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <header
      className={`fixed block h-auto px-0 z-50 left-0 right-0 mx-auto navbar-fluid-transition bg-[#111827] ${
        scrolled
          ? 'top-2.5 sm:top-3 w-[calc(100%-1.5rem)] sm:w-[min(calc(100%-3rem),72rem)] max-w-6xl rounded-2xl py-2.5 sm:py-3 border border-cyan-500/20 shadow-[0_12px_30px_-8px_rgba(0,0,0,0.4),0_4px_12px_rgba(0,0,0,0.25)]'
          : 'top-0 w-full max-w-full rounded-none py-4 border border-b-slate-800/80 border-t-transparent border-x-transparent shadow-md'
      }`}
    >
      <div className={`w-full max-w-7xl mx-auto navbar-fluid-transition ${scrolled ? 'px-4 sm:px-6' : 'px-4 sm:px-6 lg:px-8'}`}>
        <div className="flex items-center justify-between">
          {/* Logo & Brand Name */}
          <div
            onClick={() => handleNavClick('home')}
            className="flex items-center gap-3 cursor-pointer group"
          >
            <div className="relative flex items-center justify-center w-11 h-11 rounded-xl bg-gradient-to-br from-blue-600 via-cyan-600 to-indigo-700 p-0.5 shadow-lg shadow-cyan-500/20 group-hover:shadow-cyan-500/40 transition-all duration-300">
              <div className="w-full h-full bg-[#040d21] rounded-[10px] flex items-center justify-center relative overflow-hidden">
                <img src="/prosight-logo-dark.png" alt="" className="w-full h-full object-contain rounded-[10px]" />
              </div>
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-xl font-extrabold tracking-tight text-white group-hover:text-cyan-300 transition-colors">
                  ProSight
                </span>
                <span className="px-1.5 py-0.5 text-xs font-bold rounded bg-cyan-500/20 text-cyan-400 border border-cyan-400/40">
                  AI
                </span>
              </div>
              <p className="text-[10px] font-medium tracking-widest text-slate-400 uppercase">
                Construction Project Intelligence
              </p>
            </div>
          </div>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center gap-1 bg-slate-900/60 p-1.5 rounded-full border border-slate-800/80 backdrop-blur-md">
            {navItems.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => handleNavClick(item.id)}
                  className={`relative px-4 py-2 text-sm font-medium rounded-full transition-all duration-300 cursor-pointer isolate ${
                    isActive
                      ? 'text-white'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
                  }`}
                >
                  {isActive && (
                    <span className="absolute inset-0 rounded-full bg-gradient-to-r from-blue-600/80 to-cyan-600/80 shadow-[0_0_15px_rgba(6,182,212,0.4)] -z-10" />
                  )}
                  {item.label}
                </button>
              );
            })}
          </nav>

          {/* Right Action Buttons */}
          <div className="hidden md:flex items-center gap-3">
            <Link to="/login">
              <Button
                variant="primary"
                size="md"
                icon={ChevronRight}
              >
                Log In
              </Button>
            </Link>
          </div>

          {/* Mobile Hamburger Toggle */}
          <div className="md:hidden flex items-center">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800 text-slate-300 hover:text-white hover:border-cyan-500/50"
              aria-label="Toggle menu"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className={`md:hidden fixed inset-x-3 sm:inset-x-6 ${scrolled ? 'top-[68px]' : 'top-[76px]'} bg-[#111827] border border-cyan-500/20 rounded-2xl p-6 shadow-2xl navbar-fluid-transition animate-in slide-in-from-top-5`}>
          <div className="flex flex-col gap-3">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => handleNavClick(item.id)}
                className={`text-left px-4 py-3 rounded-xl text-base font-semibold transition-all ${
                  activeTab === item.id
                    ? 'bg-gradient-to-r from-blue-600 to-cyan-600 text-white shadow-lg shadow-cyan-500/20'
                    : 'text-slate-300 hover:bg-slate-800/60 hover:text-cyan-400'
                }`}
              >
                {item.label}
              </button>
            ))}
            <div className="pt-4 border-t border-slate-800/80">
              <Link
                to="/login"
                onClick={() => setMobileMenuOpen(false)}
                className="block"
              >
                <Button
                  variant="primary"
                  size="lg"
                  className="w-full justify-center"
                  icon={ChevronRight}
                >
                  Log In
                </Button>
              </Link>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};
