const finished = new Set(['completed', 'rejected']);
export const isFinished = item => finished.has(item.status);

export function visibleWorkflows(items, view) {
  return items.filter(item => !isFinished(item) && (!view.fresh || view.ids.includes(item.id)));
}

export function clearWorkflowMessages(messages, ids) {
  const cleared = new Set(ids);
  const keep = messages.filter(message => message.role === 'user' || !message.workflowIds?.some(id => cleared.has(id)));
  return keep.length === messages.length ? messages : keep;
}

export function settleAttachmentMessages(messages, items) {
  const completed = items.filter(item => item.status === 'completed' &&
    messages.some(message => message.workflowIds?.includes(item.id)) &&
    !messages.some(message => message.completedWorkflowId === item.id));
  const kept = clearWorkflowMessages(messages, items.filter(isFinished).map(item => item.id));
  if (!completed.length) return kept;
  return [...kept, ...completed.map(item => ({role: 'assistant',
    content: 'Upload/ingestion complete.', completedWorkflowId: item.id}))];
}

export function readWorkflowView(storage, key) {
  try {
    const saved = JSON.parse(storage.getItem(key));
    if (saved?.fresh === true && Array.isArray(saved.ids)) {
      return {fresh: true, ids: saved.ids.filter(id => typeof id === 'string')};
    }
  } catch { /* A fresh in-memory view still works when storage is unavailable. */ }
  return {fresh: false, ids: []};
}
