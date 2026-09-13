import React, { useState } from 'react';
import { SectionHeading } from '../components/ui/SectionHeading';
import { Mail, Phone, MapPin, Send, CheckCircle2, MessageSquare } from 'lucide-react';
import { Button } from '../components/ui/Button';

export const ContactPage = () => {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    projectType: 'Commercial High-Rise',
    message: ''
  });
  const [sent, setSent] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    setSent(true);
  };

  return (
    <div className="pt-32 pb-24 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-16">
      
      <SectionHeading
        eyebrow="GET IN TOUCH"
        title="Speak with a Construction"
        highlightText="AI Specialist"
        description="Have questions about custom BIM integrations, enterprise security, or deploying ProSight AI across your megaprojects?"
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">
        
        {/* Contact Info */}
        <div className="lg:col-span-5 space-y-8">
          <div className="p-8 rounded-3xl bg-white border border-slate-200 shadow-lg space-y-6">
            <h3 className="text-xl font-bold text-slate-900">Global Headquarters</h3>

            <div className="space-y-4 text-sm text-slate-600">
              <div className="flex items-start gap-3">
                <MapPin className="w-5 h-5 text-cyan-600 shrink-0 mt-0.5" />
                <span>100 Construction Tech Boulevard, Suite 1400, San Francisco, CA 94105</span>
              </div>
              <div className="flex items-center gap-3">
                <Mail className="w-5 h-5 text-cyan-600 shrink-0" />
                <span>enterprise@prosight.ai</span>
              </div>
              <div className="flex items-center gap-3">
                <Phone className="w-5 h-5 text-cyan-600 shrink-0" />
                <span>+1 (800) 555-PROSIGHT</span>
              </div>
            </div>
          </div>

          <div className="p-6 rounded-2xl bg-cyan-50 border border-cyan-200 text-xs text-slate-700 space-y-2">
            <h4 className="font-bold text-cyan-700 flex items-center gap-2">
              <MessageSquare className="w-4 h-4" />
              Need Immediate Technical Support?
            </h4>
            <p>Our dedicated AI integration team is available 24/7 for active enterprise contract clients.</p>
          </div>
        </div>

        {/* Contact Form */}
        <div className="lg:col-span-7">
          <div className="p-8 sm:p-10 rounded-3xl bg-white border border-slate-200 shadow-2xl">
            {sent ? (
              <div className="py-12 text-center space-y-4">
                <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-400/40 text-emerald-600 flex items-center justify-center mx-auto shadow-md">
                  <CheckCircle2 className="w-8 h-8" />
                </div>
                <h3 className="text-2xl font-bold text-slate-900">Inquiry Received!</h3>
                <p className="text-sm text-slate-600 max-w-sm mx-auto">
                  Thank you, <span className="text-cyan-600 font-semibold">{formData.name}</span>. A senior construction solution engineer will contact you within 2 business hours.
                </p>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-5">
                <h3 className="text-2xl font-bold text-slate-900 mb-2">Send Us a Message</h3>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Your Name</label>
                    <input
                      type="text"
                      required
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      placeholder="Alex Miller"
                      className="w-full px-4 py-3 rounded-xl bg-white border border-slate-300 text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:border-cyan-500 shadow-sm transition-colors"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Work Email</label>
                    <input
                      type="email"
                      required
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      placeholder="alex@skyscrape-dev.com"
                      className="w-full px-4 py-3 rounded-xl bg-white border border-slate-300 text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:border-cyan-500 shadow-sm transition-colors"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Project Portfolio Scope</label>
                  <select
                    value={formData.projectType}
                    onChange={(e) => setFormData({ ...formData, projectType: e.target.value })}
                    className="w-full px-4 py-3 rounded-xl bg-white border border-slate-300 text-slate-900 text-sm focus:outline-none focus:border-cyan-500 shadow-sm transition-colors"
                  >
                    <option>Commercial High-Rise</option>
                    <option>Infrastructure & Transport</option>
                    <option>Industrial Plant & Energy</option>
                    <option>Residential Multi-Family</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Message / Requirements</label>
                  <textarea
                    rows={4}
                    required
                    value={formData.message}
                    onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                    placeholder="Tell us about your active site schedules, document vault setup, or integration goals..."
                    className="w-full px-4 py-3 rounded-xl bg-white border border-slate-300 text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:border-cyan-500 shadow-sm transition-colors"
                  />
                </div>

                <Button
                  type="submit"
                  variant="glow"
                  size="lg"
                  className="w-full justify-center"
                  icon={Send}
                >
                  Send Inquiry
                </Button>
              </form>
            )}
          </div>
        </div>

      </div>

    </div>
  );
};
