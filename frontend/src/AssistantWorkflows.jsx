import {useEffect, useRef, useState} from 'react';
import {Sparkles, Upload, X} from 'lucide-react';
import {authenticatedFetch} from './auth';
import {getDocuments} from './api';
import {PreviewRows} from './AttachmentWorkspace';
import {isFinished,visibleWorkflows,clearWorkflowMessages,settleAttachmentMessages,readWorkflowView} from './chatWorkflowState';

const json=(method,body)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
async function request(path,options){
  const response=await authenticatedFetch('/api/'+path,options);
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Could not save this request. Please retry.');
  return data;
}
export const isCreation=text=>/\b(create|start|add|new)\b.*\bproject\b/i.test(text);
const labels={code:'Project code',name:'Project name',status:'Status',client:'Client',location:'Location',contract_value_usd:'Contract value (USD)',planned_start:'Planned start',planned_finish:'Planned finish',revised_finish:'Revised finish (optional)',reporting_date:'Reporting date',baseline_progress:'Baseline progress (%)',revised_progress:'Revised progress (%)',actual_progress:'Actual progress (%)'};
const numeric=new Set(['contract_value_usd','baseline_progress','revised_progress','actual_progress']);
const states={draft:'Draft',pending:'Awaiting Admin approval',completed:'Created',rejected:'Cancelled',awaiting_confirmation:'Review and confirm',indexing:'Indexing PDF',failed:'Indexing failed',stale:'Data changed — upload again'};
const kinds={new_project:'Create project drafts',employees_training:'Add employees and training',attendance_payroll:'Add attendance and payroll',manpower_deployment:'Add manpower and deployment',pdf:'Add PDF evidence',project:'Update project details',manpower:'Update portfolio manpower',invoices:'Update invoices',schedule:'Update schedule',combined:'Update portfolio manpower and invoices'};
const portfolioKinds=new Set(['employees_training','attendance_payroll','manpower_deployment']);
const managerKinds=new Set(['new_project','employees_training','attendance_payroll']);

