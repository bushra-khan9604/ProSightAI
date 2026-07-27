/** Fetch projects after the backend has applied role-based field filtering. */
export async function getProjects(role) {
  const response = await fetch(`/api/projects?role=${encodeURIComponent(role)}`);
  if (!response.ok) throw new Error("Could not load projects");
  return response.json();
}

/** Send a natural-language query to the configured ProSight AI provider. */
export async function askAgent(query, userRole, projectCode = null) {
  const response = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, user_role: userRole, project_code: projectCode }),
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
