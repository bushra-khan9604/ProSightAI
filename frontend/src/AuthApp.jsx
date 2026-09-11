import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { ArrowRight, BarChart3, Building2, LockKeyhole, Mail, Sparkles } from "lucide-react";
import { getMe } from "./api";
import { supabase } from "./supabase";

const App=lazy(()=>import("./App"));

function Landing({ session, recovery, onRecoveryComplete }) {
  const navigate=useNavigate();
  const [mode,setMode]=useState("login"),[email,setEmail]=useState(""),[password,setPassword]=useState("");
  const [displayName,setDisplayName]=useState(""),[loading,setLoading]=useState(false),[message,setMessage]=useState("");
  useEffect(()=>{if(recovery)setMode("update");else if(session)navigate("/app",{replace:true})},[session,recovery,navigate]);
  async function submit(event){
    event.preventDefault();setLoading(true);setMessage("");
    try{
      if(mode==="signup"){
        const {error}=await supabase.auth.signUp({email,password,options:{data:{display_name:displayName}}});
        if(error)throw error;setMessage("Account created. Opening your workspace…");
      }else if(mode==="reset"){
        const {error}=await supabase.auth.resetPasswordForEmail(email,{redirectTo:`${window.location.origin}/`});
        if(error)throw error;setMessage("Password reset instructions sent.");
      }else if(mode==="update"){
        const {error}=await supabase.auth.updateUser({password});
        if(error)throw error;
        await supabase.auth.signOut();
        onRecoveryComplete();setMode("login");setPassword("");
        setMessage("Password updated. Sign in with your new password.");
      }else{
        const {error}=await supabase.auth.signInWithPassword({email,password});if(error)throw error;
      }
    }catch(error){setMessage(error.message||"Authentication failed")}finally{setLoading(false)}
  }
  return <div className="landing-page">
    <header className="landing-header"><a className="landing-brand" href="/">
      <img src="/prosight-logo.svg" alt="ProSight AI"/><span><b>ProSight AI</b><small>Construction intelligence</small></span>
    </a><button onClick={()=>document.querySelector("#access")?.scrollIntoView({behavior:"smooth"})}>Sign in <ArrowRight size={16}/></button></header>
    <main className="landing-main">
      <section className="landing-copy"><span className="landing-eyebrow"><Sparkles size={15}/> Governed project intelligence</span>
        <h1>See project risk clearly. Act with evidence.</h1>
        <p>Bring schedules, resources, commercial data and project reports into one secure AI workspace built for construction delivery teams.</p>
        <div className="landing-features">
          <article><Building2/><b>Portfolio visibility</b><span>Active, completed and future work in one view.</span></article>
          <article><BarChart3/><b>Evidence-backed answers</b><span>Structured facts and cited project documents.</span></article>
          <article><LockKeyhole/><b>Protected access</b><span>Supabase authentication and project-level policies.</span></article>
        </div>
      </section>
      <section className="auth-card" id="access"><div className="auth-icon"><Mail size={21}/></div>
        <span>{mode==="signup"?"Create account":mode==="reset"||mode==="update"?"Recover access":"Welcome back"}</span>
        <h2>{mode==="signup"?"Start using ProSight":mode==="reset"?"Reset your password":mode==="update"?"Choose a new password":"Sign in to your workspace"}</h2>
        <p>{mode==="signup"?"New accounts receive employee access to the project portfolio.":mode==="reset"?"We’ll email a secure reset link.":mode==="update"?"Use at least eight characters for your new password.":"Use your work email and password."}</p>
        <form onSubmit={submit}>
          {mode==="signup"&&<label><span>Name</span><input value={displayName} onChange={e=>setDisplayName(e.target.value)} autoComplete="name" required/></label>}
          {mode!=="update"&&<label><span>Email</span><input type="email" value={email} onChange={e=>setEmail(e.target.value)} autoComplete="email" required/></label>}
          {mode!=="reset"&&<label><span>{mode==="update"?"New password":"Password"}</span><input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete={mode==="login"?"current-password":"new-password"} minLength="8" required/></label>}
          {message&&<div className="auth-message" role="status">{message}</div>}
          <button className="auth-submit" disabled={loading}>{loading?"Please wait…":mode==="signup"?"Create account":mode==="reset"?"Send reset link":mode==="update"?"Update password":"Sign in"}</button>
        </form>
        <div className="auth-links">
          {mode!=="login"&&mode!=="update"&&<button onClick={()=>{setMode("login");setMessage("")}}>Back to sign in</button>}
          {mode==="login"&&<><button onClick={()=>{setMode("signup");setMessage("")}}>Create an account</button><button onClick={()=>{setMode("reset");setMessage("")}}>Forgot password?</button></>}
        </div>
      </section>
    </main>
  </div>;
}

function ProtectedApp({session,profile,onSignOut}){
  if(!session)return <Navigate to="/" replace/>;
  if(!profile)return <div className="auth-loading"><i/><span>Loading your workspace…</span></div>;
  return <Suspense fallback={<div className="auth-loading"><i/><span>Opening your workspace…</span></div>}>
    <App profile={profile} onSignOut={onSignOut}/>
  </Suspense>;
}

export default function AuthApp(){
  const [session,setSession]=useState(null),[profile,setProfile]=useState(null),[ready,setReady]=useState(false),[recovery,setRecovery]=useState(false);
  useEffect(()=>{
    let active=true;
    supabase.auth.getSession().then(({data})=>{if(active){setSession(data.session);setReady(true)}});
    const {data:{subscription}}=supabase.auth.onAuthStateChange((event,next)=>{if(event==="PASSWORD_RECOVERY")setRecovery(true);setSession(next);if(!next)setProfile(null);setReady(true)});
    return()=>{active=false;subscription.unsubscribe()};
  },[]);
  useEffect(()=>{if(!session||recovery){setProfile(null);return}getMe().then(setProfile).catch(async()=>{setProfile(null);await supabase.auth.signOut()})},[session?.access_token,recovery]);
  async function signOut(){await supabase.auth.signOut();setProfile(null)}
  if(!ready)return <div className="auth-loading"><i/><span>Restoring your session…</span></div>;
  return <Routes>
    <Route path="/" element={<Landing session={session} recovery={recovery} onRecoveryComplete={()=>setRecovery(false)}/>}/>
    <Route path="/app/*" element={<ProtectedApp session={recovery?null:session} profile={profile} onSignOut={signOut}/>}/>
    <Route path="*" element={<Navigate to={session&&!recovery?"/app":"/"} replace/>}/>
  </Routes>;
}