export function useAssistantWorkflows({userId,role,empty,selectedProject,setMessages,onChanged}){
  const permitted=['admin','project_manager'].includes(role);
  const [drafts,setDrafts]=useState([]),[attachments,setAttachments]=useState([]);
  const [activeId,setActiveId]=useState(null),[busy,setBusy]=useState(false),[file,setFile]=useState(null);
  const [kind,setKind]=useState('new_project'),[allowAI,setAllowAI]=useState(false),[external,setExternal]=useState(false);
  const [documents,setDocuments]=useState([]),[replacement,setReplacement]=useState('');
  const uploadId=useRef(null),working=useRef(false);
  const viewKey='prosight:chat-workflows:'+userId;
  const view=useRef(null),generation=useRef(0),reviewId=useRef(new URLSearchParams(location.search).get("review"));
  if(view.current===null)view.current=readWorkflowView(sessionStorage,viewKey);
  function persist(){try{sessionStorage.setItem(viewKey,JSON.stringify(view.current))}catch{}}
  function remember(items){view.current.ids=[...new Set([...view.current.ids,...items.map(item=>item.id)])];persist();}
  function clearFinished(items){setMessages(current=>clearWorkflowMessages(current,items.filter(isFinished).map(item=>item.id)));}
  const say=(content,workflowIds)=>setMessages(current=>[...current,{role:'assistant',content,workflowIds}]);
  const putDraft=item=>{remember([item]);clearFinished([item]);setDrafts(current=>visibleWorkflows([item,...current.filter(other=>other.id!==item.id)],view.current));};
  useEffect(()=>{
    let live=true;
    async function load(){
      if(working.current)return;
      const revision=generation.current;
      const results=await Promise.allSettled([permitted?request('project-drafts'):Promise.resolve({items:[]}),request('attachments')]);
      if(!live||working.current||revision!==generation.current)return;
      if(reviewId.current){
        const requested=results.flatMap(result=>result.status==='fulfilled'?result.value.items:[]).find(item=>item.id===reviewId.current);
        if(requested){remember([requested]);reviewId.current=null;history.replaceState(null,'',location.pathname);}
      }
      if(results[0].status==='fulfilled'){clearFinished(results[0].value.items);setDrafts(visibleWorkflows(results[0].value.items,view.current));}
      if(results[1].status==='fulfilled'){setMessages(current=>settleAttachmentMessages(current,results[1].value.items));setAttachments(visibleWorkflows(results[1].value.items,view.current));}
    }
    load();const timer=setInterval(load,10000);return()=>{live=false;clearInterval(timer)};
  },[permitted]);
  useEffect(()=>{
    setReplacement('');setDocuments([]);if(!selectedProject)return;
    let live=true;getDocuments(selectedProject,role).then(result=>{if(live)setDocuments(Array.isArray(result)?result:result.items||result.documents||[])}).catch(()=>{});
    return()=>{live=false};
  },[selectedProject,role]);
  const active=drafts.find(item=>item.id===activeId&&item.editable);
  function chooseFile(value){
    setFile(value);uploadId.current=crypto.randomUUID();setExternal(false);setReplacement('');
    if(value)setKind(value.name.toLowerCase().endsWith('.pdf')?'pdf':empty?'new_project':permitted?'new_project':'project');
  }
  async function action(work){
    if(working.current)return;
    working.current=true;setBusy(true);
    try{await work()}catch(error){say(error.message)}finally{working.current=false;setBusy(false)}
  }
  async function submit(text){
    if(/^(show|review|restore)\s+(saved|pending)\s+(drafts|requests|approvals)[.!]?$/i.test(text.trim())){
      await action(async()=>{
        const results=await Promise.all([permitted?request('project-drafts'):Promise.resolve({items:[]}),request('attachments')]);
        generation.current++;view.current={fresh:false,ids:[]};persist();
        setDrafts(visibleWorkflows(results[0].items,view.current));setAttachments(visibleWorkflows(results[1].items,view.current));
        const saved=results.flatMap(result=>visibleWorkflows(result.items,view.current));
        say(saved.length?'Your saved drafts and pending requests are shown below.':'There are no saved drafts or pending requests.',saved.map(item=>item.id));
      });return true;
    }
    const normalized=text.toLowerCase();
    const tokens=normalized.split(/[^a-z0-9-]+/);
    const matches=drafts.filter(item=>item.editable&&((item.fields.code&&tokens.includes(item.fields.code.toLowerCase()))||(item.fields.name&&normalized.includes(item.fields.name.toLowerCase()))));
    if(!file&&!active&&!empty&&!isCreation(text)&&!matches.length)return false;
    await action(async()=>{
      if(!file&&!permitted){say('An Admin or Project Manager can create the first project. Once approved, you can upload its files.');return;}
      if(file){
        const uploadMessageId=crypto.randomUUID();
        setMessages(current=>[...current,{id:uploadMessageId,role:'user',content:[text,file.name].filter(Boolean).join('\n')}]);
        const data=new FormData();data.append('file',file);
        if(kind==='new_project'){
          data.append('batch_id',uploadId.current);
          const result=await request('project-drafts/workbook',{method:'POST',body:data});
          remember(result.items);
          setMessages(current=>current.map(message=>message.id===uploadMessageId?{...message,workflowIds:result.items.map(item=>item.id)}:message));
          setDrafts(current=>visibleWorkflows([...result.items,...current.filter(item=>!result.items.some(next=>next.id===item.id))],view.current));
          setActiveId(result.items.length===1?result.items[0].id:null);say(result.message,result.items.map(item=>item.id));
        }else{
          if(!selectedProject&&!portfolioKinds.has(kind)){say('Select the target project in Analysis context, then send the attachment again.');return;}
          data.append('instruction',text||kinds[kind]);data.append('kind',kind);data.append('project_code',selectedProject);
          data.append('external_processing',String(external));
          data.append('replacement_id',replacement);
          const result=await request('attachments',{method:'POST',body:data});
          remember([result]);
          setMessages(current=>current.map(message=>message.id===uploadMessageId?{...message,workflowIds:[result.id]}:message));
          setAttachments(current=>visibleWorkflows([result,...current.filter(item=>item.id!==result.id)],view.current));
          say('I analyzed the attachment and saved its preview below. Review it before confirming the update.',[result.id]);
        }
        setFile(null);return;
      }
      if(matches.length>1){say('Your message names multiple drafts. Use Continue in chat on the project you want to complete first. Each project has its own reviewed confirmation.');return;}
      let draft=matches[0]||active;
      if(!draft&&!isCreation(text)&&drafts.filter(item=>item.editable).length>1){say('Which project should we complete? Mention its project code or choose Continue in chat on its draft. To start another project, say “Create a new project”.');return;}
      if(!draft){draft=await request('project-drafts',json('POST',{id:crypto.randomUUID()}));putDraft(draft);setActiveId(draft.id);}
      else setActiveId(draft.id);
      setMessages(current=>[...current,{role:'user',content:text,workflowIds:[draft.id]}]);
      if(!allowAI){say('I opened a draft for you. You can fill in its fields without AI, or allow AI processing below the chat box and send your description again.',[draft.id]);return;}
      const result=await request('project-drafts/'+draft.id,json('PATCH',{revision:draft.revision,message:text,allow_ai:allowAI}));
      putDraft(result);say(result.messages.at(-1)?.content||result.notice||'Review the project draft below.',[result.id]);
    });
    return true;
  }
  async function save(item,fields){
    // A rejected save must stay visibly dirty in the preview.
    if(working.current)throw new Error('Another request is still running.');
    working.current=true;setBusy(true);
    try{const result=await request('project-drafts/'+item.id,json('PATCH',{revision:item.revision,fields}));putDraft(result);return result;}
    finally{working.current=false;setBusy(false)}
  }
  const decide=(item,decision,attachment=false)=>action(async()=>{
    const path=attachment?'attachments/':'project-drafts/';
    const updated=await request(path+item.id+'/decision',json('POST',{decision,...(attachment?{preview_token:item.preview_token}:{revision:item.revision})}));
    if(attachment)setMessages(current=>settleAttachmentMessages(current,[updated]));else clearFinished([updated]);
    if(attachment)setAttachments(current=>visibleWorkflows(current.map(other=>other.id===item.id?updated:other),view.current));else putDraft(updated);
    if(updated.status!=='draft'&&activeId===item.id)setActiveId(null);
    if(!isFinished(updated))say(updated.status==='pending'?'Your request is awaiting Admin approval.':states[updated.status]||updated.status,[item.id]);
    await onChanged?.();
  });
  function resume(item){setActiveId(item.id);say(`Let’s complete ${item.fields.name||'this project'}. ${item.missing.length?'Please provide '+item.missing.join(', ')+'.':'Describe any changes, or review and confirm the draft.'}`,[item.id]);}
  const reload=item=>action(async()=>putDraft(await request('project-drafts/'+item.id)));
  function reset(){
    generation.current++;reviewId.current=null;history.replaceState(null,'',location.pathname);view.current={fresh:true,ids:[]};persist();
    setDrafts([]);setAttachments([]);setActiveId(null);setFile(null);setKind('new_project');setAllowAI(false);setExternal(false);setReplacement('');uploadId.current=null;
  }
  return {role,drafts,attachments,active,busy,file,kind,setKind,allowAI,setAllowAI,external,setExternal,documents,replacement,setReplacement,chooseFile,submit,save,decide,resume,reload,permitted,reset,end:()=>setActiveId(null)};
}

