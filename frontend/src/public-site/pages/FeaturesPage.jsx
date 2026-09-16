import React from 'react';
import { useNavigate } from 'react-router-dom';
import { SectionHeading } from '../components/ui/SectionHeading';
import { Card } from '../components/ui/Card';
import { ARCHITECTURE_NODES } from '../data/mockData';
import { FileText, FileSpreadsheet, ShieldCheck, Database, Search, Cpu, HardDrive, PenTool, CheckCircle2, ArrowRight } from 'lucide-react';
import { Button } from '../components/ui/Button';

const iconMap = {
  FileText,
  FileSpreadsheet,
  ShieldCheck,
  Database,
  Search,
  Cpu,
  HardDrive,
  PenTool
};

export const FeaturesPage = ({ onGetStarted }) => {
  const navigate = useNavigate();

  const handleLaunchTrial = () => {
    if (onGetStarted) onGetStarted();
    navigate('/contact');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  return (
    <div className="pt-32 pb-24 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-20">
      
      <SectionHeading
        eyebrow="ENTERPRISE PLATFORM CAPABILITIES"
        title="Purpose-Built AI for"
        highlightText="Construction Intelligence"
        description="Explore the multi-agent technology stack behind ProSight AI — designed specifically to resolve schedule delays, cost overruns, and documentation gridlock."
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {ARCHITECTURE_NODES.map((agent) => {
          const Icon = iconMap[agent.icon] || FileText;
          return (
            <Card key={agent.id} hoverable glow glowColor="cyan" className="p-8 space-y-4">
              <div className="w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-600">
                <Icon className="w-7 h-7" />
              </div>
              <h3 className="text-xl font-bold text-slate-900">{agent.title}</h3>
              <p className="text-sm font-semibold text-cyan-600">{agent.subtitle}</p>
              <p className="text-sm text-slate-600 leading-relaxed">{agent.description}</p>
              <ul className="space-y-2 pt-2 border-t border-slate-200 text-xs text-slate-500">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>Cross-links page numbers and exact document bounding boxes</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>Real-time vector synchronization with cloud document vaults</span>
                </li>
              </ul>
            </Card>
          );
        })}
      </div>

      <div className="p-10 rounded-3xl bg-white border border-slate-200 shadow-xl text-center space-y-4">
        <h3 className="text-2xl font-bold text-slate-900">Ready to test these capabilities on your active site data?</h3>
        <p className="text-sm text-slate-600 max-w-xl mx-auto">
          Start a risk-free trial and see how ProSight AI handles your Projects data.
        </p>
        <div className="pt-2">
          <Button variant="glow" size="lg" icon={ArrowRight} onClick={handleLaunchTrial}>
            Launch Free Workspace Trial
          </Button>
        </div>
      </div>

    </div>
  );
};
