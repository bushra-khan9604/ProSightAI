const normalizedCode = value => String(value || "").trim().toLocaleLowerCase();

export function classifyProjectRows(rows = [], projects = []) {
  const existingCodes = new Set(projects.map(project => normalizedCode(project.code)).filter(Boolean));
  const projectRows = rows
    .filter(row => row.entity_type === "projects" && String(row.values?.code || "").trim())
    .map(row => ({
      code: String(row.values.code).trim(),
      name: String(row.values.name || "Unnamed project").trim(),
      action: existingCodes.has(normalizedCode(row.values.code)) ? "update" : "create",
    }));
  return {
    projectRows,
    projectRowCount: projectRows.length,
    createCount: projectRows.filter(row => row.action === "create").length,
    updateCount: projectRows.filter(row => row.action === "update").length,
  };
}

export function projectWorkbookMessage(analysis, instruction, valid) {
  if (!valid) {
    return "I analyzed the workbook and retained it for traceability, but validation found issues. Review the findings below, correct the workbook or organization mapping, and upload it again.";
  }
  const parts = [];
  if (analysis.createCount) parts.push(`${analysis.createCount} new project${analysis.createCount === 1 ? "" : "s"}`);
  if (analysis.updateCount) parts.push(`${analysis.updateCount} existing project update${analysis.updateCount === 1 ? "" : "s"}`);
  const finding = parts.length ? parts.join(" and ") : "no usable project rows";
  if (!String(instruction || "").trim()) {
    return `I analyzed the workbook and found ${finding}. You did not include an instruction. Should I apply these project changes? Review the normalized records below, then confirm or describe what you want changed.`;
  }
  return `I analyzed the workbook, received your instruction, and found ${finding}. Review the normalized records below before confirming the project changes.`;
}