function ProjectDraftMessage({item,flow}){
  const [fields,setFields]=useState(item.fields),[dirty,setDirty]=useState(false),[error,setError]=useState('');
  const baseRevision=useRef(item.revision);
  useEffect(()=>{if(!dirty){setFields(item.fields);baseRevision.current=item.revision}},[item.revision,dirty]);
  async function save(){try{const result=await flow.save({...item,revision:baseRevision.current},fields);setFields(result.fields);baseRevision.current=result.revision;setDirty(false);setError('')}catch(err){setError(err.message)}}
  return <div className="message assistant workflow-message"><div className="avatar"><Sparkles size={18}/></div><div className="message-content">
    <details className="chat-project-draft" open={flow.active?.id===item.id?true:undefined}>
      <summary><strong>{item.fields.name||'New project draft'}</strong> <span>{item.fields.code||'Code needed'} · {states[item.status]}</span></summary>
      {item.source&&<p className="workflow-note">{item.source.filename} · {item.source.sheet}, row {item.source.row}</p>}
      {!!item.missing.length&&<p className="workflow-note">Still needed: {item.missing.join(', ')}.</p>}
      {item.warnings?.map((warning,index)=><p className="workflow-note" key={index}>{warning}</p>)}
      {item.issues.map((issue,index)=><p role="alert" key={index}>{issue}</p>)}
      {item.notice&&<p role="status">{item.notice}</p>}
      <div className="chat-draft-fields">{Object.entries(labels).filter(([field])=>fields.status==='active'||(!field.includes('progress')&&!['reporting_date','revised_finish'].includes(field))).map(([field,label])=><label key={field}>{fields.status==='completed'&&field==='planned_start'?'Start date':fields.status==='completed'&&field==='planned_finish'?'End date':field==='actual_progress'?'Completed progress (%)':label}{['baseline_progress','revised_progress'].includes(field)?' (optional)':''}
        {field==='status'?<select aria-label={fields.status==='completed'&&field==='planned_start'?'Start date':fields.status==='completed'&&field==='planned_finish'?'End date':field==='actual_progress'?'Completed progress (%)':label} disabled={!item.editable||flow.busy} value={fields[field]??''} onChange={event=>{setFields({...fields,[field]:event.target.value||null});setDirty(true)}}><option value="">Choose status</option>{['future','active','completed'].map(value=><option key={value}>{value}</option>)}</select>:
        <input aria-label={fields.status==='completed'&&field==='planned_start'?'Start date':fields.status==='completed'&&field==='planned_finish'?'End date':field==='actual_progress'?'Completed progress (%)':label} disabled={!item.editable||flow.busy} type={numeric.has(field)?'number':/start|finish|date/.test(field)?'date':'text'} step={numeric.has(field)?'any':undefined} min={numeric.has(field)?0:undefined} max={field.includes('progress')?100:undefined} value={fields[field]??''} onChange={event=>{setFields({...fields,[field]:event.target.value===''?null:numeric.has(field)?Number(event.target.value):event.target.value});setDirty(true)}}/>}
      </label>)}</div>
      {item.source&&<details><summary>Original worksheet values</summary><dl className="chat-source-values">{Object.entries(item.source.values).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value==null?'Not provided':String(value)}</dd></div>)}</dl></details>}
      {item.source?.records&&<details><summary>Workbook sources · {item.source.worksheets_scanned?.length||1} sheets inspected</summary>{item.source.records.map((record,index)=><div key={index}><strong>{record.sheet} · row {record.row}</strong><dl className="chat-source-values">{Object.entries(record.values).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value==null?'Not provided':String(value)}</dd></div>)}</dl></div>)}</details>}
      {item.source?.mapping&&<details><summary>JSON field mappings · {item.source.mapping_profile?.name}</summary><dl className="chat-source-values">{Object.entries(item.source.mapping).map(([field,mapping])=><div key={field}><dt>{labels[field]||field}</dt><dd>Column {mapping.column} · {mapping.header||'No label'} · {mapping.method}</dd></div>)}</dl><p className="workflow-note">Profile: {item.source.mapping_profile?.profile_id}. Review inferred or configured columns before confirming.</p><details><summary>Applied mapping profile</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(item.source.mapping_profile,null,2)}</pre></details></details>}
      {error&&<p role="alert">{error}</p>}
      <div className="workflow-actions">
        {item.editable&&<><button className="secondary" disabled={flow.busy||dirty} onClick={()=>flow.resume(item)}>Continue in chat</button><button className="secondary" disabled={flow.busy||!dirty} onClick={save}>Save edits</button></>}
        {item.can_confirm&&<button className="primary" disabled={flow.busy||dirty} onClick={()=>flow.decide(item,'confirm')}>{flow.role==='admin'?'Confirm and create':'Confirm and request approval'}</button>}
        {item.can_approve&&<button className="primary" disabled={flow.busy} onClick={()=>flow.decide(item,'approve')}>Approve and create</button>}
        {(item.editable||item.can_approve)&&<button className="secondary" disabled={flow.busy} onClick={()=>flow.decide(item,'reject')}>Cancel / reject</button>}
        <button className="secondary" disabled={flow.busy} onClick={()=>{setDirty(false);setError('');flow.reload(item)}}>Reload preview</button>
      </div>{dirty&&<p className="workflow-note">Save edits before continuing in chat or confirming.</p>}
    </details>
  </div></div>;
}

