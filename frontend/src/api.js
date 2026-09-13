import { supabase } from "./supabase";

export async function createImportBatch(project_code,dataset) {
  return json(await apiFetch('/api/portfolio-import-batches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_code,dataset})}),'Could not create import batch');
}
export async function addImportBatchFile(id,file) {
  const body=new FormData();body.append('file',file);
  return json(await apiFetch(`/api/portfolio-import-batches/${id}/files`,{method:'POST',body}),'File validation failed');
}
export async function validateImportBatch(id) {
  return json(await apiFetch(`/api/portfolio-import-batches/${id}/validate`,{method:'POST'}),'Batch validation failed');
}
export async function submitImportBatch(id) {
  return json(await apiFetch(`/api/portfolio-import-batches/${id}/submit`,{method:'POST'}),'Could not submit batch');
}
export async function getControlsVersion(code,id) {
  return json(await apiFetch(`/api/projects/${code}/controls-versions/${id}`),'Could not load draft');
}
export async function getAgentRun(id) {
  return json(await apiFetch(`/api/agent-runs/${id}`),'Could not retrieve run');
}
export async function cancelAgentRun(id) {
  return json(await apiFetch(`/api/agent-runs/${id}/cancel`,{method:'POST'}),'Could not cancel run');
}
export async function editControlsVersion(code,id,tables) {
  return json(await apiFetch(`/api/projects/${code}/controls-versions/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({tables})}),'Draft validation failed');
}
export async function submitControlsVersion(code,id) {
  return json(await apiFetch(`/api/projects/${code}/controls-versions/${id}/submit`,{method:'POST'}),'Could not submit draft');
}
export async function downloadControlsVersion(code,id,format,runId=null) {
  const urlPath=runId?`/api/agent-runs/${runId}/exports/${format}`:`/api/projects/${code}/controls-versions/${id}/exports/${format}`;
  const artifact=await json(await apiFetch(urlPath,{method:'POST'}),'Could not prepare export');
  const response=await apiFetch(`/api/artifacts/${artifact.id}/download`);
  if(!response.ok)throw new Error('Artifact is unavailable or access has changed');
  const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');
  link.href=url;link.download=artifact.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

async function apiFetch(url, options = {}) {
  const { data: { session } } = await supabase.auth.getSession();
  const headers = new Headers(options.headers || {});
  if (session?.access_token) headers.set("Authorization", `Bearer ${session.access_token}`);
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) await supabase.auth.signOut();
  return response;
}

async function json(response, fallback) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail?.message || payload.detail || fallback);
  return payload;
}

export async function getMe() {
  return json(await apiFetch("/api/me"), "Could not load your profile");
}

export async function getProjects() {
  return json(await apiFetch("/api/projects"), "Could not load projects");
}

export async function askAgent(query, _userRole, projectCode = null, history = []) {
  const response = await apiFetch("/api/query", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, history, project_code: projectCode }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) { const error = new Error("The assistant could not answer"); error.requestId = payload.request_id; throw error; }
  return payload;
}

export async function askAgentStream(query, _userRole, projectCode = null, history = [], handlers = {}) {
  const response = await apiFetch("/api/query/stream", {
    method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ query, history, project_code: projectCode }),
  });
  if (!response.ok || !response.body) throw new Error("The assistant could not answer");
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer="",finalPayload=null,streamError=null;
  while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});
    const blocks=buffer.split(/\r?\n\r?\n/);buffer=blocks.pop()||"";
    for(const block of blocks){const type=block.match(/^event:\s*(.+)$/m)?.[1],raw=block.match(/^data:\s*(.+)$/m)?.[1];
      if(!type||!raw)continue;const payload=JSON.parse(raw);if(type==="status"){handlers.onStatus?.(payload.label||"Thinking");if(payload.run_id)handlers.onRun?.(payload.run_id)}
      if(type==="delta")handlers.onDelta?.(payload.text||"");
      if(type==="final")finalPayload=payload;if(type==="error")streamError=payload;}
    if(done)break;}
  if(streamError){const error=new Error(streamError.message||"The assistant could not answer");error.requestId=streamError.request_id;error.partial=Boolean(streamError.partial);throw error;}
  if(!finalPayload)throw new Error("The Assistant stream ended without a final response");return finalPayload;
}

export async function updateProject(projectCode, project) {
  return json(await apiFetch(`/api/projects/${encodeURIComponent(projectCode)}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(project),
  }), "Could not update project");
}

export async function uploadProjectFile(file, projectCode) {
  const body=new FormData();body.append("file",file);body.append("project_code",projectCode);
  return json(await apiFetch("/api/uploads",{method:"POST",body}),"Upload failed");
}

export async function getIngestionJob(jobId) { return json(await apiFetch(`/api/ingestion-jobs/${jobId}`),"Could not load ingestion status"); }
export async function getProjectIngestionJobs(projectCode) { return json(await apiFetch(`/api/projects/${encodeURIComponent(projectCode)}/ingestion-jobs`),"Could not load ingestion jobs"); }
export async function clearFailedIngestionJob(jobId) { return json(await apiFetch(`/api/ingestion-jobs/${encodeURIComponent(jobId)}`,{method:"DELETE"}),"Could not clear failed upload"); }

export async function uploadPortfolioWorkbook(file, _role, dataset="combined", projectCode="") {
  const body=new FormData();body.append("file",file);body.append("dataset",dataset);if(projectCode)body.append("project_code",projectCode);
  return json(await apiFetch("/api/portfolio-imports",{method:"POST",body}),"Portfolio import failed");
}

export async function downloadPortfolioTemplate(_role, dataset="combined") {
  const response=await apiFetch(`/api/portfolio-imports/template?dataset=${encodeURIComponent(dataset)}`);
  if(!response.ok)throw new Error("Could not download template");
  const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement("a");
  link.href=url;link.download=`ProSight-${dataset}-Import-Template.xlsx`;link.click();URL.revokeObjectURL(url);
}

export const portfolioTemplateUrl = () => "#";
export async function getProjectSchedule(_role, projectCode) { return json(await apiFetch(`/api/projects/${encodeURIComponent(projectCode)}/schedule`),"Could not load project schedule"); }
export async function getPortfolioManpower(_role, projectCode="") { const q=new URLSearchParams();if(projectCode)q.set("project_code",projectCode);return json(await apiFetch(`/api/portfolio/manpower?${q}`),"Could not load portfolio manpower"); }
export async function exportPortfolioManpower(employeeCodes,scenarioChanges=[]) {
  const response=await apiFetch("/api/portfolio/manpower/export",{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({employee_codes:employeeCodes,scenario_changes:scenarioChanges}),
  });
  if(!response.ok){const payload=await response.json().catch(()=>({}));throw new Error(payload.detail||"Could not export manpower")}
  const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement("a");
  link.href=url;link.download="ProSight-Manpower-Scenario.xlsx";link.click();URL.revokeObjectURL(url);
}
export async function getPortfolioInvoices(_role, projectCode="") { const q=new URLSearchParams();if(projectCode)q.set("project_code",projectCode);return json(await apiFetch(`/api/portfolio/invoices?${q}`),"Could not load project invoices"); }
export async function getInvoicePivot() { return json(await apiFetch("/api/portfolio/invoice-pivot"),"Could not load invoice pivot"); }
export async function getDocuments(projectCode) { return json(await apiFetch(`/api/projects/${encodeURIComponent(projectCode)}/documents`),"Could not load project documents"); }
export async function getChangeRequest(changeId) { return json(await apiFetch(`/api/change-requests/${changeId}`),"Could not load change preview"); }
export async function decideChange(changeId,decision) { return json(await apiFetch(`/api/change-requests/${changeId}/${decision}`,{method:"POST"}),"Could not decide change"); }
export async function getNotifications(_role,status="all") { return json(await apiFetch(`/api/notifications?status=${status}`),"Could not load notifications"); }
export async function markNotificationRead(notificationId) { return json(await apiFetch(`/api/notifications/${notificationId}/read`,{method:"POST"}),"Could not update notification"); }
export async function markAllNotificationsRead() { return json(await apiFetch("/api/notifications/read-all",{method:"POST"}),"Could not update notifications"); }
export async function getApprovals() { return json(await apiFetch("/api/approvals?status=pending"),"Could not load approval queue"); }
export async function deleteDocument(documentId) { return json(await apiFetch(`/api/documents/${documentId}`,{method:"DELETE"}),"Could not delete document"); }
export async function createProjectPreview(project) { return json(await apiFetch("/api/projects/change-preview",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(project)}),"Could not create project preview"); }
export async function createProjectImportPreview(file) { const body=new FormData();body.append("file",file);return json(await apiFetch("/api/projects/import-preview",{method:"POST",body}),"Could not preview workbook"); }
export async function updateProjectImport(changeId,project) { return json(await apiFetch(`/api/change-requests/${changeId}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(project)}),"Could not update import preview"); }
export async function confirmDocumentDate(jobId,reportingDate) { return json(await apiFetch(`/api/ingestion-jobs/${jobId}/confirm-date`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reporting_date:reportingDate})}),"Could not confirm report date"); }
