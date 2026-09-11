import OpenAI from "npm:openai@4";
import { createClient } from "npm:@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
const publishableKey = Deno.env.get("SUPABASE_ANON_KEY")!;
const openai = new OpenAI({ apiKey: Deno.env.get("OPENAI_API_KEY")! });
const model = Deno.env.get("OPENAI_EMBEDDING_MODEL") ?? "text-embedding-3-small";

Deno.serve(async (request) => {
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const authorization = request.headers.get("authorization") ?? "";
  if (!authorization.toLowerCase().startsWith("bearer ")) {
    return Response.json({ error: "Authentication required" }, { status: 401 });
  }
  const { query, project_code, limit = 5 } = await request.json().catch(() => ({}));
  if (!String(query ?? "").trim() || !String(project_code ?? "").trim()) {
    return Response.json({ error: "query and project_code are required" }, { status: 400 });
  }

  const embeddingResult = await openai.embeddings.create({
    model,
    input: String(query).trim(),
    dimensions: 1536,
    encoding_format: "float",
  });
  const embedding = embeddingResult.data[0]?.embedding;
  if (!embedding || embedding.length !== 1536) {
    return Response.json({ error: "Embedding dimension mismatch" }, { status: 502 });
  }

  const userClient = createClient(supabaseUrl, publishableKey, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false },
  });
  const { data, error } = await userClient.rpc("hybrid_search", {
    query_text: String(query).trim(),
    query_embedding: embedding,
    match_project_code: String(project_code),
    match_count: Math.min(Math.max(Number(limit), 1), 20),
  });
  if (error) return Response.json({ error: error.message }, { status: 400 });
  return Response.json({ query, project_code, evidence: data ?? [] });
});
