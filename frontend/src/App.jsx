import { useEffect, useRef, useState } from "react";
import {
  Activity, Bell, BookOpen, Bot, BriefcaseBusiness, Building2,
  ChevronRight, CircleDollarSign, Clock3, LayoutDashboard, Menu,
  FileSpreadsheet, FileText, Moon, Paperclip, Send, Sun, Trash2,
  Upload, Users, Wrench, X,
} from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  askAgent, confirmDocumentDate, createProjectImportPreview, createProjectPreview,
  decideChange, deleteDocument, getChangeRequest, getDocuments, getIngestionJob,
  getProjects, updateProjectImport, uploadProjectFile,
} from "./api";

const roles = {
  "Project Manager": "project_manager",
  "Planning Engineer": "planning_engineer",
  Admin: "admin",
};

const nav = [
  ["assistant", "AI Assistant", Bot],
  ["dashboard", "Command Center", LayoutDashboard],
  ["projects", "Project Explorer", Building2],
];

const money = (value) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);

/** Render the health classification derived from project progress variance. */
function Status({ project }) {
  const risk = project.variance_pct <= -3;
  return <span className={`status ${risk ? "risk" : "success"}`}>{risk ? "At risk" : "On track"}</span>;
}

function Sidebar({ page, setPage, collapsed, setCollapsed }) {
  return <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
    <div className="brand">
      <div className="brand-mark"><img src="/prosight-logo.png" alt="ProSight AI logo"/></div>
      {!collapsed && <div><strong>ProSight AI</strong><small>Construction intelligence</small></div>}
    </div>
    <nav>{nav.map(([id, label, Icon]) =>
      <button key={id} className={page === id ? "active" : ""} onClick={() => setPage(id)}>
        <Icon size={19}/>{!collapsed && <span>{label}</span>}
      </button>)}
    </nav>
    <div className="sidebar-foot">
      <button className="collapse" onClick={() => setCollapsed(!collapsed)}>
        {collapsed ? <Menu size={18}/> : <X size={18}/>}
      </button>
    </div>
  </aside>;
}

/** Global search, role selector, notifications, and persisted theme control. */
function Header({ dark, setDark, role, setRole }) {
  return <header>
    <div className="header-actions">
      <select value={role} onChange={(e) => setRole(e.target.value)}>
        {Object.keys(roles).map((item) => <option key={item}>{item}</option>)}
      </select>
      <button className="icon-btn" aria-label="Notifications"><Bell size={18}/><span className="dot"/></button>
      <button className="theme-switch" onClick={() => setDark(!dark)}>
        {dark ? <Sun size={16}/> : <Moon size={16}/>}<span>{dark ? "Light" : "Dark"}</span>
      </button>
    </div>
  </header>;
}

/** Reusable portfolio metric card. */
function Kpi({ icon: Icon, label, value, detail, tone }) {
  return <article className="kpi card">
    <div className={`kpi-icon ${tone}`}><Icon size={20}/></div>
    <div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
  </article>;
}

