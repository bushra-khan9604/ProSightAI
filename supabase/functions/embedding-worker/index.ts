import OpenAI from "npm:openai@4";
import { createClient } from "npm:@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const openaiKey = Deno.env.get("OPENAI_API_KEY")!;
const workerSecret = Deno.env.get("EMBEDDING_WORKER_SECRET") ?? "";
const model = Deno.env.get("OPENAI_EMBEDDING_MODEL") ?? "text-embedding-3-small";
const supabase = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } });
const openai = new OpenAI({ apiKey: openaiKey });

type QueueMessage = {
  msg_id: number;
  message: { chunk_id: string; content_hash: string; embedding_model?: string };
};

Deno.serve(async (request) => {
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
  if (!workerSecret) return new Response("Worker secret is not configured", { status: 503 });
  if (request.headers.get("x-worker-secret") !== workerSecret) {
    return new Response("Unauthorized", { status: 401 });
  }

  const requested = Number((await request.json().catch(() => ({}))).batch_size ?? 16);
  const batchSize = Math.min(Math.max(requested, 1), 64);
  const { data: jobs, error: queueError } = await supabase.rpc("dequeue_embedding_jobs", {
    batch_size: batchSize,
  });
  if (queueError) return Response.json({ error: queueError.message }, { status: 500 });

  const completed: string[] = [];
  const failed: Array<{ chunk_id: string; error: string }> = [];
  for (const job of (jobs ?? []) as QueueMessage[]) {
    const chunkId = job.message.chunk_id;
    try {
      const { data: chunk, error: chunkError } = await supabase
        .from("document_chunks")
        .select("id,content,content_hash,embedding_attempts")
        .eq("id", chunkId)
        .maybeSingle();
      if (chunkError) throw chunkError;
      if (!chunk || chunk.content_hash !== job.message.content_hash) {
        await supabase.rpc("complete_embedding_job", { job_msg_id: job.msg_id });
        continue;
      }

      await supabase.from("document_chunks").update({
        embedding_status: "processing",
        embedding_attempts: Number(chunk.embedding_attempts ?? 0) + 1,
        embedding_error: null,
      }).eq("id", chunkId);
      const response = await openai.embeddings.create({
        model: job.message.embedding_model ?? model,
        input: chunk.content,
        dimensions: 1536,
        encoding_format: "float",
      });
      const embedding = response.data[0]?.embedding;
      if (!embedding || embedding.length !== 1536) throw new Error("Embedding dimension mismatch");
      const { error: updateError } = await supabase.from("document_chunks").update({
        embedding,
        embedding_status: "ready",
        embedding_error: null,
        updated_at: new Date().toISOString(),
      }).eq("id", chunkId).eq("content_hash", job.message.content_hash);
      if (updateError) throw updateError;
      await supabase.rpc("complete_embedding_job", { job_msg_id: job.msg_id });
      completed.push(chunkId);
    } catch (error) {
      const message = error instanceof Error ? error.message.slice(0, 500) : "Embedding failed";
      const { data: current } = await supabase.from("document_chunks")
        .select("content_hash,embedding_attempts").eq("id", chunkId).maybeSingle();
      if (!current || current.content_hash !== job.message.content_hash) {
        await supabase.rpc("complete_embedding_job", { job_msg_id: job.msg_id });
        continue;
      }
      const attempts = Number(current?.embedding_attempts ?? 1);
      const terminal = attempts >= 5;
      await supabase.from("document_chunks").update({
        embedding_status: terminal ? "failed" : "pending",
        embedding_error: message,
        updated_at: new Date().toISOString(),
      }).eq("id", chunkId).eq("content_hash", job.message.content_hash);
      if (terminal) await supabase.rpc("complete_embedding_job", { job_msg_id: job.msg_id });
      else await supabase.rpc("retry_embedding_job", {
        job_msg_id: job.msg_id,
        job_message: job.message,
        delay_seconds: Math.min(30 * 2 ** attempts, 900),
      });
      failed.push({ chunk_id: chunkId, error: message });
    }
  }
  return Response.json({ processed: completed.length + failed.length, completed, failed });
});
