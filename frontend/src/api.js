/** Fetch projects after the backend has applied role-based field filtering. */
export async function getProjects(role) {
  const response = await fetch(`/api/projects?role=${encodeURIComponent(role)}`);
  if (!response.ok) throw new Error("Could not load projects");
  return response.json();
}

/** Send a natural-language query to the configured ProSight AI provider. */
export async function askAgent(query, userRole, projectCode = null, history = []) {
  const response = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, history, user_role: userRole, project_code: projectCode }),
  });
  const payload = await response.json();
  if (!response.ok) {
    console.error("prosight.query_failed", {
      request_id: payload.request_id,
      status: response.status,
      duration_ms: payload.duration_ms,
    });
    const error = new Error("The assistant could not answer");
    error.requestId = payload.request_id;
    throw error;
  }
  console.info("prosight.api_response_received", {
    request_id: payload.request_id,
    provider: payload.mode,
    duration_ms: payload.duration_ms,
  });
  return payload;
}

/** Stream Assistant execution states and return the compatible final response. */
export async function askAgentStream(query, userRole, projectCode = null, history = [], handlers = {}) {
  const response = await fetch("/api/query/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ query, history, user_role: userRole, project_code: projectCode }),
  });
  if (!response.ok || !response.body) throw new Error("The assistant could not answer");
  const reader=response.body.getReader(),decoder=new TextDecoder();
  let buffer="",finalPayload=null,streamError=null;
  while(true){
    const {value,done}=await reader.read();
    buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});
    const blocks=buffer.split(/\r?\n\r?\n/);buffer=blocks.pop()||"";
    for(const block of blocks){
      const type=block.match(/^event:\s*(.+)$/m)?.[1];
      const raw=block.match(/^data:\s*(.+)$/m)?.[1];
      if(!type||!raw)continue;
      const payload=JSON.parse(raw);
      if(type==="status")handlers.onStatus?.(payload.label||"Thinking");
      if(type==="final")finalPayload=payload;
      if(type==="error")streamError=payload;
    }
    if(done)break;
  }
  if(streamError){const error=new Error(streamError.message||"The assistant could not answer");error.requestId=streamError.request_id;throw error;}
  if(!finalPayload)throw new Error("The Assistant stream ended without a final response");
  return finalPayload;
}

export async function updateProject(projectCode, project, role) {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectCode)}?role=${encodeURIComponent(role)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(project),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Could not update project");
  return payload;
}

export async function uploadProjectFile(file, projectCode, userRole) {
  const body = new FormData();
  body.append("file", file); body.append("project_code", projectCode); body.append("user_role", userRole);
  const response = await fetch("/api/uploads", { method: "POST", body });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Upload failed");
  return payload;
}

export async function getIngestionJob(jobId, role) {
  const response = await fetch(`/api/ingestion-jobs/${jobId}?role=${encodeURIComponent(role)}`);
  if (!response.ok) throw new Error("Could not load ingestion status");
  return response.json();
}

export async function getProjectIngestionJobs(projectCode, role) {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectCode)}/ingestion-jobs?role=${encodeURIComponent(role)}`);
  if (!response.ok) throw new Error("Could not load ingestion jobs");
  return response.json();
}

export async function uploadPortfolioWorkbook(file, role, dataset = "combined", projectCode = "") {
  const body = new FormData();
  body.append("file", file); body.append("role", role); body.append("dataset", dataset);
  if (projectCode) body.append("project_code", projectCode);
  const response = await fetch("/api/portfolio-imports", { method: "POST", body });
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.detail;
    throw new Error(typeof detail === "object" ? detail.message : detail || "Portfolio import failed");
  }
  return payload;
}

export function portfolioTemplateUrl(role, dataset = "combined") {
  return `/api/portfolio-imports/template?role=${encodeURIComponent(role)}&dataset=${encodeURIComponent(dataset)}`;
}

export async function getProjectSchedule(role, projectCode) {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectCode)}/schedule?role=${encodeURIComponent(role)}`);
  if (!response.ok) throw new Error("Could not load project schedule");
  return response.json();
}

export async function getPortfolioManpower(role, projectCode = "") {
  const query = new URLSearchParams({ role });
  if (projectCode) query.set("project_code", projectCode);
  const response = await fetch(`/api/portfolio/manpower?${query}`);
  if (!response.ok) throw new Error("Could not load portfolio manpower");
  return response.json();
}

export async function getPortfolioInvoices(role, projectCode = "") {
  const query = new URLSearchParams({ role });
  if (projectCode) query.set("project_code", projectCode);
  const response = await fetch(`/api/portfolio/invoices?${query}`);
  if (!response.ok) throw new Error("Could not load project invoices");
  return response.json();
}

export async function getInvoicePivot(role) {
  const response = await fetch(`/api/portfolio/invoice-pivot?role=${encodeURIComponent(role)}`);
  if (!response.ok) throw new Error("Could not load invoice pivot");
  return response.json();
}

export async function getDocuments(projectCode, role) {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectCode)}/documents?role=${encodeURIComponent(role)}`);
  if (!response.ok) throw new Error("Could not load project documents");
  return response.json();
}

export async function getChangeRequest(changeId, role) {
  const response = await fetch(`/api/change-requests/${changeId}?role=${encodeURIComponent(role)}`);
  if (!response.ok) throw new Error("Could not load change preview");
  return response.json();
}

export async function decideChange(changeId, decision, role) {
  const response = await fetch(`/api/change-requests/${changeId}/${decision}?role=${encodeURIComponent(role)}`, { method: "POST" });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Could not decide change");
  return payload;
}

export async function getNotifications(role, status = "all") {
  const response = await fetch(`/api/notifications?role=${encodeURIComponent(role)}&status=${status}`);
  if (!response.ok) throw new Error("Could not load notifications");
  return response.json();
}

export async function markNotificationRead(notificationId, role) {
  const response = await fetch(`/api/notifications/${notificationId}/read?role=${encodeURIComponent(role)}`, { method: "POST" });
  if (!response.ok) throw new Error("Could not update notification");
  return response.json();
}

export async function markAllNotificationsRead(role) {
  const response = await fetch(`/api/notifications/read-all?role=${encodeURIComponent(role)}`, { method: "POST" });
  if (!response.ok) throw new Error("Could not update notifications");
  return response.json();
}

export async function getApprovals(role) {
  const response = await fetch(`/api/approvals?role=${encodeURIComponent(role)}&status=pending`);
  if (!response.ok) throw new Error("Could not load approval queue");
  return response.json();
}

export async function deleteDocument(documentId, role) {
  const response = await fetch(`/api/documents/${documentId}?role=${encodeURIComponent(role)}`, { method: "DELETE" });
  if (!response.ok) throw new Error("Could not delete document");
  return response.json();
}

export async function createProjectPreview(project, role) {
  const response = await fetch(`/api/projects/change-preview?role=${encodeURIComponent(role)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(project),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Could not create project preview");
  return payload;
}

export async function createProjectImportPreview(file, role) {
  const body = new FormData();
  body.append("file", file);
  body.append("role", role);
  const response = await fetch("/api/projects/import-preview", { method: "POST", body });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Could not preview workbook");
  return payload;
}

export async function updateProjectImport(changeId, project, role) {
  const response = await fetch(`/api/change-requests/${changeId}?role=${encodeURIComponent(role)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(project),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Could not update import preview");
  return payload;
}

export async function confirmDocumentDate(jobId, reportingDate, role) {
  const response = await fetch(`/api/ingestion-jobs/${jobId}/confirm-date?role=${encodeURIComponent(role)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reporting_date: reportingDate }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Could not confirm report date");
  return payload;
}