export function WorkflowMessages({flow}){
  return <>{flow.drafts.map(item=><ProjectDraftMessage key={item.id} item={item} flow={flow}/>)}
    {flow.attachments.map(item=><div className="message assistant workflow-message" key={item.id}><div className="avatar"><Sparkles size={18}/></div><div className="message-content"><details>
      <summary>{item.filename} · {item.project_code} · {states[item.status]||item.status}</summary>
      <p className="workflow-note">{item.preview.summary}</p>
      {item.preview.counts&&<p className="workflow-note">Mapped records: {Object.entries(item.preview.counts).map(([name,count])=>`${name.replaceAll('_',' ')} ${count}`).join(' · ')}</p>}
      {item.preview.rows&&<PreviewRows rows={item.preview.rows} totalRows={item.preview.row_count||item.preview.rows.length}/>}
      {item.preview.excerpt&&<blockquote>{item.preview.excerpt}</blockquote>}
      {item.preview.warnings?.map((warning,index)=><p key={index}>{String(warning)}</p>)}
      {item.preview.mappings&&<details><summary>Schema and column mappings</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(item.preview.mappings,null,2)}</pre></details>}
      {item.error&&<p role="alert">{item.error}</p>}
      <div className="workflow-actions">
        {item.can_confirm&&<button className="primary" disabled={flow.busy} onClick={()=>flow.decide(item,'confirm',true)}>Confirm update</button>}
        {item.can_approve&&<button className="primary" disabled={flow.busy} onClick={()=>flow.decide(item,'approve',true)}>Approve and apply</button>}
        {(item.can_confirm||item.can_approve)&&<button className="secondary" disabled={flow.busy} onClick={()=>flow.decide(item,'reject',true)}>Reject / cancel</button>}
        {item.can_retry&&<button className="secondary" disabled={flow.busy} onClick={()=>flow.decide(item,'retry',true)}>Retry indexing</button>}
      </div>
    </details></div></div>)}</>;
}

