import { useEffect, useState } from "react";
import { authenticatedFetch } from "./auth";
import { getDocuments } from "./api";

async function request(url,options){
  const response=await authenticatedFetch(url,options);
  const value=await response.json();
  if(!response.ok)throw new Error(typeof value.detail==="string"?value.detail:"Attachment request failed");
  return value;
}
const labels={pdf:"Add PDF evidence",project:"Update project workbook",new_project:"Create project from workbook",employees_training:"Add employees and training",attendance_payroll:"Add attendance and payroll",manpower_deployment:"Add manpower and deployment",manpower:"Update portfolio manpower",invoices:"Update invoices",schedule:"Update schedule",combined:"Update portfolio manpower and invoices"};
const portfolioKinds=new Set(["employees_training","attendance_payroll","manpower_deployment"]);
const managerKinds=new Set(["new_project","employees_training","attendance_payroll"]);
const statusLabels={awaiting_confirmation:"Review and confirm",pending:"Awaiting Admin approval",indexing:"Indexing PDF",completed:"Completed",failed:"Indexing failed — retry available",rejected:"Rejected",stale:"Data changed — upload again for a new preview"};
const text=value=>value===null||value===undefined?"—":typeof value==="object"?JSON.stringify(value):String(value);

function flatten(value,prefix="",result={}){
  if(value&&typeof value==="object"&&Object.keys(value).length){
    Object.entries(value).forEach(([key,item])=>flatten(item,prefix?`${prefix} / ${key}`:key,result));
  }else result[prefix]=Array.isArray(value)?"None":text(value);
  return result;
}
export function PreviewRows({rows,totalRows=rows.length}){
  const [page,setPage]=useState(0);
  return <><p>{totalRows} proposed rows. Review the before and after values before confirming.{rows.length<totalRows?` Showing the first ${rows.length} rows after full-workbook validation.`:""}</p>
    <div className="attachment-table">{rows.slice(page*20,page*20+20).map((row,index)=>{
      const before=flatten(row.before||{}),after=flatten(row.after||{});
      const fields=[...new Set([...Object.keys(before),...Object.keys(after)])].filter(Boolean);
      return <article key={index}><h4>{row.key} · {row.operation}</h4><table><thead><tr><th>Field</th><th>Before</th><th>After</th></tr></thead><tbody>{fields.map(field=><tr key={field}><td>{field.replaceAll("_"," ")}</td><td>{before[field]??"Not set"}</td><td className={before[field]!==after[field]?"attachment-value-changed":""}>{after[field]??"Not set"}</td></tr>)}</tbody></table></article>;
    })}</div>
    {rows.length>20&&<div className="attachment-actions"><button type="button" disabled={!page} onClick={()=>setPage(page-1)}>Previous rows</button><span>Page {page+1} of {Math.ceil(rows.length/20)}</span><button type="button" disabled={(page+1)*20>=rows.length} onClick={()=>setPage(page+1)}>Next rows</button></div>}
  </>;
}

