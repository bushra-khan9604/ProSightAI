import {useEffect,useState,useRef} from 'react';
import {authenticatedFetch} from './auth';

async function call(path,options){
  const response=await authenticatedFetch('/api/project-drafts'+path,options);
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Could not update project draft');
  return data;
}
const json=(method,body)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
const labels={code:'Project code',name:'Project name',status:'Status',client:'Client',location:'Location',contract_value_usd:'Contract value (USD)',planned_start:'Planned start',planned_finish:'Planned finish',revised_finish:'Revised finish (optional)',reporting_date:'Reporting date',baseline_progress:'Baseline progress (%)',revised_progress:'Revised progress (%)',actual_progress:'Actual progress (%)'};
const numeric=new Set(['contract_value_usd','baseline_progress','revised_progress','actual_progress']);
const states={draft:'Draft — not created',pending:'Awaiting Admin approval',completed:'Project created',rejected:'Cancelled / rejected'};

export default function ProjectCreationWorkspace({role,empty,onChanged,initialMessage,clearInitialMessage}){
  const handledInitial=useRef("");
  const permitted=['admin','project_manager'].includes(role);
  const [open,setOpen]=useState(empty),[items,setItems]=useState([]),[draft,setDraft]=useState(null);
  const [fields,setFields]=useState({}),[message,setMessage]=useState(''),[allowAI,setAllowAI]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[dirty,setDirty]=useState(false);
  function select(item){setDraft(item);setFields(item.fields);setDirty(false);setError('')}
  async function refresh(){const data=await call('');setItems(data.items);return data.items}
  useEffect(()=>{if(!permitted)return;let active=true;const load=()=>call('').then(data=>{if(active)setItems(data.items)}).catch(err=>{if(active)setError(err.message)});load();const timer=setInterval(load,10000);return()=>{active=false;clearInterval(timer)}},[permitted]);
  async function start(text=''){
    setOpen(true);setBusy(true);setError('');
    try{const result=await call('',json('POST',{id:crypto.randomUUID()}));select(result);setMessage(text);await refresh()}
    catch(err){setError(err.message)}finally{setBusy(false)}
  }
  useEffect(()=>{if(!initialMessage){handledInitial.current="";return}if(permitted&&handledInitial.current!==initialMessage){handledInitial.current=initialMessage;start(initialMessage);clearInitialMessage?.()}},[initialMessage,permitted]);
  useEffect(()=>{const latest=items.find(item=>item.id===draft?.id);if(latest&&!dirty&&!busy&&(latest.revision!==draft.revision||latest.status!==draft.status))select(latest)},[items,dirty,busy,draft?.id]);
  async function edit(useMessage){
    setBusy(true);setError('');
    try{const updated=await call('/'+draft.id,json('PATCH',{revision:draft.revision,...(useMessage?{message,allow_ai:allowAI}:{fields})}));select(updated);if(useMessage)setMessage('');await refresh()}
    catch(err){setError(err.message)}finally{setBusy(false)}
  }
  async function decide(decision){
    setBusy(true);setError('');
    try{const updated=await call('/'+draft.id+'/decision',json('POST',{revision:draft.revision,decision}));select(updated);await refresh();await onChanged?.()}
    catch(err){setError(err.message)}finally{setBusy(false)}
  }
  if(!permitted)return empty?<section className="empty-project-guide"><h2>Your organization has no approved projects yet</h2><p>An Admin or Project Manager needs to create the first project. Once approved, you can upload its files and update permitted information.</p></section>:null;
  return <section className="project-creation-workspace" aria-label="Create a project with AI">
    <button className="primary" aria-expanded={open} onClick={()=>setOpen(!open)}>Describe a new project</button>
    {open&&<div className="project-creation-panel card">
      <h2>{empty?'Start your first project':'Create a project with the assistant'}</h2>
      <p>Describe it → fill missing details → review → {role==='admin'?'confirm creation':'request Admin approval'}. Drafts do not appear as live projects.</p>
      <div className="attachment-actions"><button className="secondary" disabled={busy} onClick={()=>start()}>Start a new draft</button>
      <label>Saved drafts and approvals<select aria-label="Saved project drafts" value={draft?.id||''} onChange={event=>{const item=items.find(item=>item.id===event.target.value);if(item)select(item)}}><option value="">Select a saved draft</option>{items.map(item=><option key={item.id} value={item.id}>{item.fields.name||'Unnamed draft'} · {states[item.status]}</option>)}</select></label></div>
      {items.some(item=>item.status==='pending')&&<p role="status">{items.filter(item=>item.status==='pending').length} project request(s) awaiting Admin approval. Select a saved request to review it.</p>}
      {error&&<p role="alert" className="attachment-error">{error}</p>}
      {draft&&<><p role="status"><strong>{states[draft.status]}</strong></p>
        <div className="creation-conversation" aria-live="polite">{draft.messages.map((item,index)=><p key={index}><b>{item.role==='assistant'?'Assistant':'You'}: </b>{item.content}</p>)}</div>
        {draft.editable&&<form onSubmit={event=>{event.preventDefault();if(message.trim()&&allowAI&&!dirty)edit(true)}}>
          <label>Describe the project or answer the assistant<textarea aria-label="Project description" rows={3} maxLength={4000} value={message} onChange={event=>setMessage(event.target.value)} placeholder="Create a future project called Oasis School in Dubai for Horizon Education. The contract is USD 5 million, starting 1 March 2027 and finishing 30 June 2028."/></label>
          <label className="creation-consent"><input type="checkbox" checked={allowAI} onChange={event=>setAllowAI(event.target.checked)}/>Allow the configured AI provider to interpret this description and the current draft. Do not include restricted data.</label>
          <button className="primary" disabled={busy||!message.trim()||!allowAI||dirty}>{busy?'Working…':'Send description'}</button>
          <p>You can also fill in the fields below without sending them to AI.</p>
        </form>}
        <h3>Project preview</h3>
        {draft.missing.length>0&&<p>Still needed: {draft.missing.join(', ')}.</p>}
        {draft.issues.length>0&&<ul role="alert">{draft.issues.map((issue,index)=><li key={index}>{issue}</li>)}</ul>}
        {draft.notice&&<p role="status">{draft.notice}</p>}
        <div className="creation-fields">{Object.entries(labels).map(([field,label])=><label key={field}>{label}{field==='status'?<select disabled={!draft.editable||busy} value={fields[field]??''} onChange={event=>{setFields({...fields,[field]:event.target.value||null});setDirty(true)}}><option value="">Choose status</option>{['future','active','completed'].map(value=><option key={value}>{value}</option>)}</select>:<input aria-label={label} disabled={!draft.editable||busy} type={numeric.has(field)?'number':field.includes('start')||field.includes('finish')||field==='reporting_date'?'date':'text'} step={numeric.has(field)?'any':undefined} min={numeric.has(field)?0:undefined} max={field.includes('progress')?100:undefined} value={fields[field]??''} onChange={event=>{setFields({...fields,[field]:event.target.value===''?null:numeric.has(field)?Number(event.target.value):event.target.value});setDirty(true)}}/>}</label>)}</div>
        <p>Confirming creates a new project only. It will not overwrite an existing project or add documents.</p>
        <div className="attachment-actions">
          {draft.editable&&<button className="secondary" disabled={busy||!dirty} onClick={()=>edit(false)}>Save field edits</button>}
          {draft.can_confirm&&<button className="primary" disabled={busy||dirty} onClick={()=>decide('confirm')}>{role==='admin'?'Confirm and create project':'Confirm and request Admin approval'}</button>}
          {draft.can_approve&&<button className="primary" disabled={busy||dirty} onClick={()=>decide('approve')}>Approve and create project</button>}
          {(draft.editable||draft.can_approve)&&<button className="secondary" disabled={busy} onClick={()=>decide('reject')}>Cancel / reject draft</button>}
          <button className="secondary" disabled={busy} onClick={async()=>{try{select(await call('/'+draft.id))}catch(err){setError(err.message)}}}>Reload saved preview</button>
        </div>{dirty&&<p>Save your edits before sending another description or confirming.</p>}
      </>}
    </div>}
  </section>;
}
