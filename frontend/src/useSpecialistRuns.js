import {useEffect,useRef} from 'react';
import {getAgentRun,cancelAgentRun} from './api';

export function answerFields(r){return {pending:false,error:false,status:null,runState:'completed',content:r.answer,
  citations:r.citations,route:r.agent_route,mode:r.mode,notice:r.notice,requestId:r.request_id,durationMs:r.duration_ms,
  timeToFirstTokenMs:r.time_to_first_token_ms,controlsVersion:r.dataset_version,draftId:r.draft_id,controlsProject:r.project_code,retryQuery:null};}

/** Recover existing jobs without repeating the user's request or storing access tokens. */
export function useSpecialistRuns(owner,setMessages){
  const key=`prosight-runs:${import.meta.env.VITE_SUPABASE_URL}:${owner}`;
  const entries=useRef(new Map()),terminal=useRef(new Set()),alive=useRef(true);
  function patch(id,fields){if(alive.current)setMessages(items=>items.map(m=>m.id===id?{...m,...fields}:m));}
  function persist(){try{sessionStorage.setItem(key,JSON.stringify([...entries.current.values()].map(({runId,id,query})=>({runId,id,query}))));}catch{/* Storage can be disabled. */}}
  function stop(id){const entry=entries.current.get(id);if(entry)clearTimeout(entry.timer);entries.current.delete(id);persist();}
  function complete(id,answer){terminal.current.add(id);stop(id);patch(id,answerFields(answer));}
  function apply(entry,run){
    if(terminal.current.has(entry.id))return true;
    if(run.status==='completed'&&run.answer){complete(entry.id,run.answer);return true;}
    if(['failed','cancelled'].includes(run.status)){
      terminal.current.add(entry.id);stop(entry.id);
      patch(entry.id,{pending:false,runState:run.status,status:null,error:run.status==='failed',cancelBusy:false,
        content:run.status==='cancelled'?'Task cancelled.':`Task failed. ${run.error||'Please try again.'}`,retryQuery:entry.query});return true;
    }
    patch(entry.id,{pending:true,error:false,cancelBusy:false,runState:run.status==='queued'?'queued':'running',
      status:run.status==='queued'?'Waiting to start…':run.kind==='planner'?'Planner is preparing your draft…':'Analyst is analyzing…'});
    return false;
  }
  async function check(id){
    const entry=entries.current.get(id);if(!entry||entry.checking||terminal.current.has(id))return;
    clearTimeout(entry.timer);entry.checking=true;
    try{
      const run=await getAgentRun(entry.runId);
      if(!alive.current||entries.current.get(id)!==entry)return;
      if(!entry.query&&run.input?.query){entry.query=run.input.query;persist();}
      if(!apply(entry,run))entry.timer=setTimeout(()=>check(id),Date.now()-entry.started<60000?3000:10000);
    }catch{
      if(alive.current&&entries.current.get(id)===entry&&!terminal.current.has(id))patch(id,{pending:false,error:false,runState:'disconnected',cancelBusy:false,
        status:null,notice:'Unable to check this task. Check your connection and project access, then check its status.'});
    }finally{entry.checking=false;}
  }
  function register(id,runId,query){
    if(terminal.current.has(id))return;
    if(!entries.current.has(id))entries.current.set(id,{id,runId,query,started:Date.now()});
    persist();patch(id,{runId,runState:'running',status:'Working on your project…'});
  }
  function recover(id){patch(id,{pending:true,error:false,runState:'reconnecting',status:'Checking task status…'});check(id);}
  async function cancel(id){
    const entry=entries.current.get(id);if(!entry||entry.cancelling)return;
    entry.cancelling=true;patch(id,{cancelBusy:true,status:'Cancelling…'});
    try{const run=await cancelAgentRun(entry.runId);if(alive.current&&entries.current.get(id)===entry&&!apply(entry,run))recover(id);}
    catch{if(alive.current&&entries.current.get(id)===entry&&!terminal.current.has(id)){patch(id,{cancelBusy:false,notice:'Cancellation could not be confirmed. Checking task status…'});recover(id);}}
    finally{entry.cancelling=false;}
  }
  useEffect(()=>{
    alive.current=true;
    try{
      sessionStorage.removeItem('prosight-pending-run');
      const saved=JSON.parse(sessionStorage.getItem(key)||'[]');
      if(Array.isArray(saved))for(const e of saved){
        if(!e.id||!e.runId)continue;
        entries.current.set(e.id,{...e,started:Date.now()});
        setMessages(items=>items.some(m=>m.id===e.id)?items:[...items,{id:e.id,runId:e.runId,role:'assistant',content:'',pending:true,status:'Checking task status…',runState:'reconnecting'}]);
        check(e.id);
      }
    }catch{/* Ignore malformed recovery metadata. */}
    return()=>{alive.current=false;for(const e of entries.current.values())clearTimeout(e.timer);entries.current.clear();};
  },[key]);
  return {register,recover,cancel,complete,isTerminal:id=>terminal.current.has(id)};
}
