import {useEffect, useRef, useState} from 'react';
import {Sparkles, Upload, X} from 'lucide-react';
import {authenticatedFetch} from './auth';
import {readApiResponse} from './apiResponse';
import {classifyProjectRows,projectWorkbookMessage} from './projectImport';
import {PreviewRows} from './AttachmentWorkspace';
import {isFinished,visibleWorkflows,clearWorkflowMessages,settleAttachmentMessages,readWorkflowView} from './chatWorkflowState';

const json=(method,body)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
async function request(path,options){
  const response=await authenticatedFetch('/api/'+path,options);
  return readApiResponse(response,'Could not save this request. Please retry.');
}
export const isCreation=text=>/\b(create|start|add|new)\b.*\bproject\b/i.test(text);
const labels={code:'Project code',name:'Project name',status:'Status',client:'Client',location:'Location',contract_value_usd:'Contract value (USD)',planned_start:'Planned start',planned_finish:'Planned finish',revised_finish:'Revised finish (optional)',reporting_date:'Reporting date',baseline_progress:'Baseline progress (%)',revised_progress:'Revised progress (%)',actual_progress:'Actual progress (%)'};
const numeric=new Set(['contract_value_usd','baseline_progress','revised_progress','actual_progress']);
const states={draft:'Draft',pending:'Awaiting Admin approval',completed:'Applied',rejected:'Cancelled',validation_failed:'Validation failed',publish_failed:'Publication failed',approved:'Approved',publishing:'Publishing',awaiting_confirmation:'Review and confirm',indexing:'Indexing PDF',failed:'Indexing failed',stale:'Data changed — upload again'};

function projectFields(values={}){
  return {
    code:values.code??null,name:values.name??null,
    status:values.status==='planning'?'future':values.status??null,
    client:values.client??null,location:values.location??null,
    contract_value_usd:values.contract_value??null,
    planned_start:values.planned_start_date??null,
    planned_finish:values.planned_finish_date??null,
    revised_finish:null,reporting_date:values.reporting_date??null,
    baseline_progress:null,revised_progress:null,
    actual_progress:values.progress_percent??null,
  };
}
function governedImport(item,organizationRole='member',projects=[]){
  const project=item.rows?.find(row=>row.entity_type==='projects')?.values||{};
  const rowAnalysis=classifyProjectRows(item.rows,projects);
  const analysis={...rowAnalysis,...(item.analysis||{}),projectRows:rowAnalysis.projectRows};
  const displayStatus={review_ready:'draft',awaiting_approval:'pending',published:'completed',rejected:'rejected',cancelled:'rejected'}[item.status]||item.status;
  const issues=(item.issues||[]).map(issue=>issue.message||String(issue));
  return {
    id:item.id||item.import_batch_id,status:displayStatus,native_status:item.status,
    fields:projectFields(project),revision:item.validation_checksum||item.normalized_preview_checksum||item.id,
    missing:[],issues,warnings:[],messages:[],notice:issues.length?'Correct the workbook or mapping profile, then upload a new version.':'',
    source:{filename:item.original_filename||'Workbook',sheet:'Governed import',row:item.rows?.[0]?.row_number||2,
      values:project,mapping_profile:{profile_id:item.mapping_profile_id,name:item.mapping_name}},
    editable:false,ready:item.status==='review_ready',threeLayer:true,analysis,
    can_confirm:item.status==='review_ready',
    can_approve:item.status==='awaiting_approval'&&['owner','admin'].includes(organizationRole),
  };
}