export default function AttachmentWorkspace({projects,role,selectedProject,onChanged}){
  const [open,setOpen]=useState(false),[file,setFile]=useState(null),[instruction,setInstruction]=useState("");
  const [kind,setKind]=useState("pdf"),[external,setExternal]=useState(false),[replacement,setReplacement]=useState("");
  const [items,setItems]=useState([]),[documents,setDocuments]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const [notice,setNotice]=useState("");
  async function refresh(){const result=await request('/api/attachments');setItems(result.items)}
  useEffect(()=>{let active=true;const load=()=>request('/api/attachments').then(result=>{if(active)setItems(result.items)}).catch(err=>{if(active)setError(err.message)});load();const timer=setInterval(load,5000);return()=>{active=false;clearInterval(timer)}},[]);
  useEffect(()=>{setReplacement("");if(!selectedProject){setDocuments([]);return}let active=true;getDocuments(selectedProject,role).then(result=>{if(active)setDocuments(Array.isArray(result)?result:result.items||result.documents||[])}).catch(()=>setDocuments([]));return()=>{active=false}},[selectedProject,role]);
  useEffect(()=>{if(!projects.length&&["admin","project_manager"].includes(role)){setKind("new_project")}},[projects.length,role]);
  async function upload(event){
    event.preventDefault();if(!file||busy)return;setBusy(true);setError("");setNotice("");
    try{const data=new FormData();data.append('file',file);data.append('instruction',instruction);data.append('kind',kind);data.append('project_code',selectedProject||'');data.append('external_processing',String(external));data.append('replacement_id',replacement);
      await request('/api/attachments',{method:'POST',body:data});await refresh();setNotice("Preview saved. No project data has been changed. Review it below.");
    }catch(err){setError(err.message)}finally{setBusy(false)}
  }
  async function decide(item,decision){
    setBusy(true);setError("");setNotice("");
    try{const updated=await request(`/api/attachments/${item.id}/decision`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision,preview_token:item.preview_token})});await refresh();await onChanged?.();setNotice(statusLabels[updated.status]||updated.status)}
    catch(err){setError(err.message)}finally{setBusy(false)}
  }
  return <section className="attachment-workspace" aria-label="Attachment and Update Agent">
    <button type="button" className="secondary" aria-expanded={open} onClick={()=>setOpen(!open)}>Attach PDF / Excel · Review updates</button>
    {open&&<div className="attachment-panel"><h3>Attachment and Update Agent</h3><p>Files are analyzed locally. A saved preview and the required approvals come before database changes or external PDF embedding.</p>
      {!projects.length&&<p>No projects yet. Admin or Project Manager can attach a Projects workbook to prepare the first project.</p>}
      <form onSubmit={upload} className="attachment-form">
        <label>Action<select value={kind} onChange={event=>{setKind(event.target.value);setFile(null);setReplacement("")}}>{Object.entries(labels).filter(([value])=>!managerKinds.has(value)||["admin","project_manager"].includes(role)).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        <label>Instruction<textarea required minLength={5} maxLength={4000} value={instruction} onChange={event=>setInstruction(event.target.value)} placeholder="Describe what this file should add or update. The selected action and preview control the change."/></label>
        <label>File<input key={kind} type="file" required accept={kind==="pdf"?".pdf":".xlsx"} onChange={event=>setFile(event.target.files?.[0]||null)}/></label>
        {portfolioKinds.has(kind)?<p>Portfolio scope: every referenced project and employee must already exist or be included in the same supported workbook.</p>:kind!=="new_project"&&<p>Target project: <b>{selectedProject||"Select a project in Analysis context above"}</b></p>}
        {kind==="pdf"&&<><label>Document version<select value={replacement} onChange={event=>setReplacement(event.target.value)}><option value="">New evidence document</option>{documents.filter(doc=>doc.kind==="pdf"&&doc.approval_status==="approved").map(doc=><option key={doc.id} value={doc.id}>Replace {doc.filename}</option>)}</select></label>
        <label className="attachment-consent"><input type="checkbox" checked={external} onChange={event=>setExternal(event.target.checked)}/>This document is permitted for external embedding after Admin approval.</label><p>Leave unchecked for local analysis only. Do not authorize restricted documents.</p></>}
        {kind!=="pdf"&&<p>Use the defined workbook schema. Recognized calculated columns are recomputed without executing formulas. The mapped rows must be reviewed before approval.</p>}
        <button className="primary" disabled={busy||!file||(kind!=="new_project"&&!portfolioKinds.has(kind)&&!selectedProject)}>{busy?"Working…":"Analyze and prepare preview"}</button>
      </form>
      {error&&<p role="alert" className="attachment-error">{error}</p>}{notice&&<p role="status">{notice}</p>}
      <h3>Saved attachment operations</h3>{!items.length&&<p>No attachments yet.</p>}
      {items.map(item=><details className="attachment-operation" key={item.id}><summary>{item.filename} · {item.project_code} · {statusLabels[item.status]||item.status}</summary>
        <p>{item.instruction}</p><p>{item.preview.summary}</p>
        {item.preview.counts&&<p>Mapped records: {Object.entries(item.preview.counts).map(([name,count])=>`${name.replaceAll("_"," ")} ${count}`).join(" · ")}</p>}
        {item.preview.rows&&<PreviewRows rows={item.preview.rows} totalRows={item.preview.row_count||item.preview.rows.length}/>}
        {item.preview.excerpt&&<><p>{item.preview.pages_with_text} pages with text · approximately {item.preview.chunks} chunks</p><blockquote>{item.preview.excerpt}</blockquote>{item.preview.replaces&&<p>Replaces {item.preview.replaces.filename} after successful indexing.</p>}</>}
        {item.preview.warnings?.length>0&&<ul>{item.preview.warnings.map((warning,index)=><li key={index}>{text(warning)}</li>)}</ul>}
        {item.preview.mappings&&<details><summary>Column mappings</summary><pre>{JSON.stringify(item.preview.mappings,null,2)}</pre></details>}
        {item.error&&<p role="alert">{item.error}</p>}
        <div className="attachment-actions">
          {item.can_confirm&&<button className="primary" disabled={busy} onClick={()=>decide(item,'confirm')}>{role==="admin"?"Confirm and apply approved preview":"Confirm and request Admin approval"}</button>}
          {item.can_approve&&<button className="primary" disabled={busy} onClick={()=>decide(item,'approve')}>Approve and apply</button>}
          {(item.can_confirm||item.can_approve)&&<button className="secondary" disabled={busy} onClick={()=>decide(item,'reject')}>Reject / cancel</button>}
          {item.can_retry&&<button className="secondary" disabled={busy} onClick={()=>decide(item,'retry')}>Retry indexing</button>}
        </div>
      </details>)}
    </div>}
  </section>;
}
