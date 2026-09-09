import { createClient } from "@supabase/supabase-js";

let clientPromise;
export function authChanged() { window.dispatchEvent(new Event("prosight:auth-changed")); }
export function getAuthClient() {
  if (!clientPromise) clientPromise = (async () => {
    const response = await window.fetch("/api/auth/config");
    if (!response.ok) throw new Error("Could not load sign-in configuration. Please retry.");
    const config = await response.json();
    if (config.provider !== "supabase") return null;
    if (!config.url || !config.publishableKey) throw new Error("Supabase sign-in is not configured.");
    const client = createClient(config.url, config.publishableKey);
    client.auth.onAuthStateChange(() => { setTimeout(authChanged, 0); });
    return client;
  })().catch(error => { clientPromise = undefined; throw error; });
  return clientPromise;
}

export async function authenticatedFetch(url, options = {}) {
  const client = await getAuthClient();
  const headers = new Headers(options.headers);
  if (client) {
    const { data, error } = await client.auth.getSession();
    if (error) throw error;
    if (data.session) headers.set("Authorization", `Bearer ${data.session.access_token}`);
  }
  const response = await window.fetch(url, { ...options, headers, credentials: "same-origin" });
  if (response.status === 401 && !String(url).startsWith("/api/auth/")) authChanged();
  return response;
}

export async function downloadTemplate(url) {
  const response = await authenticatedFetch(url);
  if (!response.ok) throw new Error("Could not download template. Check your session and try again.");
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = "prosight-portfolio-template.xlsx";
  link.click();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