export function ChatUpload({flow,disabled}){
  const input=useRef(null);
  return <><input ref={input} type="file" accept=".xlsx,.pdf" aria-label="Upload Excel or PDF" hidden onChange={event=>{flow.chooseFile(event.target.files?.[0]||null);event.target.value=''}}/>
    <button className="chat-upload secondary" aria-label="Attach Excel or PDF" title="Attach Excel or PDF" disabled={disabled} onClick={()=>input.current?.click()}><Upload size={18}/></button></>;
}
export function WorkflowComposer({flow,showConsent}){
  return <div className="workflow-composer">
    {flow.file&&<div className="chat-file"><span>{flow.file.name}</span><select aria-label="Attachment action" value={flow.kind} disabled={flow.busy} onChange={event=>flow.setKind(event.target.value)}>{Object.entries(kinds).filter(([key])=>flow.file.name.toLowerCase().endsWith('.pdf')?key==='pdf':key!=='pdf'&&(!managerKinds.has(key)||flow.permitted)).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select><button aria-label="Remove attachment" disabled={flow.busy} onClick={()=>flow.chooseFile(null)}><X size={14}/></button></div>}
    {flow.active&&<div className="chat-draft-context"><span>Draft: {flow.active.fields.name||'New project'}</span><button disabled={flow.busy} onClick={flow.end}>Return to general chat</button></div>}
    {!flow.file&&showConsent&&flow.permitted&&<label className="chat-consent"><input type="checkbox" checked={flow.allowAI} onChange={event=>flow.setAllowAI(event.target.checked)}/>Allow AI to interpret my description and current draft.</label>}
    {flow.file&&flow.kind==='pdf'&&<><label className="chat-file">Document version<select aria-label="Document version" value={flow.replacement} onChange={event=>flow.setReplacement(event.target.value)}><option value="">New evidence document</option>{flow.documents.filter(doc=>doc.kind==='pdf'&&doc.approval_status==='approved').map(doc=><option key={doc.id} value={doc.id}>Replace {doc.filename}</option>)}</select></label><label className="chat-consent"><input type="checkbox" checked={flow.external} onChange={event=>flow.setExternal(event.target.checked)}/>Permit external PDF embedding after Admin approval.</label></>}
  </div>;
}