/** Executive command center assembled from authorized project records. */
function Dashboard({ projects, goToAssistant }) {
  const active = projects.filter((p) => p.status === "active");
  const delayed = active.filter((p) => p.delay_days > 0);
  const avg = active.reduce((sum, p) => sum + p.actual_progress, 0) / (active.length || 1);
  const progress = active.map((p) => ({
    name: p.name.split(" ").slice(0, 2).join(" "),
    Baseline: p.baseline_progress, Revised: p.revised_progress, Actual: p.actual_progress,
  }));
  // The prototype dataset contains snapshots rather than full history, so this
  // illustrative trend should be replaced by progress_snapshots in production.
  const trend = [
    { month: "Feb", Revised: 40, Actual: 38 }, { month: "Mar", Revised: 47, Actual: 45 },
    { month: "Apr", Revised: 55, Actual: 51 }, { month: "May", Revised: 61, Actual: 57 },
    { month: "Jun", Revised: 67, Actual: 63 }, { month: "Jul", Revised: 72, Actual: 68.5 },
  ];
  const risk = [...delayed].sort((a, b) => a.variance_pct - b.variance_pct)[0];
  return <>
    <PageTitle eyebrow="Portfolio overview" title="Project Command Center"
      subtitle="A live view of portfolio health, delivery performance, and emerging risks."/>
    <section className="kpi-grid">
      <Kpi icon={BriefcaseBusiness} label="Active projects" value={active.length} detail="Current delivery portfolio" tone="blue"/>
      <Kpi icon={CircleDollarSign} label="Contract value" value={`$${(active.reduce((s,p)=>s+p.contract_value_usd,0)/1e6).toFixed(1)}M`} detail="Across active projects" tone="green"/>
      <Kpi icon={Activity} label="Average progress" value={`${avg.toFixed(1)}%`} detail="Actual portfolio progress" tone="purple"/>
      <Kpi icon={Clock3} label="Delayed projects" value={delayed.length} detail="Require schedule attention" tone="red"/>
    </section>
    <section className="dashboard-grid">
      <article className="card health-panel">
        <CardTitle title="Project health" action="View all"/>
        <div className="health-head"><span>Project</span><span>Progress</span><span>Status</span></div>
        {active.map((p) => <div className="health-row" key={p.code}>
          <div><strong>{p.name}</strong><small>{p.code}</small></div>
          <div className="progress-wrap"><div className="progress"><i style={{width:`${p.actual_progress}%`}}/></div><b>{p.actual_progress}%</b></div>
          <Status project={p}/>
        </div>)}
      </article>
      <article className="card chart-panel">
        <CardTitle title="Schedule performance" action="Last 6 months"/>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={trend}><CartesianGrid strokeDasharray="3 3" vertical={false}/>
            <XAxis dataKey="month"/><YAxis domain={[30, 80]} unit="%"/><Tooltip/>
            <Line dataKey="Revised" stroke="#63b3ed" strokeWidth={3} dot={false}/>
            <Line dataKey="Actual" stroke="#2563eb" strokeWidth={3} dot={{r:3}}/>
          </LineChart>
        </ResponsiveContainer>
      </article>
      <article className="card insight-panel">
        <div className="spark"><Bot size={18}/> AI insight</div>
        {risk ? <><h3>{risk.name}</h3><p>Actual progress is <b>{Math.abs(risk.variance_pct)} points behind</b> the revised plan, with a {risk.delay_days}-day completion delay.</p>
          <div className="insight-stat"><span>Actual</span><strong>{risk.actual_progress}%</strong></div>
          <div className="insight-stat"><span>Revised</span><strong>{risk.revised_progress}%</strong></div>
          <button className="primary wide" onClick={() => goToAssistant(`Explain the progress and delay for ${risk.code}`)}>View full analysis <ChevronRight size={16}/></button>
        </> : <p>No schedule risks detected.</p>}
      </article>
    </section>
    <section className="lower-grid">
      <article className="card"><CardTitle title="Progress by project"/>
        <ResponsiveContainer width="100%" height={220}><BarChart data={progress} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" horizontal={false}/><XAxis type="number" domain={[0,100]}/>
          <YAxis dataKey="name" type="category" width={105}/><Tooltip/><Legend/>
          <Bar dataKey="Baseline" fill="#cbd5e1" radius={4}/><Bar dataKey="Revised" fill="#60a5fa" radius={4}/><Bar dataKey="Actual" fill="#2563eb" radius={4}/>
        </BarChart></ResponsiveContainer>
      </article>
      <article className="card"><CardTitle title="Upcoming milestones"/>
        <div className="timeline">{active.flatMap((p)=>p.milestones.filter((m)=>m.status!=="complete").slice(0,2).map((m)=>({...m, project:p.name}))).map((m,i)=>
          <div className="timeline-item" key={`${m.name}${i}`}><i/><div><strong>{m.name}</strong><small>{m.project}</small></div><span>{m.status.replace("due ","")}</span></div>)}</div>
      </article>
    </section>
  </>;
}

/** Consistent title block shared by every application view. */
function PageTitle({ eyebrow, title, subtitle, children }) {
  return <div className="page-title"><div><span>{eyebrow}</span><h1>{title}</h1><p>{subtitle}</p></div>{children}</div>;
}

/** Small heading row used at the top of dashboard cards. */
function CardTitle({ title, action }) {
  return <div className="card-title"><h2>{title}</h2>{action && <button>{action}<ChevronRight size={14}/></button>}</div>;
}