export function useAssistantWorkflows({userId,role,projects,setMessages,onChanged}){
  const empty=!projects.length;
  const permitted=['admin','project_manager'].includes(role);
  const [drafts,setDrafts]=useState([]),[attachments,setAttachments]=useState([]);
  const [activeId,setActiveId]=useState(null),[busy,setBusy]=useState(false),[file,setFile]=useState(null);
  const [allowAI,setAllowAI]=useState(false);
  const [organizationRole,setOrganizationRole]=useState('member');
  const working=useRef(false);
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
      const results=await Promise.allSettled([permitted?request('three-layer/imports'):Promise.resolve({items:[]}),request('attachments')]);
      if(!live||working.current||revision!==generation.current)return;
      if(reviewId.current){
        const requested=results.flatMap(result=>result.status==='fulfilled'?result.value.items:[]).find(item=>item.id===reviewId.current);
        if(requested){remember([requested]);reviewId.current=null;history.replaceState(null,'',location.pathname);}
      }
      if(results[0].status==='fulfilled'){
        const imports=results[0].value.items.map(item=>governedImport(item,results[0].value.organization_role,projects));
        setOrganizationRole(results[0].value.organization_role||'member');clearFinished(imports);setDrafts(visibleWorkflows(imports,view.current));
      }
      if(results[1].status==='fulfilled'){setMessages(current=>settleAttachmentMessages(current,results[1].value.items));setAttachments(visibleWorkflows(results[1].value.items,view.current));}
    }
    load();const timer=setInterval(load,10000);return()=>{live=false;clearInterval(timer)};
  },[permitted,projects]);
  const active=drafts.find(item=>item.id===activeId&&item.editable);
  function chooseFile(value){
    if(value&&!value.name.toLowerCase().endsWith('.xlsx')){
      say('The AI Assistant accepts Excel .xlsx workbooks. Upload project documents from Project Explorer.');
      return;
    }
    setFile(value);
  }
  async function action(work){
    if(working.current)return;
    working.current=true;setBusy(true);
    try{await work()}catch(error){say(error.message)}finally{working.current=false;setBusy(false)}
  }
  async function advanceThreeLayer(item,decision){
    if(decision==='reject'){
      if(item.native_status!=='awaiting_approval')throw new Error('Only an import awaiting approval can be rejected.');
      await request(`three-layer/imports/${item.id}/decision`,json('POST',{decision:'rejected'}));
    }else if(item.native_status==='review_ready'){
      await request(`three-layer/imports/${item.id}/submit`,json('POST',{}));
      if(['owner','admin'].includes(organizationRole)){
        await request(`three-layer/imports/${item.id}/decision`,json('POST',{decision:'approved'}));
        await request(`three-layer/imports/${item.id}/publish`,json('POST',{}));
      }
    }else if(item.native_status==='awaiting_approval'){
      await request(`three-layer/imports/${item.id}/decision`,json('POST',{decision:'approved'}));
      await request(`three-layer/imports/${item.id}/publish`,json('POST',{}));
    }
    const listed=await request('three-layer/imports');
    const updated=listed.items.find(candidate=>candidate.id===item.id);
    if(updated){
      const normalized=governedImport(updated,listed.organization_role,projects);
      putDraft(normalized);
      if(normalized.native_status==='published')say('The approved project changes were published to the construction database.',[item.id]);
      else if(normalized.native_status==='awaiting_approval')say('The project changes were submitted for organization approval.',[item.id]);
    }
    await onChanged?.();
  }
  async function submit(text){
    if(/^(show|review|restore)\s+(saved|pending)\s+(drafts|requests|approvals)[.!]?$/i.test(text.trim())){
      await action(async()=>{
        const results=await Promise.allSettled([permitted?request('three-layer/imports'):Promise.resolve({items:[],organization_role:'member'}),request('attachments')]);
        const importResponse=results[0].status==='fulfilled'?results[0].value:{items:[],organization_role:'member'};
        const attachmentResponse=results[1].status==='fulfilled'?results[1].value:{items:[]};
        const imports=importResponse.items.map(item=>governedImport(item,importResponse.organization_role,projects));
        generation.current++;view.current={fresh:false,ids:[]};persist();
        setDrafts(visibleWorkflows(imports,view.current));setAttachments(visibleWorkflows(attachmentResponse.items,view.current));
        const saved=[...visibleWorkflows(imports,view.current),...visibleWorkflows(attachmentResponse.items,view.current)];
        say(saved.length?'Your saved drafts and pending requests are shown below.':'There are no saved drafts or pending requests.',saved.map(item=>item.id));
      });return true;
    }
    const pendingImport=drafts.find(item=>item.threeLayer&&item.native_status==='review_ready');
    if(!file&&pendingImport&&/\b(yes|confirm|apply|proceed|publish)\b|\bgo ahead\b/i.test(text.trim())){
      setMessages(current=>[...current,{role:'user',content:text,workflowIds:[pendingImport.id]}]);
      await action(()=>advanceThreeLayer(pendingImport,'confirm'));
      return true;
    }
    if(!file&&pendingImport&&/\b(create|update)\b/i.test(text.trim())){
      setMessages(current=>[...current,{role:'user',content:text,workflowIds:[pendingImport.id]}]);
      say(`This governed preview contains ${pendingImport.analysis.createCount} create and ${pendingImport.analysis.updateCount} update. It applies all validated rows atomically. If that matches your intent, say “confirm”; otherwise revise the workbook and upload it again.`,[pendingImport.id]);
      return true;
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
        if(text.trim())data.append('instruction',text.trim());
        const prepared=await request('three-layer/imports/prepare',{method:'POST',body:data});
        const listed=await request('three-layer/imports');
        const persisted=listed.items.find(item=>item.id===prepared.import_batch_id);
        const raw={...(persisted||{...prepared,id:prepared.import_batch_id,status:prepared.valid?'review_ready':'validation_failed',rows:prepared.rows,issues:prepared.issues,original_filename:file.name}),analysis:prepared.analysis,instruction:prepared.instruction};
        const item=governedImport(raw,listed.organization_role||organizationRole,projects);
        remember([item]);
        setMessages(current=>current.map(message=>message.id===uploadMessageId?{...message,workflowIds:[item.id]}:message));
        setDrafts(current=>visibleWorkflows([item,...current.filter(other=>other.id!==item.id)],view.current));
        say(projectWorkbookMessage(item.analysis,text,prepared.valid),[item.id]);
        setFile(null);return;
      }
      if(isCreation(text)||empty){say('Attach an XLSX project register and optionally describe what you want done. I will analyze its project rows, identify creates and updates, and ask you to confirm before publication.');return;}
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
    if(item.threeLayer&&!attachment){
      await advanceThreeLayer(item,decision);return;
    }
    const path=attachment?'attachments/':'project-drafts/';
    const updated=await request(path+item.id+'/decision',json('POST',{decision,...(attachment?{preview_token:item.preview_token}:{revision:item.revision})}));
    if(attachment)setMessages(current=>settleAttachmentMessages(current,[updated]));else clearFinished([updated]);
    if(attachment)setAttachments(current=>visibleWorkflows(current.map(other=>other.id===item.id?updated:other),view.current));else putDraft(updated);
    if(updated.status!=='draft'&&activeId===item.id)setActiveId(null);
    if(!isFinished(updated))say(updated.status==='pending'?'Your request is awaiting Admin approval.':states[updated.status]||updated.status,[item.id]);
    await onChanged?.();
  });
  function resume(item){setActiveId(item.id);say(`Let’s complete ${item.fields.name||'this project'}. ${item.missing.length?'Please provide '+item.missing.join(', ')+'.':'Describe any changes, or review and confirm the draft.'}`,[item.id]);}
  const reload=item=>action(async()=>putDraft(item.threeLayer
    ?governedImport(await request('three-layer/imports/'+item.id),organizationRole,projects)
    :await request('project-drafts/'+item.id)));
  function reset(){
    generation.current++;reviewId.current=null;history.replaceState(null,'',location.pathname);view.current={fresh:true,ids:[]};persist();
    setDrafts([]);setAttachments([]);setActiveId(null);setFile(null);setAllowAI(false);
  }
  return {role,drafts,attachments,active,busy,file,allowAI,setAllowAI,chooseFile,submit,save,decide,resume,reload,permitted,reset,end:()=>setActiveId(null)};
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
      {item.threeLayer&&<p className="workflow-note">Detected changes: {item.analysis.createCount} create · {item.analysis.updateCount} update.</p>}
      {item.threeLayer&&item.analysis.projectRows.length>0&&<div className="project-import-rows" aria-label="Detected project changes">{item.analysis.projectRows.map(row=><div key={row.code}><span className={`project-import-action ${row.action}`}>{row.action}</span><b>{row.code}</b><span>{row.name}</span></div>)}</div>}
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
      {error&&<p role="alert">{error}</p>}
      <div className="workflow-actions">
        {item.editable&&<><button className="secondary" disabled={flow.busy||dirty} onClick={()=>flow.resume(item)}>Continue in chat</button><button className="secondary" disabled={flow.busy||!dirty} onClick={save}>Save edits</button></>}
        {item.can_confirm&&<button className="primary" disabled={flow.busy||dirty} onClick={()=>flow.decide(item,'confirm')}>{flow.role==='admin'?'Confirm project changes':'Confirm and request approval'}</button>}
        {item.can_approve&&<button className="primary" disabled={flow.busy} onClick={()=>flow.decide(item,'approve')}>Approve and apply</button>}
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
  return <><input ref={input} type="file" accept=".xlsx" aria-label="Upload Excel workbook" hidden onChange={event=>{flow.chooseFile(event.target.files?.[0]||null);event.target.value=''}}/>
    <button className="chat-upload secondary" aria-label="Attach Excel workbook" title="Attach Excel workbook" disabled={disabled} onClick={()=>input.current?.click()}><Upload size={18}/></button></>;
}
export function WorkflowComposer({flow,showConsent}){
  return <div className="workflow-composer">
    {flow.file&&<div className="chat-file"><span>{flow.file.name}</span><small>Describe what to create or update, or send without instructions for analysis.</small><button aria-label="Remove attachment" disabled={flow.busy} onClick={()=>flow.chooseFile(null)}><X size={14}/></button></div>}
    {flow.active&&<div className="chat-draft-context"><span>Draft: {flow.active.fields.name||'New project'}</span><button disabled={flow.busy} onClick={flow.end}>Return to general chat</button></div>}
    {!flow.file&&showConsent&&flow.permitted&&<label className="chat-consent"><input type="checkbox" checked={flow.allowAI} onChange={event=>flow.setAllowAI(event.target.checked)}/>Allow AI to interpret my description and current draft.</label>}
  </div>;
}
