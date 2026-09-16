import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Sparkles, Mail, Lock, Eye, EyeOff, ArrowRight, CheckCircle2, ArrowLeft, User } from 'lucide-react';
import { BlueprintGrid } from '../components/background/BlueprintGrid';
import { Button } from '../components/ui/Button';
import { supabase } from '../../supabase';

const AUTH_COPY = {
  login: { eyebrow: 'Welcome Back', title: 'Log in to ProSight AI', description: 'Access your intelligent construction project memory & AI pipeline.', submit: 'Log In' },
  signup: { eyebrow: 'Create Account', title: 'Join ProSight AI', description: 'Create your secure construction intelligence workspace account.', submit: 'Create Account' },
  reset: { eyebrow: 'Recover Access', title: 'Reset your password', description: 'We will send a secure password reset link to your work email.', submit: 'Send Reset Link' },
  update: { eyebrow: 'Recover Access', title: 'Choose a new password', description: 'Enter a new password for your ProSight AI account.', submit: 'Update Password' },
};

export const LoginPage = ({ initialMode = 'login', recovery = false, onRecoveryComplete = () => {} }) => {
  const navigate = useNavigate();
  const [mode, setMode] = useState(recovery ? 'update' : initialMode);
  const [formData, setFormData] = useState({ displayName: '', emailOrUsername: '', password: '' });
  const [showPassword, setShowPassword] = useState(false);
  const [submitted, setSubmitted] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    setMode(recovery ? 'update' : initialMode);
    setSubmitted(null);
    setMessage('');
  }, [recovery, initialMode]);

  const changeMode = (nextMode) => {
    if (nextMode === 'login') navigate('/login', { replace: true });
    setMode(nextMode);
    setMessage('');
    setSubmitted(null);
    setShowPassword(false);
    setFormData((current) => ({ ...current, password: '' }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setMessage('');
    try {
      if (mode === 'signup') {
        const { data, error } = await supabase.auth.signUp({
          email: formData.emailOrUsername.trim(),
          password: formData.password,
          options: { data: { display_name: formData.displayName.trim() } },
        });
        if (error) throw error;
        setSubmitted({ title: 'Account Created!', detail: data.session ? 'Opening your workspace...' : 'Your account is ready. Sign in to continue.', redirects: Boolean(data.session) });
        if (data.session) window.setTimeout(() => navigate('/app', { replace: true }), 700);
      } else if (mode === 'reset') {
        const { error } = await supabase.auth.resetPasswordForEmail(formData.emailOrUsername.trim(), { redirectTo: `${window.location.origin}/login` });
        if (error) throw error;
        setSubmitted({ title: 'Check Your Inbox', detail: 'A secure password reset link has been sent.', redirects: false });
      } else if (mode === 'update') {
        const { error } = await supabase.auth.updateUser({ password: formData.password });
        if (error) throw error;
        await supabase.auth.signOut();
        onRecoveryComplete();
        setSubmitted({ title: 'Password Updated!', detail: 'You can now sign in with your new password.', redirects: false });
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email: formData.emailOrUsername.trim(), password: formData.password });
        if (error) throw error;
        setSubmitted({ title: 'Welcome Back!', detail: 'Redirecting to workspace...', redirects: true });
        window.setTimeout(() => navigate('/app', { replace: true }), 700);
      }
    } catch (error) {
      setMessage(error?.message || 'Authentication failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const copy = AUTH_COPY[mode];

  return (
    <div className="prosight-public-root min-h-screen text-white flex flex-col justify-between relative overflow-hidden font-sans selection:bg-cyan-500 selection:text-white py-6 px-4">
      <BlueprintGrid showParticles={true} dark={true} />

      <header className="relative h-auto bg-transparent border-0 px-0 z-10 max-w-7xl mx-auto w-full flex items-center justify-between py-2">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 via-cyan-600 to-indigo-700 p-0.5 shadow-md shadow-cyan-500/20 group-hover:shadow-cyan-500/40 transition-all duration-300">
            <div className="w-full h-full bg-[#040d21] rounded-[10px] flex items-center justify-center relative overflow-hidden">
              <img src="/prosight-logo-light.png" alt="" className="w-full h-full object-contain rounded-[10px]" />
            </div>
          </div>
          <div><div className="flex items-center gap-1.5">
            <span className="text-lg font-extrabold tracking-tight text-white group-hover:text-cyan-300 transition-colors">ProSight</span>
            <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-cyan-500/20 text-cyan-400 border border-cyan-400/40">AI</span>
          </div></div>
        </Link>

        <Link to="/" className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-slate-900/80 border border-slate-700/80 text-xs font-semibold text-slate-300 hover:text-white hover:border-cyan-400/60 shadow-md backdrop-blur-md transition-all cursor-pointer">
          <ArrowLeft className="w-3.5 h-3.5 text-cyan-400" /><span>Back to Home</span>
        </Link>
      </header>

      <main className="relative z-10 my-auto py-8 px-0 max-w-none w-auto">
        <div className="relative w-full max-w-md mx-auto">
          <div className="absolute -inset-1.5 bg-gradient-to-r from-cyan-400 via-blue-500 to-cyan-300 rounded-[28px] blur-md opacity-85 animate-pulse pointer-events-none" />
          <div className="relative rounded-3xl bg-white/95 border-2 border-cyan-400 shadow-[0_0_35px_rgba(6,182,212,0.4),0_25px_60px_-15px_rgba(0,0,0,0.7)] p-6 sm:p-8 backdrop-blur-2xl space-y-6 text-slate-900">
            <div className="space-y-2">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-700 text-xs font-semibold">
                <Sparkles className="w-3.5 h-3.5 text-cyan-600" /><span>{copy.eyebrow}</span>
              </div>
              <h1 className={`text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight pt-1${mode === 'login' || mode === 'signup' ? ' text-center' : ''}`}>{copy.title}</h1>
              <p className="text-xs sm:text-sm text-slate-500 text-center">{copy.description}</p>
            </div>

            {submitted ? (
              <div className="py-8 text-center space-y-4 animate-in zoom-in-95">
                <div className="w-14 h-14 rounded-full bg-emerald-500/15 border border-emerald-500/40 text-emerald-600 flex items-center justify-center mx-auto shadow-md"><CheckCircle2 className="w-7 h-7" /></div>
                <h3 className="text-xl font-bold text-slate-900">{submitted.title}</h3>
                <p className="text-xs text-slate-600 max-w-xs mx-auto">
                  {mode === 'login' && <>Authenticated as <span className="text-cyan-600 font-semibold">{formData.emailOrUsername}</span>. </>}
                  {submitted.detail}
                </p>
                {!submitted.redirects && <button type="button" onClick={() => changeMode('login')} className="text-xs font-semibold text-cyan-600 hover:text-cyan-700 hover:underline">Back to sign in</button>}
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4 pt-1">
                {mode === 'signup' && <AuthField icon={User} label="Name" type="text" autoComplete="name" value={formData.displayName} placeholder="Your name" onChange={(value) => setFormData({ ...formData, displayName: value })} />}
                {mode !== 'update' && <AuthField icon={Mail} label={mode === 'login' ? 'Email or Username' : 'Email'} type="email" autoComplete="email" value={formData.emailOrUsername} placeholder={mode === 'login' ? 'sarah@construct-corp.com or sarah_j' : 'you@company.com'} onChange={(value) => setFormData({ ...formData, emailOrUsername: value })} />}

                {mode !== 'reset' && <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="block text-xs font-semibold text-slate-700">{mode === 'update' ? 'New Password' : 'Password'}</label>
                    {mode === 'login' && <button type="button" onClick={() => changeMode('reset')} className="text-xs font-semibold text-cyan-600 hover:text-cyan-700 hover:underline transition-colors">Forgot password?</button>}
                  </div>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                    <input type={showPassword ? 'text' : 'password'} required minLength="8" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={formData.password} onChange={(event) => setFormData({ ...formData, password: event.target.value })} placeholder="••••••••••••" className="w-full pl-10 pr-10 py-2.5 rounded-xl bg-white border border-slate-300 text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 shadow-sm transition-colors" />
                    <button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Hide password' : 'Show password'} className="absolute right-3 top-3 text-slate-400 hover:text-cyan-600 transition-colors cursor-pointer">
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>}

                {message && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700">{message}</div>}

                <div className="pt-2"><Button type="submit" variant="glow" size="lg" disabled={loading} className="w-full justify-center text-sm py-3 font-semibold shadow-lg shadow-cyan-500/30" icon={ArrowRight}>{loading ? 'Please wait...' : copy.submit}</Button></div>

                <div className="flex items-center justify-center gap-2 text-xs text-slate-500">
                  {mode === 'login' ? <><span>New to ProSight AI?</span><Link to="/signup" className="font-semibold text-cyan-600 hover:text-cyan-700 hover:underline">Create an account</Link></> : mode !== 'update' ? <button type="button" onClick={() => changeMode('login')} className="font-semibold text-cyan-600 hover:text-cyan-700 hover:underline">Back to sign in</button> : null}
                </div>
              </form>
            )}
          </div>
        </div>
      </main>

      <footer className="relative z-10 text-center text-xs text-slate-400 py-2"><p>© {new Date().getFullYear()} ProSight AI Inc.</p></footer>
    </div>
  );
};

function AuthField({ icon: Icon, label, ...props }) {
  const { onChange, ...inputProps } = props;
  return <div>
    <label className="block text-xs font-semibold text-slate-700 mb-1.5">{label}</label>
    <div className="relative">
      <Icon className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
      <input required {...inputProps} onChange={(event) => onChange(event.target.value)} className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-white border border-slate-300 text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 shadow-sm transition-colors" />
    </div>
  </div>;
}