/** Interactive single-project view with schedule, contacts, and site operations. */
function ProjectExplorer({ projects }) {
  const [selected, setSelected] = useState(projects[0]?.code);
  const [tab, setTab] = useState("overview");
  const project = projects.find((p)=>p.code===selected) || projects[0];
  if (!project) return null;
  const manpower = project.manpower.map((m)=>({name:m.designation,value:m.count}));
  return <>
    <PageTitle eyebrow="Project controls" title="Project Explorer" subtitle="Inspect schedules, teams, site operations, and supporting evidence.">
      <select className="project-select" value={project.code} onChange={(e)=>setSelected(e.target.value)}>
        {projects.map((p)=><option key={p.code} value={p.code}>{p.code} — {p.name}</option>)}
      </select>
    </PageTitle>
    <section className="project-hero card">
      <div><span className="status success">{project.status}</span><h2>{project.name}</h2><p>{project.location} · {project.client}</p></div>
      <div className="hero-metrics"><div><span>Contract value</span><strong>{money(project.contract_value_usd)}</strong></div>
        <div><span>Actual progress</span><strong>{project.actual_progress}%</strong></div>
        <div><span>Variance</span><strong className={project.variance_pct<0?"negative":""}>{project.variance_pct>0?"+":""}{project.variance_pct} pp</strong></div>
        <div><span>Delay</span><strong>{project.delay_days} days</strong></div></div>
    </section>
    <div className="tabs">{["overview","contacts","operations","milestones"].map((item)=>
      <button className={tab===item?"active":""} onClick={()=>setTab(item)} key={item}>{item}</button>)}</div>
    {tab==="overview" && <section className="lower-grid">
      <article className="card"><CardTitle title="Schedule & progress"/><div className="date-grid">
        <div><span>Planned start</span><strong>{project.planned_start}</strong></div>
        <div><span>Planned finish</span><strong>{project.planned_finish}</strong></div>
        <div><span>Revised finish</span><strong>{project.revised_finish||"Not set"}</strong></div></div>
        <ResponsiveContainer width="100%" height={230}><BarChart data={[
          {name:"Baseline",value:project.baseline_progress},{name:"Revised",value:project.revised_progress},{name:"Actual",value:project.actual_progress}]}>
          <CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="name"/><YAxis domain={[0,100]}/><Tooltip/>
          <Bar dataKey="value" radius={[7,7,0,0]}>{["#94a3b8","#60a5fa","#2563eb"].map(c=><Cell fill={c} key={c}/>)}</Bar>
        </BarChart></ResponsiveContainer></article>
      <article className="card"><CardTitle title="Evidence"/>{project.sources.map(s=><div className="evidence" key={s}><BookOpen size={16}/><span>{s}</span></div>)}</article>
    </section>}
    {tab==="contacts" && <article className="card table-card"><table><thead><tr><th>Name</th><th>Project role</th><th>Email</th><th>Mobile</th></tr></thead>
      <tbody>{project.contacts.map(c=><tr key={c.name}><td><b>{c.name}</b></td><td>{c.project_role}</td><td>{c.email}</td><td>{c.mobile}</td></tr>)}</tbody></table></article>}
    {tab==="operations" && <section className="three-grid">
      <article className="card"><CardTitle title="Current activities"/>{project.activities.map(a=><div className="list-row" key={a}><Activity size={16}/>{a}</div>)}</article>
      <article className="card"><CardTitle title="Manpower"/><ResponsiveContainer width="100%" height={230}><PieChart><Pie data={manpower} dataKey="value" innerRadius={55} outerRadius={85} fill="#2563eb"><Cell fill="#2563eb"/><Cell fill="#06b6d4"/><Cell fill="#10b981"/><Cell fill="#8b5cf6"/><Cell fill="#f59e0b"/></Pie><Tooltip/></PieChart></ResponsiveContainer></article>
      <article className="card"><CardTitle title="Equipment"/>{project.equipment.map(e=><div className="list-row split" key={e.type}><span><Wrench size={15}/>{e.type}</span><b>{e.count}</b></div>)}</article>
    </section>}
    {tab==="milestones" && <article className="card timeline large">{project.milestones.map((m,i)=>
      <div className="timeline-item" key={m.name}><i/><div><strong>{m.name}</strong><small>Milestone {i+1}</small></div><span>{m.status}</span></div>)}</article>}
  </>;
}

