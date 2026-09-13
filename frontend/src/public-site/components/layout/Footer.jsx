import React from 'react';
import { Link, useNavigate } from 'react-router-dom';

const LinkedInIcon = (props) => (
  <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"></path>
    <rect x="2" y="9" width="4" height="12"></rect>
    <circle cx="4" cy="4" r="2"></circle>
  </svg>
);

const TwitterIcon = (props) => (
  <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M22 4s-.7 2.1-2 3.4c1.6 10-9.4 17.3-18 11.6 2.2.1 4.4-.6 6-2C3 15.5.5 9.6 3 5c2.2 2.6 5.6 4.1 9 4-.9-4.2 4-6.6 7-3.8 1.1 0 3-1.2 3-1.2z"></path>
  </svg>
);

const YoutubeIcon = (props) => (
  <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M22.54 6.42a2.78 2.78 0 0 0-1.94-2C18.88 4 12 4 12 4s-6.88 0-8.6.46a2.78 2.78 0 0 0-1.94 2A29 29 0 0 0 1 11.75a29 29 0 0 0 .46 5.33A2.78 2.78 0 0 0 3.4 19c1.72.46 8.6.46 8.6.46s6.88 0 8.6-.46a2.78 2.78 0 0 0 1.94-2 29 29 0 0 0 .46-5.25 29 29 0 0 0-.46-5.33z"></path>
    <polygon points="9.75 15.02 15.5 11.75 9.75 8.48 9.75 15.02"></polygon>
  </svg>
);

export const Footer = ({ activeTab, setActiveTab }) => {
  const navigate = useNavigate();

  const handleNav = (id) => {
    if (id === 'how-it-works') {
      navigate('/#how-it-works');
      document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' });
      return;
    }
    setActiveTab(id);
    if (id === 'home') {
      navigate('/');
    } else {
      navigate(`/${id}`);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <footer className="relative bg-slate-100/90 border-t border-slate-200 pt-16 pb-12 overflow-hidden text-slate-600 text-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        
        <div className="grid grid-cols-1 md:grid-cols-12 gap-10 pb-12 border-b border-slate-200">
          
          {/* Brand & Logo */}
          <div className="md:col-span-8 space-y-4">
            <div className="flex items-center gap-3 cursor-pointer" onClick={() => handleNav('home')}>
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 via-cyan-600 to-indigo-700 p-0.5 shadow-md">
                <div className="w-full h-full bg-slate-900 rounded-[10px] flex items-center justify-center relative">
                  <img src="/prosight-logo-light.png" alt="" className="w-full h-full object-contain rounded-[10px]" />
                </div>
              </div>
              <div>
                <span className="text-xl font-bold text-slate-900 tracking-tight">ProSight <span className="text-cyan-600">AI</span></span>
                <p className="text-[10px] font-medium tracking-widest text-slate-500 uppercase">Construction Project Intelligence</p>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed max-w-sm">
              ProSight AI transforms blueprints, Primavera P6 schedules, submittals, and BOQs into evidence-backed project intelligence answers.
            </p>

            {/* Social Icons */}
            <div className="flex items-center gap-3 pt-2">
              {[
                { icon: LinkedInIcon, href: '#', label: 'LinkedIn' },
                { icon: TwitterIcon, href: '#', label: 'X (Twitter)' },
                { icon: YoutubeIcon, href: '#', label: 'YouTube' }
              ].map((social, idx) => {
                const Icon = social.icon;
                return (
                  <a
                    key={idx}
                    href={social.href}
                    aria-label={social.label}
                    className="w-9 h-9 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-slate-600 hover:text-cyan-600 hover:border-cyan-500/50 hover:bg-cyan-50 transition-all shadow-sm"
                  >
                    <Icon className="w-4 h-4" />
                  </a>
                );
              })}
            </div>
          </div>

          {/* Quick Navigation Links */}
          <div className="md:col-span-4 space-y-3">
            <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">Navigation</h4>
            <ul className="space-y-2 text-xs">
              {[
                { id: 'home', label: 'Home' },
                { id: 'features', label: 'Features & Agents' },
                { id: 'how-it-works', label: 'How It Works' },
                { id: 'about', label: 'About Us' },
                { id: 'contact', label: 'Contact Support' }
              ].map((link) => (
                <li key={link.id}>
                  <button
                    onClick={() => handleNav(link.id)}
                    className="hover:text-cyan-600 transition-colors text-slate-600 cursor-pointer"
                  >
                    {link.label}
                  </button>
                </li>
              ))}
              <li className="pt-1 border-t border-slate-200 flex items-center gap-3 text-xs">
                <Link to="/login" className="text-cyan-600 hover:text-cyan-700 font-semibold transition-colors">Log In</Link>
              </li>
            </ul>
          </div>

        </div>

        {/* Bottom Tagline & Copyright */}
        <div className="pt-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
          <p>© {new Date().getFullYear()} ProSight AI Inc. All rights reserved.</p>
          <p className="text-cyan-600 font-semibold tracking-wide">
            Smarter Projects. Stronger Tomorrow.
          </p>
        </div>

      </div>
    </footer>
  );
};
