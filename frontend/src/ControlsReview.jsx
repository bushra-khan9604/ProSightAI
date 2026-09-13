import {useState} from 'react';
import {createImportBatch,addImportBatchFile,validateImportBatch,submitImportBatch,getControlsVersion,editControlsVersion,submitControlsVersion,downloadControlsVersion,confirmDocumentDate} from './api';

export function BatchImport({project,dataset,onImported}) {
  const [files,setFiles]=useState([]),[batch,setBatch]=useState(null),[preview,setPreview]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[status,setStatus]=useState('');
  const [documents,setDocuments]=useState([]),[dates,setDates]=useState({});
  async function validate(){
    setBusy(true);setError('');
    try{
      const created=batch||await createImportBatch(project,dataset);setBatch(created);
      for(const file of files){setStatus(`Validating ${file.name}`);const updated=await addImportBatchFile(created.id,file);setDocuments(updated.input?.documents||[])}
      setPreview(await validateImportBatch(created.id));setStatus('Review validation before submitting. PDFs require their own date confirmation and Admin approval.');
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }
  async function submit(){setBusy(true);try{await submitImportBatch(batch.id);setStatus('Submitted. Structured data becomes authoritative after Admin approval.');onImported()}catch(e){setError(e.message)}finally{setBusy(false)}}
  return <div className="controls-import">
    <label className="drop-zone"><b>Add project files</b><span>XLSX / searchable PDF · 20 MB per file · up to 30 files</span>
      <input className="accessible-file-input" type="file" multiple accept={dataset==='documents'?'.pdf':'.xlsx,.pdf'} disabled={busy||!!batch}
        onChange={e=>setFiles(current=>[...current,...Array.from(e.target.files)].slice(0,30))}/></label>
    {files.map((file,index)=><div className="controls-file" key={`${file.name}-${index}`}><span>{file.name}</span>
      {!batch&&<button aria-label={`Remove ${file.name}`} disabled={busy} onClick={()=>setFiles(files.filter((_,i)=>i!==index))}>Remove</button>}</div>)}
    {!!files.length&&!preview&&<button className="primary" disabled={busy||!project} onClick={validate}>Validate files</button>}
    {status&&<p role="status">{status}</p>}{error&&<p className="portfolio-card-feedback error" role="alert">{error}</p>}
    {documents.map((document,index)=>{const job=document.job;return <div className="controls-file" key={job?.id||index}><span>{document.filename} · {job?.status||'Submitted'}</span>
      {job?.status==='awaiting_date_confirmation'&&<div className="date-confirm"><input aria-label={`Reporting date for ${document.filename}`} type="date" value={dates[job.id]||job.detected_reporting_date||''} onChange={e=>setDates({...dates,[job.id]:e.target.value})}/><button disabled={busy||!(dates[job.id]||job.detected_reporting_date)} onClick={async()=>{setBusy(true);try{const updated=await confirmDocumentDate(job.id,dates[job.id]||job.detected_reporting_date);setDocuments(current=>current.map(d=>d.job?.id===job.id?{...d,job:updated.job||updated}:d))}catch(e){setError(e.message)}finally{setBusy(false)}}}>Confirm date</button></div>}
    </div>})}
    {preview&&<><div className="table-wrap"><table><thead><tr><th>Section</th><th>Before</th><th>After</th></tr></thead><tbody>
      {Object.entries(preview.validation?.counts||{}).map(([name,count])=><tr key={name}><td>{name}</td><td>{preview.validation?.before_counts?.[name]??0}</td><td>{count}</td></tr>)}
    </tbody></table></div>
    {(preview.validation?.warnings||[]).map((warning,i)=><p key={i}>{warning}</p>)}
    <button className="primary" disabled={busy||status.startsWith('Submitted')} onClick={submit}>Submit for approval</button></>}
  </div>;
}

export function ControlsResult({code,versionId,draftId,runId}) {
  const [draft,setDraft]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[status,setStatus]=useState('');
  const [dirty,setDirty]=useState(false);
  async function action(fn){setBusy(true);setError('');try{await fn()}catch(e){setError(e.message)}finally{setBusy(false)}}
  const currentId=draft?.id||draftId||versionId;
  const editable=draft?.content['Proposed Recovery']?{'Proposed Recovery':['activity_reduction_wd','incremental_cost_usd']}:{Schedule:['duration_wd','crew_size'], 'Cost Baseline':['labor_budget_usd','equipment_budget_usd','material_subcontract_usd'],Procurement:['lead_days']};
  function edit(sheet,index,field,value){setDirty(true);setDraft(d=>({...d,content:{...d.content,[sheet]:d.content[sheet].map((r,i)=>i===index?{...r,[field]:value===''?'':Number(value)}:r)}}))}
  return <div className="controls-result">
    <small>Dataset {versionId?.slice(0,8)}</small>
    <div className="controls-actions">
      {draftId&&!draft&&<button disabled={busy} onClick={()=>action(async()=>setDraft(await getControlsVersion(code,currentId)))}>Review draft</button>}
      {['xlsx','pdf'].map(format=><button disabled={busy||dirty} key={format} onClick={()=>action(()=>downloadControlsVersion(code,currentId,format,draftId?null:runId))}>Download {format.toUpperCase()}</button>)}
    </div>
    {draft&&<details open><summary>Planning draft · {draft.status} · {draft.reporting_date}</summary>
      {Object.entries(editable).map(([sheet,fields])=>draft.content[sheet]?.length>0&&<details key={sheet}><summary>{sheet} ({draft.content[sheet].length})</summary>
        <div className="table-wrap"><table><thead><tr><th>Record</th>{fields.map(f=><th key={f}>{f.replaceAll('_',' ')}</th>)}</tr></thead><tbody>
          {draft.content[sheet].map((row,index)=><tr key={row.activity_id||row.package_id||index}><td>{row.name||row.description||row.activity_id}</td>
            {fields.map(field=><td key={field}><input aria-label={`${row.activity_id} ${field}`} type="number" min="0" step="any" disabled={busy||draft.status!=='draft'} value={row[field]??''} onChange={e=>edit(sheet,index,field,e.target.value)}/></td>)}</tr>)}
        </tbody></table></div></details>)}
      {dirty&&<p role="status">Save and recalculate your edits before submitting or downloading.</p>}
      <button disabled={busy||!dirty||draft.status!=='draft'} onClick={()=>action(async()=>{setDraft(await editControlsVersion(code,draft.id,Object.fromEntries(Object.keys(editable).filter(k=>draft.content[k]).map(k=>[k,draft.content[k]]))));setDirty(false);setStatus('New revision saved and recalculated.')})}>Save revised draft</button>
      <button disabled={busy||dirty||draft.status!=='draft'} onClick={()=>action(async()=>{await submitControlsVersion(code,draft.id);setDraft({...draft,status:'pending_approval'});setStatus('Submitted for Admin approval.')})}>Submit saved draft for approval</button>
    </details>}
    {status&&<p role="status">{status}</p>}{error&&<p role="alert">{error}</p>}
  </div>;
}
