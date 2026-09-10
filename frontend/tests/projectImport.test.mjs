import test from "node:test";
import assert from "node:assert/strict";
import {classifyProjectRows, projectWorkbookMessage} from "../src/projectImport.js";

test("workbook rows are classified as project creates and updates", () => {
  const analysis = classifyProjectRows([
    {entity_type: "projects", values: {code: "P-001", name: "Existing"}},
    {entity_type: "projects", values: {code: "P-002", name: "New"}},
    {entity_type: "risks", values: {code: "R-1"}},
  ], [{code: "p-001"}]);
  assert.equal(analysis.projectRowCount, 2);
  assert.equal(analysis.createCount, 1);
  assert.equal(analysis.updateCount, 1);
  assert.deepEqual(analysis.projectRows.map(row => row.action), ["update", "create"]);
});

test("instruction-less workbooks ask the user what to do", () => {
  const message = projectWorkbookMessage({createCount: 1, updateCount: 2}, "", true);
  assert.match(message, /You did not include an instruction/);
  assert.match(message, /Should I apply these project changes/);
});

test("invalid workbooks request correction instead of publication", () => {
  assert.match(projectWorkbookMessage({createCount: 0, updateCount: 0}, "update", false), /validation found issues/);
});
