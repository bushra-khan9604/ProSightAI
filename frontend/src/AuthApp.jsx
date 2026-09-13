import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { getMe } from "./api";
import PublicSite from "./public-site/PublicSite";
import { supabase } from "./supabase";

const App = lazy(() => import("./App"));

function LoadingScreen({ children }) {
  return <div className="auth-loading"><i/><span>{children}</span></div>;
}

function ProtectedApp({ session, profile, onSignOut }) {
  if (!session) return <Navigate to="/login" replace/>;
  if (!profile) return <LoadingScreen>Loading your workspace…</LoadingScreen>;
  return <Suspense fallback={<LoadingScreen>Opening your workspace…</LoadingScreen>}>
    <App profile={profile} onSignOut={onSignOut}/>
  </Suspense>;
}

export default function AuthApp() {
  const [session, setSession] = useState(null);
  const [profile, setProfile] = useState(null);
  const [ready, setReady] = useState(false);
  const [recovery, setRecovery] = useState(false);

  useEffect(() => {
    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (active) {
        setSession(data.session);
        setReady(true);
      }
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, nextSession) => {
      if (event === "PASSWORD_RECOVERY") setRecovery(true);
      setSession(nextSession);
      if (!nextSession) setProfile(null);
      setReady(true);
    });
    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!session || recovery) {
      setProfile(null);
      return;
    }
    getMe().then(setProfile).catch(async () => {
      setProfile(null);
      await supabase.auth.signOut();
    });
  }, [session?.access_token, recovery]);

  async function signOut() {
    await supabase.auth.signOut();
    setProfile(null);
  }

  if (!ready) return <LoadingScreen>Restoring your session…</LoadingScreen>;

  return <Routes>
    <Route path="/app/*" element={<ProtectedApp session={recovery ? null : session} profile={profile} onSignOut={signOut}/>}/>
    <Route path="/*" element={<PublicSite session={session} recovery={recovery} onRecoveryComplete={() => setRecovery(false)}/>}/>
  </Routes>;
}