/** Project-scoped upload, ingestion status, review, and document management drawer. */
function UploadCenter({ open, onClose, role, projects, selectedProject, setSelectedProject, refreshProjects, returnFocusRef }) {
  const [documents,setDocuments]=useState([]),[jobs,setJobs]=useState([]),[error,setError]=useState("");
  const [showProjectForm,setShowProjectForm]=useState(false),[projectChange,setProjectChange]=useState(null);
  const [dateEdits,setDateEdits]=useState({});
  const [draft,setDraft]=useState({
    code:"",name:"",status:"future",client:"",location:"",contract_value_usd:0,
    planned_start:"",planned_finish:"",revised_finish:"",reporting_date:new Date().toISOString().slice(0,10),
    baseline_progress:0,revised_progress:0,actual_progress:0,
  });
  const roleKey=roles[role];
  useEffect(()=>{
    if(!open)return;
    const closeOnEscape=event=>{if(event.key==="Escape")onClose()};
    window.addEventListener("keydown",closeOnEscape);
    return()=>window.removeEventListener("keydown",closeOnEscape);
  },[open,onClose]);
  async function refresh(){
    if(!selectedProject)return;
    try{setDocuments(await getDocuments(selectedProject,roleKey));}catch{setDocuments([])}
  }
  useEffect(()=>{if(open)refresh()},[open,selectedProject,role]);
  useEffect(()=>{
    if(!jobs.some(j=>["queued","processing"].includes(j.status)))return;
    const timer=setInterval(async()=>setJobs(current=>Promise.all(current.map(async j=>{
      if(!["queued","processing"].includes(j.status))return j;
      try{return await getIngestionJob(j.id,roleKey)}catch{return j}
    }))),1200);
    return()=>clearInterval(timer);
  },[jobs]);
  useEffect(()=>{if(jobs.some(j=>["ready","awaiting_approval"].includes(j.status)))refresh()},[jobs]);
  async function uploadFiles(files){
    if(!selectedProject){setError("Select a project before uploading.");return}
    setError("");
    for(const file of files){
      try{const result=await uploadProjectFile(file,selectedProject,roleKey);setJobs(j=>[result.job,...j])}
      catch(e){setError(e.message)}
    }
  }
  async function review(job,decision){
    try{
      await decideChange(job.change_request_id,decision,roleKey);
      setJobs(items=>items.map(x=>x.id===job.id?{...x,status:decision==="approve"?"ready":"rejected",message:`Change ${decision}d`}:x));
      refresh();
    }catch(e){setError(e.message)}
  }
  async function showPreview(job){
    try{const change=await getChangeRequest(job.change_request_id,roleKey);alert(JSON.stringify(change.preview,null,2))}
    catch(e){setError(e.message)}
  }
  async function remove(id){try{await deleteDocument(id,roleKey);refresh()}catch(e){setError(e.message)}}
  async function submitProject(event){
    event.preventDefault();setError("");
    try{
      const normalized={...draft,contract_value_usd:Number(draft.contract_value_usd)};
      setProjectChange(projectChange
        ? await updateProjectImport(projectChange.id,normalized,roleKey)
        : await createProjectPreview(normalized,roleKey));
    }
    catch(e){setError(e.message)}
  }
  async function uploadNewProjectWorkbook(file){
    if(!file)return;
    setError("");
    try{
      const change=await createProjectImportPreview(file,roleKey);
      setProjectChange(change);
      const project=change.payload.projects[0];
      setDraft(Object.fromEntries(Object.keys(draft).map(key=>[key,project[key]??draft[key]])));
    }catch(e){setError(e.message)}
  }
  async function reviewProject(decision){
    try{
      if(decision==="approve"){
        await updateProjectImport(projectChange.id,{...draft,contract_value_usd:Number(draft.contract_value_usd)},roleKey);
      }
      await decideChange(projectChange.id,decision,roleKey);
      if(decision==="approve"){
        await refreshProjects();
        setSelectedProject(draft.code);
        setShowProjectForm(false);
      }
      setProjectChange({...projectChange,status:decision==="approve"?"applied":"rejected"});
    }catch(e){setError(e.message)}
  }
  async function confirmDate(job){
    try{
      const reportingDate=dateEdits[job.id]||job.detected_reporting_date;
      const updated=await confirmDocumentDate(job.id,reportingDate,roleKey);
      setJobs(items=>items.map(item=>item.id===job.id?updated:item));
    }catch(e){setError(e.message)}
  }
  if(!open)return null;
  return <div className="upload-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget){onClose();returnFocusRef?.current?.focus()}}}>
  <aside className="upload-center" role="dialog" aria-modal="true" aria-label="Upload Center" onMouseDown={event=>event.stopPropagation()}>
    <div className="upload-head"><div><span>PROJECT KNOWLEDGE</span><h2>Upload Center</h2></div><button onClick={onClose}><X/></button></div>
    {["project_manager","admin"].includes(roleKey)&&<section className="new-project-panel">
      <button className="new-project-toggle" onClick={()=>setShowProjectForm(!showProjectForm)}>
        {showProjectForm?"Close project form":"Add new project"}
      </button>
      {showProjectForm&&<form className="new-project-form" onSubmit={submitProject}>
        <h3>New project details</h3>
        <label className="project-excel-drop">
          <FileSpreadsheet size={22}/><b>Auto-fill from canonical XLSX</b>
          <span>One project row; related sheets are retained for approval.</span>
          <input type="file" accept=".xlsx" onChange={e=>uploadNewProjectWorkbook(e.target.files[0])}/>
        </label>
        {projectChange?.preview?.related_counts&&<div className="import-counts">
          {Object.entries(projectChange.preview.related_counts).map(([name,count])=><span key={name}><b>{count}</b>{name}</span>)}
        </div>}
        <fieldset><legend>Project identity</legend><div className="project-form-grid">
          <label>Project code<input required value={draft.code} onChange={e=>setDraft({...draft,code:e.target.value.toUpperCase()})} placeholder="PRJ-2027-010"/></label>
          <label>Status<select value={draft.status} onChange={e=>setDraft({...draft,status:e.target.value})}><option value="future">Future</option><option value="active">Active</option><option value="completed">Completed</option></select></label>
          <label className="wide">Project name<input required value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/></label>
          <label className="wide">Client<input required value={draft.client} onChange={e=>setDraft({...draft,client:e.target.value})}/></label>
          <label>Location<input required value={draft.location} onChange={e=>setDraft({...draft,location:e.target.value})}/></label>
        </div></fieldset>
        <fieldset><legend>Commercial details</legend><div className="project-form-grid">
          <label>Contract value (USD)<input required min="0" type="number" value={draft.contract_value_usd} onChange={e=>setDraft({...draft,contract_value_usd:e.target.value})}/></label>
          <label>Reporting date<input required type="date" value={draft.reporting_date} onChange={e=>setDraft({...draft,reporting_date:e.target.value})}/></label>
        </div></fieldset>
        <fieldset><legend>Schedule</legend><div className="project-form-grid">
          <label>Planned start<input required type="date" value={draft.planned_start} onChange={e=>setDraft({...draft,planned_start:e.target.value})}/></label>
          <label>Planned finish<input required type="date" value={draft.planned_finish} onChange={e=>setDraft({...draft,planned_finish:e.target.value})}/></label>
          <label>Revised finish<input type="date" value={draft.revised_finish} onChange={e=>setDraft({...draft,revised_finish:e.target.value})}/></label>
        </div></fieldset>
        <fieldset><legend>Progress</legend><div className="project-form-grid">
          {["baseline_progress","revised_progress","actual_progress"].map(field=><label key={field}>{field.replaceAll("_"," ")} (%)<input type="number" min="0" max="100" step=".1" value={draft[field]} onChange={e=>setDraft({...draft,[field]:Number(e.target.value)})}/></label>)}
        </div></fieldset>
        <button className="primary project-submit" type="submit">{projectChange?"Save preview changes":"Create approval preview"}</button>
        {projectChange&&<div className="project-review"><b>{projectChange.status.replaceAll("_"," ")}</b><span>{roleKey==="admin"?"Review and approve before the database is changed.":"Saved for Admin review; the database has not changed."}</span>
          {projectChange.status==="pending"&&<div className="job-actions"><button type="button" onClick={()=>alert(JSON.stringify(projectChange.preview,null,2))}>Preview</button>{roleKey==="admin"&&<><button type="button" onClick={()=>reviewProject("approve")}>Approve</button><button type="button" onClick={()=>reviewProject("reject")}>Reject</button></>}</div>}</div>}
      </form>}
    </section>}
    <label>Target project<select value={selectedProject} onChange={e=>setSelectedProject(e.target.value)}>
      <option value="">Select a project</option>{projects.map(p=><option value={p.code} key={p.code}>{p.code} — {p.name}</option>)}
    </select></label>
    <label className="drop-zone" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();uploadFiles([...e.dataTransfer.files])}}>
      <Upload size={28}/><b>Drop PDF or XLSX files here</b><span>PDF 20 MB · XLSX 10 MB</span>
      <input type="file" accept=".pdf,.xlsx" multiple onChange={e=>uploadFiles([...e.target.files])}/>
    </label>
    {error&&<div className="upload-error">{error}</div>}
    <h3>Ingestion jobs</h3>{jobs.length===0&&<p className="empty">No uploads in this session.</p>}
    {jobs.map(job=><div className="job-row" key={job.id}><div><b>{job.status.replaceAll("_"," ")}</b><span>{job.message}</span>
      <progress value={job.progress} max="100"/></div>
      {job.status==="awaiting_date_confirmation"&&<div className="date-confirm"><input type="date" value={dateEdits[job.id]||job.detected_reporting_date||""} onChange={e=>setDateEdits({...dateEdits,[job.id]:e.target.value})}/><button onClick={()=>confirmDate(job)}>Confirm date</button></div>}
      {job.status==="awaiting_approval"&&<div className="job-actions"><button onClick={()=>showPreview(job)}>Preview</button>
        {roleKey==="admin"&&<><button onClick={()=>review(job,"approve")}>Approve</button><button onClick={()=>review(job,"reject")}>Reject</button></>}</div>}</div>)}
    <h3>Project documents</h3>{documents.map(doc=><div className="document-row" key={doc.id}>
      {doc.kind==="pdf"?<FileText/>:<FileSpreadsheet/>}<div><b>{doc.filename}</b><span>{doc.status}</span></div>
      {roleKey==="admin"&&<button onClick={()=>remove(doc.id)} title="Delete document"><Trash2/></button>}</div>)}
  </aside></div>;
}

/** Conversational UI that preserves messages for the current browser session. */
function Assistant({ role, projects, initialQuery, clearInitial, refreshProjects }) {
  const [messages,setMessages]=useState([{role:"assistant",content:"Hello — I’m ProSight AI. Ask me about project progress, contacts, activities, resources, or milestones.",citations:[]}]);
  const [query,setQuery]=useState(initialQuery||""); const [loading,setLoading]=useState(false);
  const [uploadsOpen,setUploadsOpen]=useState(false),[selectedProject,setSelectedProject]=useState("");
  const messagesRef=useRef(null),uploadTriggerRef=useRef(null),forceScrollRef=useRef(false);
  useEffect(()=>{if(initialQuery){setQuery(initialQuery);clearInitial();}},[initialQuery]);
  useEffect(()=>{setSelectedProject("")},[role]);
  useEffect(()=>{
    const container=messagesRef.current;
    if(!container)return;
    const nearBottom=container.scrollHeight-container.scrollTop-container.clientHeight<120;
    if(forceScrollRef.current||nearBottom){
      container.scrollTo({top:container.scrollHeight,behavior:forceScrollRef.current?"auto":"smooth"});
      forceScrollRef.current=false;
    }
  },[messages,loading]);
  function openUploads(){setUploadsOpen(true)}
  function closeUploads(){setUploadsOpen(false);requestAnimationFrame(()=>uploadTriggerRef.current?.focus())}
  async function submit(text=query){
    if(!text.trim()||loading)return;
    console.info("prosight.query_submitted", {query_length:text.trim().length,role:roles[role]});
    forceScrollRef.current=true;setMessages(m=>[...m,{role:"user",content:text}]);setQuery("");setLoading(true);
    // The backend returns either OpenAI application mode or local test/data mode.
    try{const result=await askAgent(text,roles[role],selectedProject||null);
      console.info("prosight.response_rendered",{request_id:result.request_id,provider:result.mode,duration_ms:result.duration_ms});
      setMessages(m=>[...m,{role:"assistant",content:result.answer,citations:result.citations,route:result.agent_route,mode:result.mode,notice:result.notice,requestId:result.request_id,durationMs:result.duration_ms}]);}
    catch(error){console.error("prosight.client_error",{request_id:error.requestId||null,error_type:error.name});
      setMessages(m=>[...m,{role:"assistant",content:`I could not reach the ProSight service. Reference: ${error.requestId||"not available"}.`,error:true}]);}
    finally{setLoading(false);}
  }
  return <div className="assistant-page"><PageTitle eyebrow="Multi-agent project intelligence" title="AI Project Assistant" subtitle="Ask about structured project data or evidence from uploaded reports."/>
    <div className="suggestions"><select value={selectedProject} onChange={e=>setSelectedProject(e.target.value)}><option value="">All projects</option>{projects.map(p=><option value={p.code} key={p.code}>{p.code}</option>)}</select>
      {["Which active projects are delayed?","Show project contacts","What does the latest report say?"].map(item=><button key={item} onClick={()=>submit(item)}>{item}</button>)}
      <button ref={uploadTriggerRef} className="upload-trigger" onClick={openUploads}><Upload size={14}/> Upload Center</button>
     </div>
    <section className="chat card"><div className="messages" ref={messagesRef}>{messages.map((m,i)=><div className={`message ${m.role}`} key={i}>
      <div className="avatar">{m.role==="assistant"?<Bot size={18}/>:<Users size={18}/>}</div><div><p>{m.content}</p>
      {m.role==="assistant"&&m.mode&&<div className={`mode-badge ${m.mode}`}>{m.mode==="openai"?"OpenAI reasoning":"Local data mode"}</div>}
      {m.route?.length>0&&<div className="agent-route">{m.route.map((agent,i)=><span key={`${agent}-${i}`}>{agent.replaceAll("_"," ")}</span>)}</div>}
      {m.requestId&&m.mode&&<div className="request-meta">Request {m.requestId.slice(0,8)} · {m.durationMs} ms</div>}
      {m.notice&&<div className="mode-notice">{m.notice}</div>}
      {m.citations?.length>0&&<details><summary>View {m.citations.length} sources</summary>{m.citations.map(c=><span key={c}>{c}</span>)}</details>}
      </div></div>)}
      {loading&&<div className="typing"><i/><i/><i/></div>}</div>
      <div className="composer"><button className="attach" onClick={openUploads} title="Attach PDF or Excel"><Paperclip size={17}/></button><input value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>e.key==="Enter"&&submit()} placeholder="Ask the multi-agent team about data or documents..."/>
        <button className="primary" onClick={()=>submit()}><Send size={17}/></button></div>
    </section><UploadCenter open={uploadsOpen} onClose={closeUploads} returnFocusRef={uploadTriggerRef} {...{role,projects,selectedProject,setSelectedProject,refreshProjects}}/></div>;
}

/** Root component responsible for shared provider data, theme, and navigation state. */
export default function App(){
  const [page,setPage]=useState("assistant"),[dark,setDark]=useState(()=>localStorage.theme==="dark");
  const [role,setRole]=useState("Project Manager"),[projects,setProjects]=useState([]),[loading,setLoading]=useState(true);
  const [collapsed,setCollapsed]=useState(false),[initialQuery,setInitialQuery]=useState("");
  // Theme preference is local to the browser and does not affect server data.
  useEffect(()=>{document.documentElement.dataset.theme=dark?"dark":"light";localStorage.theme=dark?"dark":"light"},[dark]);
  // Changing roles refetches data so contact masking is enforced by Python.
  async function refreshProjects(){setLoading(true);try{setProjects(await getProjects(roles[role]))}finally{setLoading(false)}}
  useEffect(()=>{refreshProjects()},[role]);
  function goToAssistant(q){setInitialQuery(q);setPage("assistant")}
  return <div className="app-shell"><Sidebar {...{page,setPage,collapsed,setCollapsed}}/><div className="main-shell">
    <Header {...{dark,setDark,role,setRole}}/><main className={loading?"loading":""}>
      {loading?<div className="loader"><i/></div>:<>
      {page==="dashboard"&&<Dashboard projects={projects} goToAssistant={goToAssistant}/>}
      {page==="projects"&&<ProjectExplorer projects={projects}/>}
      {page==="assistant"&&<Assistant role={role} projects={projects} initialQuery={initialQuery} clearInitial={()=>setInitialQuery("")} refreshProjects={refreshProjects}/>}
      </>}</main></div></div>;
}
