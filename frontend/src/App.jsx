import {useAssistantWorkflows, WorkflowMessages, WorkflowComposer, ChatUpload, isCreation} from "./AssistantWorkflows";
import AttachmentWorkspace from "./AttachmentWorkspace";
import { useEffect, useRef, useState } from "react";
import {
  Activity, Bell, BookOpen, Bot, BriefcaseBusiness, Building2,
  Check, ChevronDown, ChevronRight, CircleDollarSign, Clock3, LayoutDashboard, Menu,
  FileSpreadsheet, FileText, HardHat, Moon, Plus, ReceiptText, RotateCcw,
  Send, Sparkles, Sun, Trash2, TrendingUp, Upload, Users, Wrench, X,
} from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  askAgent, askAgentStream, clearFailedIngestionJob, confirmDocumentDate, createProjectImportPreview, createProjectPreview, retryDocumentIndex,
  decideChange, deleteDocument, deleteProject, getChangeRequest, getDocuments, getIngestionJob,
  getApprovals, getInvoicePivot, getNotifications, getPortfolioInvoices, getProjectSchedule,
  getPortfolioManpower, getProjectIngestionJobs, getProjects, getResourceAllocationConflicts,
  getResourceAllocationDetails, getResourceAllocationSummary, getResourceAllocationTrends,
  markAllNotificationsRead,
  markNotificationRead, portfolioTemplateUrl, updateProject, updateProjectImport,
  uploadPortfolioWorkbook, uploadProjectFile,
  getCurrentUser, login as loginUser, logout as logoutUser,
} from "./api";

import { getAuthClient, downloadTemplate } from "./auth";

const roles = {
  "Project Manager": "project_manager",
  "Planning Engineer": "planning_engineer",
  Admin: "admin",
};

/** Accessible reusable selector for roles and projects. */
function SmartSelect({ label, value, options, onChange, icon: Icon, className="", compact=false, disabled=false }) {
  const [open,setOpen]=useState(false),[activeIndex,setActiveIndex]=useState(0);
  const rootRef=useRef(null),triggerRef=useRef(null);
  const selectedIndex=Math.max(0,options.findIndex(option=>option.value===value));
  const selected=options[selectedIndex]||options[0];
  useEffect(()=>{
    if(!open)return;
    setActiveIndex(selectedIndex);
    const closeOutside=event=>{if(rootRef.current&&!rootRef.current.contains(event.target))setOpen(false)};
    const closeEscape=event=>{if(event.key==="Escape"){setOpen(false);triggerRef.current?.focus()}};
    document.addEventListener("pointerdown",closeOutside,true);document.addEventListener("keydown",closeEscape);
    return()=>{document.removeEventListener("pointerdown",closeOutside,true);document.removeEventListener("keydown",closeEscape)};
  },[open,selectedIndex]);
  function choose(option){onChange(option.value);setOpen(false);triggerRef.current?.focus()}
  function onKeyDown(event){
    if(["ArrowDown","ArrowUp","Home","End","Enter"," ","Escape"].includes(event.key))event.preventDefault();
    if(event.key==="Escape"){setOpen(false);return}
    if(event.key==="Enter"||event.key===" "){
      if(open)choose(options[activeIndex]);else setOpen(true);
      return;
    }
    if(event.key==="Home"){setOpen(true);setActiveIndex(0);return}
    if(event.key==="End"){setOpen(true);setActiveIndex(options.length-1);return}
    if(event.key==="ArrowDown"){setOpen(true);setActiveIndex(index=>(index+1)%options.length)}
    if(event.key==="ArrowUp"){setOpen(true);setActiveIndex(index=>(index-1+options.length)%options.length)}
  }
  return <div className={`smart-select ${className} ${compact?"compact":""}`} ref={rootRef}>
    {label&&!compact&&<span className="smart-select-label">{label}</span>}
    <button type="button" className="smart-select-trigger" ref={triggerRef} disabled={disabled}
      role="combobox" aria-label={label||"Select an option"} aria-haspopup="listbox" aria-expanded={open}
      aria-controls={open?`${className}-options`:undefined} aria-activedescendant={open?`${className}-option-${activeIndex}`:undefined}
      onClick={()=>setOpen(current=>!current)} onKeyDown={onKeyDown}>
      {Icon&&<Icon size={17}/>}<span className="smart-select-value"><b>{selected?.label}</b>{selected?.description&&<small>{selected.description}</small>}</span>
      <ChevronDown className="select-chevron" size={16}/>
    </button>
    {open&&<div className="smart-select-menu" id={`${className}-options`} role="listbox" aria-label={label||"Options"}>
      {options.map((option,index)=><button type="button" role="option" tabIndex={-1} aria-selected={option.value===value}
        id={`${className}-option-${index}`} className={`${option.value===value?"selected":""} ${activeIndex===index?"active":""}`}
        key={option.value||"all"} onMouseEnter={()=>setActiveIndex(index)} onClick={()=>choose(option)}>
        <span><b>{option.label}</b>{option.description&&<small>{option.description}</small>}</span>{option.value===value&&<Check size={15}/>}
      </button>)}
    </div>}
  </div>;
}

const nav = [
  ["assistant", "AI Assistant", Bot],
  ["dashboard", "Command Center", LayoutDashboard],
  ["projects", "Project Explorer", Building2],
];
const roleOptions = [
  {value:"Project Manager",label:"Project Manager"},
  {value:"Planning Engineer",label:"Planning Engineer"},
  {value:"Admin",label:"Admin"},
];

const money = (value) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
const metricNumber = (value) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(Number(value) || 0);
const metricMoney = (value) => money(Number(value) || 0);
function downloadResourceCsv(items) {
  const fields = ["employee_name", "employee_id", "designation", "department", "project_code", "capacity_hours", "planned_hours", "actual_hours", "billable_hours", "allocation_percent", "utilization_percent", "billing_value", "allocation_status", "last_updated"];
  const escape = value => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const csv = [fields.join(","), ...items.map(item => fields.map(field => escape(item[field])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `resource-allocation-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

const splitTableRow=(line)=>{
  const source=line.trim().replace(/^\|/,"").replace(/\|$/,"");
  const cells=[];let current="";let escaped=false;
  for(const character of source){
    if(escaped){current+=character;escaped=false;continue;}
    if(character==="\\"){escaped=true;continue;}
    if(character==="|"){cells.push(current.trim());current="";continue;}
    current+=character;
  }
  if(escaped)current+="\\";
  cells.push(current.trim());
  return cells;
};
const tableSeparator=(cells)=>cells.length>=2&&cells.every(cell=>/^:?-{3,}:?$/.test(cell));
const numericCell=(value)=>value==="—"||/^\s*[-+]?(?:[$€£]\s*)?[\d,.]+(?:\s*%)?\s*$/.test(value);
const InlineText=({content})=>String(content||"").split(/(\*\*[^*\n]+\*\*)/g).map((part,index)=>
  part.startsWith("**")&&part.endsWith("**")?<strong key={index}>{part.slice(2,-2)}</strong>:part);

/** Render safe bold text and strictly valid GitHub-style tables without injecting HTML. */
function AssistantText({ content }) {
  const lines=String(content||"").split(/\r?\n/);const blocks=[];let prose=[];
  const flush=()=>{if(prose.length){blocks.push({type:"prose",lines:prose});prose=[];}};
  for(let index=0;index<lines.length;){
    if(index+1<lines.length&&lines[index].includes("|")){
      const header=splitTableRow(lines[index]);const separator=splitTableRow(lines[index+1]);
      if(header.length===separator.length&&tableSeparator(separator)){
        const rows=[];let cursor=index+2;
        while(cursor<lines.length&&lines[cursor].includes("|")){
          const row=splitTableRow(lines[cursor]);
          if(row.length!==header.length)break;
          rows.push(row);cursor++;
        }
        if(rows.length){flush();blocks.push({type:"table",header,rows});index=cursor;continue;}
      }
    }
    prose.push(lines[index]);index++;
  }
  flush();
  return <div className="assistant-content">{blocks.map((block,index)=>{
    if(block.type==="table"){
      const numeric=block.header.map((_,column)=>block.rows.every(row=>numericCell(row[column])));
      return <div className="assistant-table-wrap" key={index}><table className="assistant-table">
        <thead><tr>{block.header.map((cell,column)=><th className={numeric[column]?"numeric":""} key={column}><InlineText content={cell}/></th>)}</tr></thead>
        <tbody>{block.rows.map((row,rowIndex)=><tr key={rowIndex}>{row.map((cell,column)=><td className={numeric[column]?"numeric":""} key={column}><InlineText content={cell}/></td>)}</tr>)}</tbody>
      </table></div>;
    }
    return <div className="assistant-prose" key={index}>{block.lines.map((line,lineIndex)=>{
      const trimmed=line.trim();
      if(!trimmed)return <span className="assistant-space" key={lineIndex}/>;
      if(trimmed.startsWith("### "))return <h4 key={lineIndex}><InlineText content={trimmed.slice(4)}/></h4>;
      if(trimmed.startsWith("## "))return <h3 key={lineIndex}><InlineText content={trimmed.slice(3)}/></h3>;
      if(/^[-*]\s/.test(trimmed))return <div className="assistant-bullet" key={lineIndex}><i/><p><InlineText content={trimmed.slice(2)}/></p></div>;
      if(/^\d+\.\s/.test(trimmed))return <div className="assistant-number" key={lineIndex}><b>{trimmed.match(/^\d+/)[0]}</b><p><InlineText content={trimmed.replace(/^\d+\.\s/,"")}/></p></div>;
      return <p key={lineIndex}><InlineText content={line}/></p>;
    })}</div>;
  })}</div>;
}

function LandingPage({ onLogin }) {
  return <div className="public-shell">
    <header className="public-nav">
      <div className="public-brand"><img src="/prosight-logo.svg" alt="ProSight AI"/><span>ProSight AI<small>Construction intelligence</small></span></div>
      <button className="public-login" onClick={onLogin}>Sign in <ChevronRight size={16}/></button>
    </header>
    <main className="landing-page">
      <section className="landing-hero">
        <div className="landing-copy"><span className="eyebrow"><Sparkles size={14}/> Project intelligence, grounded in your data</span>
          <h1>Build with a clearer view of what happens next.</h1>
          <p>ProSight AI brings project progress, manpower, schedules, documents, and commercial signals into one calm command center.</p>
          <button className="landing-cta" onClick={onLogin}>Open command center <ChevronRight size={17}/></button>
          <div className="landing-trust"><span><Check size={14}/> Evidence-backed answers</span><span><Check size={14}/> Approval-first updates</span><span><Check size={14}/> Role-aware access</span></div>
        </div>
        <div className="landing-visual"><div className="visual-glow"/><div className="hero-window"><div className="window-bar"><i/><i/><i/><span>Project command center</span></div><div className="window-content"><div className="mini-kpis"><b>18 <small>Active projects</small></b><b>92% <small>On schedule</small></b><b>$24.8M <small>Portfolio value</small></b></div><div className="mini-chart"><div className="chart-line"/><span>Progress signal</span></div><div className="mini-alert"><span><Activity size={14}/> Focus area</span><b>3 projects need attention</b></div></div></div></div>
      </section>
      <section className="landing-features"><div><span className="feature-icon"><Bot size={18}/></span><b>Ask your project data</b><p>Get direct answers with source context and citations.</p></div><div><span className="feature-icon"><FileSpreadsheet size={18}/></span><b>Turn sheets into insight</b><p>Review semantic imports before they touch the database.</p></div><div><span className="feature-icon"><ShieldCheckIcon/></span><b>Stay in control</b><p>Roles, approvals, and audit trails at every important step.</p></div></section>
    </main>
  </div>;
}

function ShieldCheckIcon(){ return <Check size={18}/>; }

function LoginPage({ onBack, onLoggedIn }) {
  const [supabase,setSupabase]=useState(true);
  useEffect(()=>{getAuthClient().then(client=>setSupabase(Boolean(client))).catch(err=>setError(err.message))},[]);
  const [username,setUsername]=useState(""),[password,setPassword]=useState(""),[error,setError]=useState(""),[loading,setLoading]=useState(false);
  async function submit(event){
    event.preventDefault();setError("");setLoading(true);
    try{onLoggedIn(await loginUser(username,password));}catch(err){setError(err.message);}finally{setLoading(false);}
  }
  return <div className="auth-shell"><div className="auth-panel"><button className="auth-back" onClick={onBack}><ChevronRight size={15} style={{transform:"rotate(180deg)"}}/> Back to home</button><div className="auth-logo"><img src="/prosight-logo.svg" alt="ProSight AI"/></div><span className="eyebrow">Secure project workspace</span><h1>Welcome back.</h1><p>Sign in to your ProSight command center.</p><form onSubmit={submit}><label>{supabase?"Email":"Username"}<input type={supabase?"email":"text"} autoComplete="username" value={username} onChange={event=>setUsername(event.target.value)} placeholder={supabase?"you@company.com":"Your username"} required/></label><label>Password<input autoComplete="current-password" type="password" value={password} onChange={event=>setPassword(event.target.value)} placeholder="Your password" required/></label>{error&&<div className="auth-error" role="alert">{error}</div>}<button className="landing-cta auth-submit" disabled={loading}>{loading?"Signing in…":"Sign in"}<ChevronRight size={17}/></button></form><small className="auth-note">Your role and project access are assigned by ProSight administration.</small></div><div className="auth-side"><span className="eyebrow"><Sparkles size={14}/> Trusted project intelligence</span><h2>One reliable view for every project decision.</h2><p>Keep documents, progress signals, schedules, and commercial actions connected—with a human approval step when it matters.</p></div></div>;
}

/** Render the health classification derived from project progress variance. */
function Status({ project }) {
  const risk = project.variance_pct <= -3;
  return <span className={`status ${risk ? "risk" : "success"}`}>{risk ? "At risk" : "On track"}</span>;
}

function Sidebar({ page, setPage, collapsed, setCollapsed, dark, setDark, role, refreshProjects, onActivityCleared, user, onLogout }) {
  return <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
    <div className="brand">
      <div className="brand-mark"><img src="/prosight-logo.svg" alt="ProSight AI construction intelligence"/></div>
      {!collapsed && <div><strong>ProSight AI</strong><small>Construction intelligence</small></div>}
    </div>
    <nav>{nav.map(([id, label, Icon]) =>
      <button key={id} className={page === id ? "active" : ""} onClick={() => setPage(id)}>
        <Icon size={19}/>{!collapsed && <span>{label}</span>}
      </button>)}
    </nav>
    <div className="sidebar-foot">
      <SidebarUtilities {...{dark,setDark,role,refreshProjects,onActivityCleared,collapsed,user,onLogout}}/>
      <button className="collapse" aria-label={collapsed?"Expand sidebar":"Collapse sidebar"} title={collapsed?"Expand sidebar":"Collapse sidebar"} onClick={() => setCollapsed(!collapsed)}>
        <Menu size={18}/>
      </button>
    </div>
  </aside>;
}

/** Role, notification, and theme utilities anchored in the sidebar. */
function SidebarUtilities({ dark, setDark, role, refreshProjects, onActivityCleared, collapsed, user, onLogout }) {
  const [open,setOpen]=useState(false),[notifications,setNotifications]=useState([]);
  const [unread,setUnread]=useState(0),[approvals,setApprovals]=useState([]);
  const [loading,setLoading]=useState(false),[error,setError]=useState("");
  const centerRef=useRef(null),roleKey=roles[role];
  async function refreshCenter(showLoading=false){
    if(showLoading)setLoading(true);
    try{
      const [notices,queue]=await Promise.all([
        getNotifications(roleKey,"unread"),
        roleKey==="admin"?getApprovals(roleKey):Promise.resolve({items:[]}),
      ]);
      setNotifications(notices.items);setUnread(notices.unread_count);
      setApprovals(queue.items);setError("");
    }catch(err){setError(err.message)}finally{if(showLoading)setLoading(false)}
  }
  useEffect(()=>{refreshCenter(true);const timer=setInterval(()=>refreshCenter(),20000);return()=>clearInterval(timer)},[roleKey]);
  useEffect(()=>{
    if(!open)return;
    const closeOutside=(event)=>{
      if(centerRef.current&&!centerRef.current.contains(event.target))setOpen(false);
    };
    const closeOnEscape=(event)=>{if(event.key==="Escape")setOpen(false)};
    document.addEventListener("pointerdown",closeOutside,true);
    document.addEventListener("keydown",closeOnEscape);
    return()=>{
      document.removeEventListener("pointerdown",closeOutside,true);
      document.removeEventListener("keydown",closeOnEscape);
    };
  },[open]);
  async function review(changeId,decision){
    try{await decideChange(changeId,decision,roleKey);await Promise.all([refreshCenter(),refreshProjects()])}
    catch(err){setError(err.message)}
  }
  async function read(item){
    try{
      await markNotificationRead(item.id,roleKey);
      setNotifications(items=>items.filter(notification=>notification.id!==item.id));
      setUnread(count=>Math.max(0,count-1));
      await onActivityCleared(item);
    }catch(err){setError(err.message)}
  }
  async function readAll(){
    try{await markAllNotificationsRead(roleKey);await refreshCenter()}catch(err){setError(err.message)}
  }
  return <div className="sidebar-utilities">
    <div className="sidebar-profile" title={user?.display_name}>
      <span className="profile-avatar"><Users size={16}/></span>
      {!collapsed&&<span><b>{user?.display_name||"Signed in"}</b><small>{String(user?.role||role).replaceAll("_"," ")}</small></span>}
    </div>
    <div className="utility-actions">
      <div className="notification-center" ref={centerRef}>
        <button className="icon-btn" aria-label="Notifications" aria-expanded={open}
          onClick={()=>{setOpen(value=>!value);if(!open)refreshCenter(true)}}>
          <Bell size={18}/>{unread>0&&<span className="notification-badge">{unread>99?"99+":unread}</span>}
        </button>
        {open&&<section className="notification-popover">
          <div className="notification-head"><div><b>Notifications</b><span>{unread} unread</span></div>
            {unread>0&&<button onClick={readAll}>Mark all read</button>}</div>
          {loading&&<p className="notification-state">Loading notifications…</p>}
          {!loading&&error&&<p className="notification-state error">{error}</p>}
          {!loading&&!error&&roleKey==="admin"&&<>
            <h3>Pending approvals <span>{approvals.length}</span></h3>
            {approvals.length===0&&<p className="notification-state">No pending approvals.</p>}
            {approvals.map(item=><article className="approval-item" key={item.id}>
              <div><b>{item.action.replaceAll("_"," ")}</b><span>{item.project_code} · {item.requested_by.replaceAll("_"," ")}</span></div>
              {["attachment_update","natural_project_create"].includes(item.action)?<a href={`/assistant?review=${encodeURIComponent(item.id)}`}>Review request in AI Assistant</a>:<div className="notification-actions"><button onClick={()=>alert(JSON.stringify(item.preview,null,2))}>Preview</button>
                <button className="approve" onClick={()=>review(item.id,"approve")}>Approve</button>
                <button className="reject" onClick={()=>review(item.id,"reject")}>Reject</button></div>}
            </article>)}
          </>}
          {!loading&&!error&&<><h3>Activity</h3>
            {notifications.length===0&&<p className="notification-state">No notifications yet.</p>}
            {notifications.map(item=><button className={`notification-item ${item.read_at?"":"unread"}`}
              key={item.id} onClick={()=>read(item)}>
              <b>{item.title}</b><span>{item.message}</span><small>{item.project_code}</small>
            </button>)}</>}
        </section>}
      </div>
      <button className="theme-switch" aria-label={`Switch to ${dark?"light":"dark"} mode`} title={collapsed?`${dark?"Light":"Dark"} mode`:undefined} onClick={() => setDark(!dark)}>
        {dark ? <Sun size={16}/> : <Moon size={16}/>}<span>{dark ? "Light" : "Dark"}</span>
      </button>
      <button className="sidebar-logout" onClick={onLogout}><X size={15}/>{!collapsed&&<span>Sign out</span>}</button>
    </div>
  </div>;
}

/** Reusable portfolio metric card. */
function Kpi({ icon: Icon, label, value, detail, tone }) {
  return <article className="kpi card">
    <div className={`kpi-icon ${tone}`}><Icon size={20}/></div>
    <div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
  </article>;
}

/** Executive command center assembled from authorized project records. */
function Dashboard({ projects, role, goToAssistant, onOpenResourceAllocation }) {
  const [scheduleRange,setScheduleRange]=useState(6),[rangeOpen,setRangeOpen]=useState(false);
  const [resourceSummary,setResourceSummary]=useState(null),[resourceLoading,setResourceLoading]=useState(true);
  const rangeRef=useRef(null);
  const roleKey=roles[role];
  useEffect(()=>{
    let active=true;
    setResourceLoading(true);
    getResourceAllocationSummary(roleKey).then(result=>{if(active)setResourceSummary(result)}).catch(()=>{if(active)setResourceSummary(null)}).finally(()=>{if(active)setResourceLoading(false)});
    return()=>{active=false};
  },[roleKey]);
  useEffect(()=>{
    if(!rangeOpen)return;
    const closeOutside=event=>{if(rangeRef.current&&!rangeRef.current.contains(event.target))setRangeOpen(false)};
    const closeEscape=event=>{if(event.key==="Escape")setRangeOpen(false)};
    document.addEventListener("pointerdown",closeOutside,true);document.addEventListener("keydown",closeEscape);
    return()=>{document.removeEventListener("pointerdown",closeOutside,true);document.removeEventListener("keydown",closeEscape)};
  },[rangeOpen]);
  const active = projects.filter((p) => p.status === "active");
  const delayed = active.filter((p) => p.delay_days > 0);
  const avg = active.reduce((sum, p) => sum + p.actual_progress, 0) / (active.length || 1);
  const progress = active.map((p) => ({
    name: p.name.split(" ").slice(0, 2).join(" "),
    Baseline: !p.progress_fields_provided||p.progress_fields_provided.includes("baseline_progress")?p.baseline_progress:null, Revised: !p.progress_fields_provided||p.progress_fields_provided.includes("revised_progress")?p.revised_progress:null, Actual: p.actual_progress,
  }));
  // The prototype dataset contains snapshots rather than full history, so this
  // illustrative trend should be replaced by progress_snapshots in production.
  const trend = [
    { month: "Nov", Revised: 22, Actual: 20 }, { month: "Dec", Revised: 28, Actual: 25 },
    { month: "Jan", Revised: 34, Actual: 31 },
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
        <CardTitle title="Project health"/>
        <div className="health-head"><span>Project</span><span>Progress</span><span>Status</span></div>
        {active.map((p) => <div className="health-row" key={p.code}>
          <div><strong>{p.name}</strong><small>{p.code}</small></div>
          <div className="progress-wrap"><div className="progress"><i style={{width:`${p.actual_progress}%`}}/></div><b>{p.actual_progress}%</b></div>
          <Status project={p}/>
        </div>)}
      </article>
      <article className="card chart-panel">
        <div className="card-title"><h2>Schedule performance</h2><div className="range-selector" ref={rangeRef}>
          <button className="range-trigger" aria-haspopup="true" aria-expanded={rangeOpen} onClick={()=>setRangeOpen(open=>!open)}>
            Last {scheduleRange} months <ChevronDown size={14}/>
          </button>
          {rangeOpen&&<div className="range-popover" role="menu" aria-label="Schedule performance period">
            {[3,6,9].map(months=><button role="menuitemradio" aria-checked={scheduleRange===months} className={scheduleRange===months?"selected":""}
              key={months} onClick={()=>{setScheduleRange(months);setRangeOpen(false)}}>
              <span>{months} months</span>{scheduleRange===months&&<Check size={14}/>}
            </button>)}
          </div>}
        </div></div>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={trend.slice(-scheduleRange)}><CartesianGrid strokeDasharray="3 3" vertical={false}/>
            <XAxis dataKey="month"/><YAxis domain={[0, 100]} unit="%"/><Tooltip/>
            <Line dataKey="Revised" stroke="var(--chart-secondary)" strokeWidth={3} dot={false}/>
            <Line dataKey="Actual" stroke="var(--chart-primary)" strokeWidth={3} dot={{r:3}}/>
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
          <Bar dataKey="Baseline" fill="var(--chart-muted)" radius={4}/><Bar dataKey="Revised" fill="var(--chart-secondary)" radius={4}/><Bar dataKey="Actual" fill="var(--chart-primary)" radius={4}/>
        </BarChart></ResponsiveContainer>
      </article>
      <article className="card"><CardTitle title="Upcoming milestones"/>
        <div className="timeline">{active.flatMap((p)=>p.milestones.filter((m)=>m.status!=="complete").slice(0,2).map((m)=>({...m, project:p.name}))).map((m,i)=>
          <div className="timeline-item" key={`${m.name}${i}`}><i/><div><strong>{m.name}</strong><small>{m.project}</small></div><span>{m.status.replace("due ","")}</span></div>)}</div>
      </article>
    </section>
    <section className="command-center-feature-grid">
      <button className="resource-feature-card card" type="button" onClick={onOpenResourceAllocation}>
        <div className="resource-feature-head"><span className="feature-icon"><Users size={18}/></span><span className="feature-arrow"><ChevronRight size={17}/></span></div>
        <div className="resource-feature-copy"><span className="eyebrow">Operational controls</span><h2>Manpower Allocation</h2><p>Review staffing capacity, allocation pressure, and billing hours.</p></div>
        {resourceLoading?<div className="resource-feature-loading"><i/><i/><i/></div>:resourceSummary?.totals?<div className="resource-feature-metrics">
          <div><b>{metricNumber(resourceSummary.totals.total_manpower)}</b><span>people</span></div>
          <div><b>{metricNumber(resourceSummary.totals.utilization_percent)}%</b><span>utilization</span></div>
          <div><b>{metricNumber(resourceSummary.totals.planned_hours)}</b><span>planned hours</span></div>
          <div><b>{metricNumber(resourceSummary.totals.actual_hours)}</b><span>actual hours</span></div>
        </div>:<div className="resource-feature-empty">No allocation data yet. Open to import or review resources.</div>}
        <span className="resource-feature-link">Open dashboard <ChevronRight size={15}/></span>
      </button>
    </section>
  </>;
}

/** Server-aggregated manpower, utilization, billing, and exception dashboard. */
function ResourceAllocationDashboard({ projects, role, onBack }) {
  const roleKey=roles[role];
  const [filters,setFilters]=useState({project_code:"",date_from:"",date_to:"",department:"",designation:"",employee:"",allocation_status:"",billable_status:""});
  const [summary,setSummary]=useState(null),[trends,setTrends]=useState([]),[conflicts,setConflicts]=useState([]),[details,setDetails]=useState({items:[],total:0}),[detailOffset,setDetailOffset]=useState(0),[loading,setLoading]=useState(true),[error,setError]=useState("");
  const updateFilter=(key,value)=>{setDetailOffset(0);setFilters(current=>({...current,[key]:value}))};
  useEffect(()=>{
    let active=true;
    setLoading(true);setError("");
    Promise.all([
      getResourceAllocationSummary(roleKey,filters),
      getResourceAllocationTrends(roleKey,filters),
      getResourceAllocationConflicts(roleKey,filters),
      getResourceAllocationDetails(roleKey,filters,100,detailOffset),
    ]).then(([nextSummary,nextTrends,nextConflicts,nextDetails])=>{
      if(!active)return;
      setSummary(nextSummary);setTrends(nextTrends);setConflicts(nextConflicts);setDetails(nextDetails);
    }).catch(nextError=>{if(active)setError(nextError.message||"Could not load resource allocation dashboard")})
      .finally(()=>{if(active)setLoading(false)});
    return()=>{active=false};
  },[roleKey,filters,detailOffset]);
  const totals=summary?.totals||{};
  const projectOptions=projects.map(project=>({value:project.code,label:project.code}));
  const departmentOptions=[...new Set((summary?.by_department||[]).map(item=>item.name).filter(name=>name!=="Unassigned"))];
  const pieColors=["#2563eb","#06b6d4","#10b981","#8b5cf6","#f59e0b","#ef4444"];
  return <>
    <PageTitle eyebrow="Operational controls" title="Manpower Allocation" subtitle="A live view of staffing capacity, allocation pressure, and billing hours.">
      <button className="secondary dashboard-back" type="button" onClick={onBack}><ChevronRight size={15} style={{transform:"rotate(180deg)"}}/> Back to Command Center</button>
    </PageTitle>
    <section className="resource-filter-bar card">
      <div><span>Project</span><select value={filters.project_code} onChange={event=>updateFilter("project_code",event.target.value)}><option value="">All authorized projects</option>{projectOptions.map(option=><option value={option.value} key={option.value}>{option.label}</option>)}</select></div>
      <div><span>From</span><input type="date" value={filters.date_from} onChange={event=>updateFilter("date_from",event.target.value)}/></div>
      <div><span>To</span><input type="date" value={filters.date_to} onChange={event=>updateFilter("date_to",event.target.value)}/></div>
      <div><span>Department</span><select value={filters.department} onChange={event=>updateFilter("department",event.target.value)}><option value="">All departments</option>{departmentOptions.map(option=><option value={option} key={option}>{option}</option>)}</select></div>
      <div><span>Designation</span><input value={filters.designation} onChange={event=>updateFilter("designation",event.target.value)} placeholder="e.g. Engineer"/></div>
      <div><span>Employee</span><input value={filters.employee} onChange={event=>updateFilter("employee",event.target.value)} placeholder="Name or ID"/></div>
      <div><span>Allocation</span><select value={filters.allocation_status} onChange={event=>updateFilter("allocation_status",event.target.value)}><option value="">All allocation states</option><option value="overallocated">Over-allocated</option><option value="balanced">Balanced</option><option value="underallocated">Under-allocated</option></select></div>
      <div><span>Billing</span><select value={filters.billable_status} onChange={event=>updateFilter("billable_status",event.target.value)}><option value="">All billing states</option><option value="billable">Billable</option><option value="non_billable">Non-billable</option></select></div>
      <button className="secondary resource-clear" type="button" onClick={()=>{setDetailOffset(0);setFilters({project_code:"",date_from:"",date_to:"",department:"",designation:"",employee:"",allocation_status:"",billable_status:""})}}>Clear filters</button>
    </section>
    {loading&&<div className="resource-loading card"><span className="loading-spinner"/>Loading resource allocation…</div>}
    {!loading&&error&&<div className="resource-error card">{error}</div>}
    {!loading&&!error&&<>
      <section className="kpi-grid resource-kpi-grid">
        <Kpi icon={Users} label="Total manpower" value={metricNumber(totals.total_manpower)} detail="Authorized resource records" tone="blue"/>
        <Kpi icon={BriefcaseBusiness} label="Active projects" value={metricNumber(totals.active_projects)} detail="Projects in current view" tone="purple"/>
        <Kpi icon={Clock3} label="Planned hours" value={metricNumber(totals.planned_hours)} detail="Selected period" tone="blue"/>
        <Kpi icon={Activity} label="Actual hours" value={metricNumber(totals.actual_hours)} detail="Reported hours" tone="green"/>
        <Kpi icon={HardHat} label="Billable hours" value={metricNumber(totals.billable_hours)} detail="Approved billing input" tone="green"/>
        <Kpi icon={TrendingUp} label="Utilization" value={`${metricNumber(totals.utilization_percent)}%`} detail="Actual ÷ capacity" tone="purple"/>
        <Kpi icon={CircleDollarSign} label="Billing value" value={metricMoney(totals.billing_value)} detail="Billable hours × rate" tone="green"/>
        <Kpi icon={Wrench} label="Over-allocation" value={metricNumber(totals.over_allocation_count)} detail="Employees above 100%" tone="red"/>
      </section>
      <section className="dashboard-grid resource-chart-grid">
        <article className="card chart-panel"><CardTitle title="Hours by project"/><ResponsiveContainer width="100%" height={270}><BarChart data={summary?.by_project||[]}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="name" tick={{fontSize:10}}/><YAxis/><Tooltip/><Legend/><Bar dataKey="planned_hours" name="Planned" fill="var(--chart-secondary)" radius={4}/><Bar dataKey="actual_hours" name="Actual" fill="var(--chart-primary)" radius={4}/></BarChart></ResponsiveContainer></article>
        <article className="card chart-panel"><CardTitle title="Capacity versus demand"/><ResponsiveContainer width="100%" height={270}><BarChart data={summary?.by_project||[]}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="name" tick={{fontSize:10}}/><YAxis/><Tooltip/><Legend/><Bar dataKey="capacity_hours" name="Capacity" fill="#94a3b8" radius={4}/><Bar dataKey="planned_hours" name="Demand" fill="#f59e0b" radius={4}/></BarChart></ResponsiveContainer></article>
        <article className="card chart-panel"><CardTitle title="Department allocation"/><ResponsiveContainer width="100%" height={270}><PieChart><Pie data={summary?.by_department||[]} dataKey="headcount" nameKey="name" innerRadius={60} outerRadius={94} paddingAngle={2}>{(summary?.by_department||[]).map((item,index)=><Cell fill={pieColors[index%pieColors.length]} key={item.name}/>)}</Pie><Tooltip/><Legend/></PieChart></ResponsiveContainer></article>
      </section>
      <section className="lower-grid resource-lower-grid">
        <article className="card chart-panel"><CardTitle title="Utilization and billing trend"/><ResponsiveContainer width="100%" height={270}><LineChart data={trends}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="period" tick={{fontSize:10}}/><YAxis yAxisId="hours"/><YAxis yAxisId="billing" orientation="right"/><YAxis yAxisId="percent" orientation="right" domain={[0,100]} hide/><Tooltip/><Legend/><Line yAxisId="hours" dataKey="planned_hours" name="Planned hours" stroke="var(--chart-secondary)" strokeWidth={2}/><Line yAxisId="hours" dataKey="actual_hours" name="Actual hours" stroke="var(--chart-primary)" strokeWidth={3}/><Line yAxisId="hours" dataKey="billable_hours" name="Billable hours" stroke="#8b5cf6" strokeWidth={2}/><Line yAxisId="billing" dataKey="billing_value" name="Billing value" stroke="#10b981" strokeWidth={2}/><Line yAxisId="percent" dataKey="utilization_percent" name="Utilization %" stroke="#f59e0b" strokeWidth={2} strokeDasharray="4 3"/></LineChart></ResponsiveContainer></article>
        <article className="card resource-conflict-card"><CardTitle title="Resource exceptions"/><div className="resource-exception-summary"><span><b>{conflicts.length}</b> exceptions</span><span><b>{metricNumber(totals.under_allocation_count)}</b> under-allocated</span></div>{conflicts.slice(0,8).map(item=><div className="resource-exception" key={`${item.employee_id}-${item.project_code}`}><div><b>{item.employee_name||item.employee_id}</b><small>{item.project_code||"Unassigned"} · {item.designation||"No designation"}</small></div><span>{item.reasons.join(" · ")}</span></div>)}{conflicts.length===0&&<p className="empty">No allocation exceptions in this view.</p>}</article>
      </section>
      <article className="card table-card resource-detail-card"><div className="card-title"><h2>Resource detail</h2><div className="table-actions"><span className="table-count">{details.total} records</span><button className="secondary" type="button" disabled={!details.items.length} onClick={()=>downloadResourceCsv(details.items)}><FileSpreadsheet size={13}/> Export visible</button></div></div><div className="resource-table-wrap"><table><thead><tr><th>Employee</th><th>Designation</th><th>Department</th><th>Project</th><th>Capacity</th><th>Planned</th><th>Actual</th><th>Billable</th><th>Allocation</th><th>Utilization</th><th>Billing value</th><th>Status</th><th>Last updated</th></tr></thead><tbody>{details.items.map(item=><tr key={`${item.employee_id}-${item.project_code}-${item.last_updated}`}><td><b>{item.employee_name||item.employee_id||"—"}</b><small>{item.employee_id||"—"}</small></td><td>{item.designation||"—"}</td><td>{item.department||"—"}</td><td>{item.project_code||"Unassigned"}</td><td>{metricNumber(item.capacity_hours)}</td><td>{metricNumber(item.planned_hours)}</td><td>{metricNumber(item.actual_hours)}</td><td>{metricNumber(item.billable_hours)}</td><td>{metricNumber(item.allocation_percent)}%</td><td>{metricNumber(item.utilization_percent)}%</td><td>{metricMoney(item.billing_value)}</td><td><span className={`resource-status ${item.allocation_status}`}>{String(item.allocation_status||item.status||"unknown").replaceAll("_"," ")}</span></td><td>{item.last_updated?String(item.last_updated).slice(0,10):"—"}</td></tr>)}</tbody></table></div>{details.items.length===0&&<p className="empty">No manpower records match the selected filters.</p>}<div className="resource-pagination"><button className="secondary" type="button" disabled={detailOffset===0||loading} onClick={()=>setDetailOffset(Math.max(0,detailOffset-100))}>Previous</button><span>Showing {details.total?detailOffset+1:0}–{Math.min(detailOffset+details.items.length,details.total)} of {details.total}</span><button className="secondary" type="button" disabled={loading||detailOffset+details.items.length>=details.total} onClick={()=>setDetailOffset(detailOffset+100)}>Next</button></div></article>
    </>}
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
function ProjectExplorer({ projects, role, refreshProjects, dataRevision, selectedProject, setSelectedProject, onProjectDeleted }) {
  const selected=selectedProject;
  const setSelected=setSelectedProject;
  const [tab, setTab] = useState("overview");
  const [createOpen,setCreateOpen]=useState(false);
  const deleteDialogRef=useRef(null);
  const [deleteTarget,setDeleteTarget]=useState(null),[deleteCode,setDeleteCode]=useState("");
  const [deleting,setDeleting]=useState(false),[deleteError,setDeleteError]=useState("");
  useEffect(()=>{if(deleteTarget&&!deleteDialogRef.current?.open)deleteDialogRef.current?.showModal()},[deleteTarget]);
  async function confirmDelete(event){
    event.preventDefault();
    if(!deleteTarget || deleteCode!==deleteTarget.code || deleting)return;
    setDeleting(true);setDeleteError("");
    try{await deleteProject(deleteTarget.code,deleteCode);onProjectDeleted(deleteTarget.code);setDeleteTarget(null);await refreshProjects();}
    catch(error){setDeleteError(error.message)}finally{setDeleting(false)}
  }

  const [portfolioRevision,setPortfolioRevision]=useState(0);
  const [portfolioManpower,setPortfolioManpower]=useState([]),[invoices,setInvoices]=useState([]),[pivot,setPivot]=useState([]),[schedule,setSchedule]=useState([]);
  const project = projects.find((p)=>p.code===selected) || projects[0];
  const roleKey=roles[role];
  const projectOptions=projects.map(item=>({value:item.code,label:item.code,description:item.name}));
  useEffect(()=>{
    if(projects.length&&!projects.some(item=>item.code===selected))setSelected(projects[0].code);
  },[projects,selected]);
  useEffect(()=>{
    if(!project)return;
    if(tab==="portfolio manpower")getPortfolioManpower(roleKey,project.code).then(setPortfolioManpower).catch(()=>setPortfolioManpower([]));
    if(tab==="project invoices")getPortfolioInvoices(roleKey,project.code).then(setInvoices).catch(()=>setInvoices([]));
    if(tab==="invoice pivot")getInvoicePivot(roleKey).then(setPivot).catch(()=>setPivot([]));
    if(tab==="project schedule")getProjectSchedule(roleKey,project.code).then(setSchedule).catch(()=>setSchedule([]));
  },[tab,project?.code,roleKey,portfolioRevision]);
  if (!project) return <><PageTitle eyebrow="Project controls" title="Project Explorer" subtitle="No projects yet."/>{["admin","project_manager"].includes(roleKey)&&<button className="primary" onClick={()=>setCreateOpen(true)}>Create Project</button>}<UploadCenter open={createOpen} onClose={()=>setCreateOpen(false)} role={role} projects={projects} selectedProject={selected} setSelectedProject={setSelected} refreshProjects={refreshProjects} workspaceMode="create"/></>;
  const manpower = project.manpower.map((m)=>({name:m.designation,value:m.count}));
  return <>
    <PageTitle eyebrow="Project controls" title="Project Explorer" subtitle="Inspect schedules, teams, site operations, and supporting evidence.">
      <div className="project-title-actions">
        <SmartSelect label="Selected project" value={project.code} options={projectOptions} onChange={setSelected}
          icon={Building2} className="explorer-project-select"/>
        <button className="primary create-project-action" onClick={()=>setTab("data imports")}>
          <FileSpreadsheet size={16}/> Data Import &amp; Review
        </button>
        {roleKey==="admin"&&<button className="secondary delete-project-action" onClick={()=>{setDeleteTarget({code:project.code,name:project.name});setDeleteCode("");setDeleteError("")}}>Delete Project</button>}
        {["project_manager","admin"].includes(roleKey)&&<button className="primary create-project-action" onClick={()=>setCreateOpen(true)}><Plus size={16}/> Create Project</button>}
      </div>
    </PageTitle>
    {deleteTarget&&<dialog ref={deleteDialogRef} className="card project-delete-dialog" aria-labelledby="delete-project-title" onCancel={event=>{if(deleting)event.preventDefault();else setDeleteTarget(null)}}>
      <h2 id="delete-project-title">Delete {deleteTarget.code}?</h2>
      <p>{deleteTarget.name}</p><p>This permanently removes the project, its records, approvals, uploads, and RAG evidence. This cannot be undone.</p>
      <p>Workbooks containing this project are also removed, including shared source files. Other projects’ imported records remain.</p>
      <form onSubmit={confirmDelete}><label htmlFor="delete-project-code">Type {deleteTarget.code} to confirm</label><input id="delete-project-code" autoFocus autoComplete="off" value={deleteCode} disabled={deleting} onChange={event=>setDeleteCode(event.target.value)}/>
      {deleteError&&<p role="alert" className="delete-project-error">{deleteError}</p>}
      <div className="project-title-actions"><button type="button" className="secondary" disabled={deleting} onClick={()=>setDeleteTarget(null)}>Cancel</button><button type="submit" className="primary delete-project-action" disabled={deleting||deleteCode!==deleteTarget.code}>{deleting?"Deleting…":"Permanently delete project"}</button></div></form>
    </dialog>}
    <section className="project-hero card">
      <div><span className="status success">{project.status}</span><h2>{project.name}</h2><p>{project.location} · {project.client}</p></div>
      <div className="hero-metrics"><div><span>Contract value</span><strong>{money(project.contract_value_usd)}</strong></div>
        {project.status==="active"&&<><div><span>Completed progress</span><strong>{project.actual_progress}%</strong></div>
        <div><span>Variance</span><strong className={project.variance_pct<0?"negative":""}>{project.status!=="active"||project.variance_available===false?"Not applicable":`${project.variance_pct>0?"+":""}${project.variance_pct} pp`}</strong></div>
        <div><span>Delay</span><strong>{project.delay_days} days</strong></div></>}</div>
    </section>
    <div className="tabs">{["overview","contacts","operations","milestones","project schedule","portfolio manpower","project invoices","invoice pivot","data imports","update project"].map((item)=>
      <button className={tab===item?"active":""} onClick={()=>setTab(item)} key={item}>{item}</button>)}</div>
    {tab==="overview" && <section className="lower-grid">
      <article className="card"><CardTitle title={project.status==="active"?"Schedule & progress":"Project dates"}/><div className="date-grid">
        <div><span>{project.status==="completed"?"Start date":"Planned start"}</span><strong>{project.planned_start}</strong></div>
        <div><span>{project.status==="completed"?"End date":"Planned finish"}</span><strong>{project.planned_finish}</strong></div>
        {project.status==="active"&&<div><span>Revised finish</span><strong>{project.revised_finish||"Not set"}</strong></div>}</div>
        {project.status==="active"&&<ResponsiveContainer width="100%" height={230}><BarChart data={[
          {name:"Baseline",key:"baseline_progress",value:project.baseline_progress},{name:"Revised",key:"revised_progress",value:project.revised_progress},{name:"Actual",key:"actual_progress",value:project.actual_progress}].filter(item=>!project.progress_fields_provided||project.progress_fields_provided.includes(item.key))}>
          <CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="name"/><YAxis domain={[0,100]}/><Tooltip/>
          <Bar dataKey="value" radius={[7,7,0,0]}>{["#94a3b8","#60a5fa","#2563eb"].map(c=><Cell fill={c} key={c}/>)}</Bar>
        </BarChart></ResponsiveContainer>}</article>
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
    {tab==="project schedule"&&<article className="card table-card portfolio-table"><table><thead><tr>
      <th>Activity ID</th><th>Activity Name</th><th>Start</th><th>Finish</th><th>Original Duration</th>
    </tr></thead><tbody>{schedule.map(item=><tr key={item.activity_id}>
      <td><b>{item.activity_id}</b></td><td>{item.activity_name}</td><td>{item.start}</td><td>{item.finish}</td><td>{item.original_duration}</td>
    </tr>)}</tbody></table>{schedule.length===0&&<p className="empty">No detailed project schedule has been imported.</p>}</article>}
    {tab==="portfolio manpower"&&<article className="card table-card portfolio-table"><table><thead><tr>
      <th>EMP Code</th><th>Name</th><th>Designation</th><th>Department</th><th>Category</th><th>Location</th><th>Allocation</th><th>Status</th>
    </tr></thead><tbody>{portfolioManpower.map(item=><tr key={item.emp_code}>
      <td>{item.emp_code}</td><td><b>{item.name}</b></td><td>{item.designation}</td><td>{item.department}</td>
      <td>{item.category}</td><td>{item.current_location}</td><td>{item.allocation??"—"}</td><td>{item.status}</td>
    </tr>)}</tbody></table>{portfolioManpower.length===0&&<p className="empty">No portfolio manpower imported for this project.</p>}</article>}
    {tab==="project invoices"&&<article className="card table-card portfolio-table"><table><thead><tr>
      <th>Draft invoice</th><th>Job No</th><th>Status</th><th>Level</th><th>Approval</th><th>Payment</th><th>USD value</th><th>Risk</th><th>Live aging</th>
    </tr></thead><tbody>{invoices.map(item=><tr key={`${item.job_number}-${item.draft_invoice_number}`}>
      <td><b>{item.draft_invoice_number}</b></td><td>{item.job_number}</td><td>{item.status}</td><td>{item.levels}</td>
      <td>{item.approval_status}</td><td>{item.payment_status}</td><td>{money(item.invoice_value_usd||0)}</td>
      <td>{item.risk_profile}</td><td>{item.live_aging_days??"—"}</td>
    </tr>)}</tbody></table>{invoices.length===0&&<p className="empty">No invoices imported for this project.</p>}</article>}
    {tab==="invoice pivot"&&<InvoicePivot rows={pivot} projects={projects}/>}
    {tab==="data imports"&&<AttachmentWorkspace projects={projects} role={roleKey} selectedProject={project.code}
      onChanged={async()=>{setPortfolioRevision(value=>value+1);await refreshProjects()}}/>}
    <div hidden={tab!=="update project"}><UploadCenter
      open embedded workspaceMode="update" role={role} projects={projects} selectedProject={project.code}
      setSelectedProject={setSelected} refreshProjects={refreshProjects} dataRevision={dataRevision}
    /></div>
    <UploadCenter
      open={createOpen} workspaceMode="create" onClose={()=>setCreateOpen(false)}
      role={role} projects={projects} selectedProject={project.code}
      setSelectedProject={setSelected} refreshProjects={refreshProjects}
    />
  </>;
}

function InvoicePivot({rows,projects}){
  const codes=[...new Set(rows.flatMap(row=>Object.keys(row.projects||{})))];
  const label=code=>projects.find(project=>project.code===code)?.name||code;
  return <article className="card table-card portfolio-table"><table><thead><tr>
    <th>Levels</th><th>Invoice status</th>{codes.map(code=><th key={code}>{label(code)}</th>)}<th>Grand Total</th>
  </tr></thead><tbody>{rows.map((row,index)=><tr key={`${row.levels}-${row.status}-${index}`}>
    <td>{row.levels}</td><td>{row.status}</td>{codes.map(code=><td key={code}>{money(row.projects?.[code]||0)}</td>)}
    <td><b>{money(row.grand_total||0)}</b></td>
  </tr>)}</tbody></table>{rows.length===0&&<p className="empty">No invoice pivot data is available.</p>}</article>;
}

function PortfolioImport({open,onClose,roleKey,onImported,projects,selectedProject}){
  const [feedback,setFeedback]=useState(null),[loading,setLoading]=useState(false);
  const [dataset,setDataset]=useState("manpower"),[selectedFile,setSelectedFile]=useState("");
  const [scheduleProject,setScheduleProject]=useState(selectedProject||"");
  const [activeDataset,setActiveDataset]=useState(null);
  useEffect(()=>{if(open){setFeedback(null);setSelectedFile("");setScheduleProject(selectedProject||projects[0]?.code||"")}},[open,selectedProject]);
  useEffect(()=>{
    if(!open)return;
    const close=event=>{if(event.key==="Escape"&&!loading)onClose()};
    window.addEventListener("keydown",close);return()=>window.removeEventListener("keydown",close);
  },[open,loading,onClose]);
  async function upload(file,dataset){
    if(!file)return;
    setSelectedFile(file.name);
    setLoading(true);setActiveDataset(dataset);setFeedback(null);
    try{const imported=await uploadPortfolioWorkbook(file,roleKey,dataset,dataset==="schedule"?scheduleProject:"");setFeedback({type:"success",result:imported});onImported()}
    catch(uploadError){setFeedback({type:"error",message:uploadError.message})}
    finally{setLoading(false);setActiveDataset(null)}
  }
  const options=[
    {dataset:"manpower",title:"Manpower",description:"Employee allocation and project assignment data"},
    {dataset:"invoices",title:"Project Invoices",description:"Invoice, payment, aging and risk data"},
    {dataset:"schedule",title:"Project Schedule",description:"Project activities, dates and original durations"},
  ];
  const item=options.find(option=>option.dataset===dataset)||options[0];
  const datasetOptions=options.map(option=>({value:option.dataset,label:option.title,description:option.description}));
  function selectDataset(value){setDataset(value);setFeedback(null);setSelectedFile("")}
  if(!open)return null;
  return <div className="upload-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!loading)onClose()}}>
    <aside className={`upload-center portfolio-import ${loading?"is-loading":""}`} role="dialog" aria-modal="true" aria-label="Portfolio Data Import">
      <div className="upload-head"><div><span>PORTFOLIO CONTROLS</span><h2>Portfolio Data Import</h2></div>
        <button disabled={loading} onClick={onClose}><X/></button></div>
      <p className="portfolio-help">Choose one portfolio dataset, download its template, then upload the completed XLSX workbook.</p>
      <SmartSelect className="portfolio-dataset-smart" label="Data to import" Icon={FileSpreadsheet}
        value={dataset} options={datasetOptions} disabled={loading} onChange={selectDataset}/>
      <div className="portfolio-upload-grid"><section className={`portfolio-upload-option ${activeDataset===item.dataset?"active":""}`}>
        <div className="portfolio-card-heading"><i><FileSpreadsheet size={20}/></i><div><h3>{item.title}</h3><p>{item.description}</p></div></div>
        <a className="template-download" href={portfolioTemplateUrl(roleKey,item.dataset)} aria-disabled={loading}
          tabIndex={loading?-1:0} onClick={async event=>{event.preventDefault();if(!loading){try{await downloadTemplate(portfolioTemplateUrl(roleKey,item.dataset))}catch(error){setFeedback({type:"error",message:error.message})}}}}><FileSpreadsheet size={17}/><span>Download {item.title} template</span></a>
        <div className="upload-divider"><span>Then upload completed workbook</span></div>
        {item.dataset==="schedule"&&<label className="schedule-project-select"><span>Target project</span><select value={scheduleProject} disabled={loading} onChange={event=>setScheduleProject(event.target.value)}>
          {projects.map(project=><option value={project.code} key={project.code}>{project.code} — {project.name}</option>)}</select></label>}
        <label className="drop-zone"><Upload size={25}/><b>{activeDataset===item.dataset?"Validating and importing…":`Upload ${item.title} XLSX`}</b>
          <span>XLSX only · Maximum file size 20 MB</span><input className="accessible-file-input" disabled={loading} type="file" accept=".xlsx" onChange={event=>upload(event.target.files[0],item.dataset)}/>
          <small className="selected-upload-name">{selectedFile||"No file selected"}</small></label>
        {feedback?.type==="error"&&<div className="portfolio-card-feedback error"><b>Import failed</b><span>{feedback.message}</span></div>}
        {feedback?.type==="success"&&<div className="portfolio-card-feedback success"><b>Import completed</b><span>{
          `${feedback.result.summary?.[item.dataset]?.inserted||0} inserted, ${feedback.result.summary?.[item.dataset]?.updated||0} updated`
        }</span></div>}
      </section></div>
      {loading&&<progress className="portfolio-progress" max="100"/>}
    </aside>
  </div>;
}

/** Project-scoped upload, ingestion status, review, and document management drawer. */
function UploadCenter({ open, onClose=()=>{}, role, projects, selectedProject, setSelectedProject, refreshProjects, returnFocusRef, embedded=false, workspaceMode="update", dataRevision=0 }) {
  const [documents,setDocuments]=useState([]),[jobs,setJobs]=useState([]),[error,setError]=useState("");
  const [clearingJobs,setClearingJobs]=useState([]),[jobClearErrors,setJobClearErrors]=useState({});
  const [projectChange,setProjectChange]=useState(null);
  const [dateEdits,setDateEdits]=useState({});
  const [draft,setDraft]=useState({
    code:"",name:"",status:"future",client:"",location:"",contract_value_usd:0,
    planned_start:"",planned_finish:"",revised_finish:"",reporting_date:new Date().toISOString().slice(0,10),
    baseline_progress:0,revised_progress:0,actual_progress:0,
  });
  const formMode=workspaceMode;
  const roleKey=roles[role];
  const selectedProjectData=projects.find(project=>project.code===selectedProject);
  function editableProject(project){
    return {
      code:project?.code||"",name:project?.name||"",status:project?.status||"future",
      client:project?.client||"",location:project?.location||"",
      contract_value_usd:project?.contract_value_usd||0,
      planned_start:project?.planned_start||"",planned_finish:project?.planned_finish||"",
      revised_finish:project?.revised_finish||"",
      reporting_date:project?.reporting_date||new Date().toISOString().slice(0,10),
      baseline_progress:project?.baseline_progress||0,revised_progress:project?.revised_progress||0,
      actual_progress:project?.actual_progress||0,
    };
  }
  useEffect(()=>{
    if(!open)return;
    setError("");
    setClearingJobs([]);setJobClearErrors({});
    setProjectChange(null);
    setDraft(editableProject(formMode==="update"?selectedProjectData:null));
  },[open,formMode,selectedProject]);
  useEffect(()=>{
    if(!open||embedded)return;
    const closeOnEscape=event=>{if(event.key==="Escape")onClose()};
    window.addEventListener("keydown",closeOnEscape);
    return()=>window.removeEventListener("keydown",closeOnEscape);
  },[open,onClose,embedded]);
  async function refresh(){
    if(!selectedProject)return;
    try{
      const [documentItems,jobItems]=await Promise.all([
        getDocuments(selectedProject,roleKey),
        getProjectIngestionJobs(selectedProject,roleKey),
      ]);
      setDocuments(documentItems);setJobs(jobItems);
    }catch{setDocuments([]);setJobs([])}
  }
  useEffect(()=>{if(open&&formMode==="update")refresh()},[open,selectedProject,role,formMode,dataRevision]);
  useEffect(()=>{
    if(!Array.isArray(jobs)||!jobs.some(j=>["queued","processing"].includes(j.status)))return;
    let cancelled=false;
    const timer=setTimeout(async()=>{
      const updates=await Promise.all(jobs.map(async job=>{
        if(!["queued","processing"].includes(job.status))return job;
        try{return await getIngestionJob(job.id,roleKey)}catch{return job}
      }));
      if(cancelled)return;
      const updatesById=new Map(updates.map(job=>[job.id,job]));
      setJobs(current=>current.map(job=>updatesById.get(job.id)||job));
    },1200);
    return()=>{cancelled=true;clearTimeout(timer)};
  },[jobs]);
  useEffect(()=>{
    if(jobs.some(j=>["ready","awaiting_approval","awaiting_date_confirmation"].includes(j.status))) {
      getDocuments(selectedProject,roleKey).then(setDocuments).catch(()=>setDocuments([]));
    }
  },[jobs,selectedProject,roleKey]);
  async function uploadFiles(files){
    if(!selectedProject){setError("Select a project before uploading.");return}
    setError("");
    for(const file of files){
      try{const result=await uploadProjectFile(file,selectedProject,roleKey);setJobs(j=>[result.job,...j])}
      catch(e){
        setJobs(j=>[{
          id:`failed-${Date.now()}-${file.name}`,filename:file.name,status:"failed",
          progress:100,message:e.message||"The upload could not be accepted.",
        },...j]);
      }
    }
  }
  async function clearFailedJob(job){
    if(!window.confirm("Clear this failed upload permanently? The stored file and diagnostic record cannot be recovered."))return;
    if(!job.document_id){
      setJobs(items=>items.filter(item=>item.id!==job.id));
      setJobClearErrors(current=>{const next={...current};delete next[job.id];return next});
      return;
    }
    setClearingJobs(items=>[...items,job.id]);
    setJobClearErrors(current=>({...current,[job.id]:""}));
    try{
      await clearFailedIngestionJob(job.id,roleKey);
      setJobs(items=>items.filter(item=>item.id!==job.id));
      setJobClearErrors(current=>{const next={...current};delete next[job.id];return next});
    }catch(clearError){
      setJobClearErrors(current=>({...current,[job.id]:clearError.message||"Could not clear failed upload"}));
    }finally{
      setClearingJobs(items=>items.filter(id=>id!==job.id));
    }
  }
  async function retryIndex(job){
    try{
      await retryDocumentIndex(job.id,roleKey);
      setJobs(await getProjectIngestionJobs(selectedProject,roleKey));
    }catch(retryError){
      setJobClearErrors(current=>({...current,[job.id]:retryError.message||"Could not retry indexing"}));
    }
  }
  async function review(job,decision){
    try{
      const result=await decideChange(job.change_request_id,decision,roleKey);
      const nextStatus=decision==="approve"&&result.action==="document_approval"?"processing":decision==="approve"?"ready":"rejected";
      setJobs(items=>items.map(x=>x.id===job.id?{...x,status:nextStatus,message:result.indexing==="queued"?"Approved; indexing queued":`Change ${decision}d`}:x));
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
      if(formMode==="update"){
        const {code,...update}=normalized;
        await updateProject(code,update,roleKey);
        await refreshProjects();
        return;
      }
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
        onClose();
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
  const content=<aside className={`upload-center ${embedded?"embedded":""}`} role={embedded?undefined:"dialog"} aria-modal={embedded?undefined:"true"} aria-label={formMode==="create"?"Create Project":"Update Project"} onMouseDown={event=>event.stopPropagation()}>
    <div className="upload-head"><div><span>PROJECT CONTROLS</span><h2>{formMode==="create"?"Create Project":`Update ${selectedProjectData?.name||selectedProject}`}</h2></div>{!embedded&&<button onClick={onClose}><X/></button>}</div>
    <section className="new-project-panel">
      <form className="new-project-form" onSubmit={submitProject}>
        <h3>{formMode==="create"?"New project details":`Update ${draft.code}`}</h3>
        {formMode==="create"&&<label className="project-excel-drop">
          <FileSpreadsheet size={22}/><b>Auto-fill from canonical XLSX</b>
          <span>One project row; related sheets are retained for approval.</span>
          <input type="file" accept=".xlsx" onChange={e=>uploadNewProjectWorkbook(e.target.files[0])}/>
        </label>}
        {formMode==="create"&&projectChange?.preview?.related_counts&&<div className="import-counts">
          {Object.entries(projectChange.preview.related_counts).map(([name,count])=><span key={name}><b>{count}</b>{name}</span>)}
        </div>}
        <fieldset><legend>Project identity</legend><div className="project-form-grid">
          <label>Project code<input required disabled={formMode==="update"} value={draft.code} onChange={e=>setDraft({...draft,code:e.target.value.toUpperCase()})} placeholder="PRJ-2027-010"/></label>
          <label>Status<select value={draft.status} onChange={e=>setDraft({...draft,status:e.target.value})}><option value="future">Future</option><option value="active">Active</option><option value="completed">Completed</option></select></label>
          <label className="wide">Project name<input required value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/></label>
          <label className="wide">Client<input required value={draft.client} onChange={e=>setDraft({...draft,client:e.target.value})}/></label>
          <label>Location<input required value={draft.location} onChange={e=>setDraft({...draft,location:e.target.value})}/></label>
        </div></fieldset>
        <fieldset><legend>Commercial details</legend><div className="project-form-grid">
          <label>Contract value (USD)<input required min="0" type="number" value={draft.contract_value_usd} onChange={e=>setDraft({...draft,contract_value_usd:e.target.value})}/></label>
          {draft.status==="active"&&<label>Reporting date<input required type="date" value={draft.reporting_date} onChange={e=>setDraft({...draft,reporting_date:e.target.value})}/></label>}
        </div></fieldset>
        <fieldset><legend>Schedule</legend><div className="project-form-grid">
          <label>{draft.status==="completed"?"Start date":"Planned start"}<input required type="date" value={draft.planned_start} onChange={e=>setDraft({...draft,planned_start:e.target.value})}/></label>
          <label>{draft.status==="completed"?"End date":"Planned finish"}<input required type="date" value={draft.planned_finish} onChange={e=>setDraft({...draft,planned_finish:e.target.value})}/></label>
          {draft.status==="active"&&<label>Revised finish<input type="date" value={draft.revised_finish} onChange={e=>setDraft({...draft,revised_finish:e.target.value})}/></label>}
        </div></fieldset>
        {draft.status==="active"&&<fieldset><legend>Progress</legend><div className="project-form-grid">
          {["baseline_progress","revised_progress","actual_progress"].map(field=><label key={field}>{field.replaceAll("_"," ")} (%)<input type="number" min="0" max="100" step=".1" value={draft[field]} onChange={e=>setDraft({...draft,[field]:Number(e.target.value)})}/></label>)}
        </div></fieldset>}
        <button className="primary project-submit" type="submit">{formMode==="update"?"Save project updates":projectChange?"Save preview changes":"Create approval preview"}</button>
        {formMode==="create"&&projectChange&&<div className="project-review"><b>{projectChange.status.replaceAll("_"," ")}</b><span>{roleKey==="admin"?"Review and approve before the database is changed.":"Saved for Admin review; the database has not changed."}</span>
          {projectChange.status==="pending"&&<div className="job-actions"><button type="button" onClick={()=>alert(JSON.stringify(projectChange.preview,null,2))}>Preview</button>{roleKey==="admin"&&<><button type="button" onClick={()=>reviewProject("approve")}>Approve</button><button type="button" onClick={()=>reviewProject("reject")}>Reject</button></>}</div>}</div>}
      </form>
    </section>
    {formMode==="update"&&<>
    <label className="drop-zone" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();uploadFiles([...e.dataTransfer.files])}}>
      <Upload size={28}/><b>Drop PDF or XLSX files here</b><span>PDF 20 MB · XLSX 10 MB</span>
      <input type="file" accept=".pdf,.xlsx" multiple onChange={e=>uploadFiles([...e.target.files])}/>
    </label>
    {error&&<div className="upload-error">{error}</div>}
    <h3>Ingestion jobs</h3>{jobs.length===0&&<p className="empty">No uploads in this session.</p>}
    {jobs.map(job=><div className={`job-row ${job.status==="failed"?"failed":""}`} key={job.id}><div>
      <b>{job.status==="failed"?"Upload failed":job.status.replaceAll("_"," ")}</b>
      {job.filename&&<small>{job.filename}</small>}<span>{job.message}</span>
      {job.status!=="failed"&&<progress value={job.progress} max="100"/>}
      {jobClearErrors[job.id]&&<small className="job-clear-error">{jobClearErrors[job.id]}</small>}</div>
      {job.status==="failed"&&job.approval_status==="approved"&&roleKey==="admin"&&<button className="job-retry" type="button" onClick={()=>retryIndex(job)}>Retry indexing</button>}
      {job.status==="failed"&&<button className="job-clear" type="button" disabled={clearingJobs.includes(job.id)} onClick={()=>clearFailedJob(job)}>
        <Trash2 size={13}/>{clearingJobs.includes(job.id)?"Clearing…":"Clear"}
      </button>}
      {job.status==="awaiting_date_confirmation"&&<div className="date-confirm"><input type="date" value={dateEdits[job.id]||job.detected_reporting_date||""} onChange={e=>setDateEdits({...dateEdits,[job.id]:e.target.value})}/><button onClick={()=>confirmDate(job)}>Confirm date</button></div>}
      {job.status==="awaiting_approval"&&<div className="job-actions"><button onClick={()=>showPreview(job)}>Preview</button>
        {roleKey==="admin"&&<><button onClick={()=>review(job,"approve")}>Approve</button><button onClick={()=>review(job,"reject")}>Reject</button></>}</div>}</div>)}
    <h3>Project documents</h3>{documents.map(doc=><div className="document-row" key={doc.id}>
      {doc.kind==="pdf"?<FileText/>:<FileSpreadsheet/>}<div><b>{doc.filename}</b><span>{doc.status}</span></div>
      {roleKey==="admin"&&<button onClick={()=>remove(doc.id)} title="Delete document"><Trash2/></button>}</div>)}
    </>}
  </aside>;
  return embedded?content:<div className="upload-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget){onClose();returnFocusRef?.current?.focus()}}}>{content}</div>;
}

/** Conversational UI that preserves messages for the current browser session. */
function LegacyAssistant({ role, projects, initialQuery, clearInitial, messages, setMessages, clearMessages }) {
  const [query,setQuery]=useState(initialQuery||""); const [loading,setLoading]=useState(false);
  const [selectedProject,setSelectedProject]=useState("");
  const messagesRef=useRef(null),forceScrollRef=useRef(false);
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
  async function submit(text=query){
    if(!text.trim()||loading)return;
    console.info("prosight.query_submitted", {query_length:text.trim().length,role:roles[role]});
    forceScrollRef.current=true;setMessages(m=>[...m,{role:"user",content:text}]);setQuery("");setLoading(true);
    // The backend returns either OpenAI application mode or local test/data mode.
    const history=messages.filter(message=>["user","assistant"].includes(message.role)&&!message.error&&!message.intro)
      .slice(-10).map(({role,content})=>({role,content}));
    try{const result=await askAgent(text,roles[role],selectedProject||null,history);
      console.info("prosight.response_rendered",{request_id:result.request_id,provider:result.mode,duration_ms:result.duration_ms});
      setMessages(m=>[...m,{role:"assistant",content:result.answer,citations:result.citations,route:result.agent_route,mode:result.mode,notice:result.notice,requestId:result.request_id,durationMs:result.duration_ms}]);}
    catch(error){console.error("prosight.client_error",{request_id:error.requestId||null,error_type:error.name});
      setMessages(m=>[...m,{role:"assistant",content:`I could not reach the ProSight service. Reference: ${error.requestId||"not available"}.`,error:true}]);}
    finally{setLoading(false);}
  }
  return <div className="assistant-page"><PageTitle eyebrow="Multi-agent project intelligence" title="AI Project Assistant" subtitle="Ask about structured project data or evidence from uploaded reports.">
    <button className="new-chat-action" disabled={loading} onClick={clearMessages}><RotateCcw size={15}/> New chat</button>
  </PageTitle>
    <div className="suggestions"><select value={selectedProject} onChange={e=>setSelectedProject(e.target.value)}><option value="">All projects</option>{projects.map(p=><option value={p.code} key={p.code}>{p.code}</option>)}</select>
      {["Which active projects are delayed?","Show project contacts","What does the latest report say?"].map(item=><button key={item} onClick={()=>submit(item)}>{item}</button>)}
     </div>
    <section className="chat card"><div className="messages" ref={messagesRef}>{messages.map((m,i)=><div className={`message ${m.role}`} key={i}>
      <div className="avatar">{m.role==="assistant"?<Sparkles size={18}/>:<Users size={18}/>}</div><div>
      {m.role==="assistant"?<AssistantText content={m.content}/>:<p>{m.content}</p>}
      {m.role==="assistant"&&m.mode&&<div className={`mode-badge ${m.mode}`}>{m.mode==="openai"?"OpenAI reasoning":"Local data mode"}</div>}
      {m.route?.length>0&&<div className="agent-route">{m.route.map((agent,i)=><span key={`${agent}-${i}`}>{agent.replaceAll("_"," ")}</span>)}</div>}
      {m.requestId&&m.mode&&<div className="request-meta">Request {m.requestId.slice(0,8)} · {m.durationMs} ms</div>}
      {m.notice&&<div className="mode-notice">{m.notice}</div>}
      {m.citations?.length>0&&<details><summary>View {m.citations.length} sources</summary>{m.citations.map(c=><span key={c}>{c}</span>)}</details>}
      </div></div>)}
      {loading&&<div className="typing"><i/><i/><i/></div>}</div>
      <div className="composer"><input value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>e.key==="Enter"&&submit()} placeholder="Ask the multi-agent team about data or documents..."/>
        <button className="primary" onClick={()=>submit()}><Send size={17}/></button></div>
    </section></div>;
}

/** Executive workspace for conversational portfolio intelligence. */
function Assistant({ userId, role, projects, initialQuery, clearInitial, messages, setMessages, clearMessages, selectedProject, setSelectedProject, onDataChanged }) {
  const [query,setQuery]=useState(initialQuery||"");
  const [loading,setLoading]=useState(false);
  const flow=useAssistantWorkflows({userId,role:roles[role],empty:!projects.length,selectedProject,setMessages,onChanged:onDataChanged});
  const busy=loading||flow.busy;
  const messagesRef=useRef(null),forceScrollRef=useRef(false);
  useEffect(()=>{if(initialQuery){
    setQuery(initialQuery);
    clearInitial();
  }},[initialQuery]);
  useEffect(()=>{
    const container=messagesRef.current;
    if(!container)return;
    const nearBottom=container.scrollHeight-container.scrollTop-container.clientHeight<120;
    if(forceScrollRef.current||nearBottom){
      container.scrollTo({top:container.scrollHeight,behavior:forceScrollRef.current?"auto":"smooth"});
      forceScrollRef.current=false;
    }
  },[messages,loading,flow.busy,flow.drafts.length,flow.attachments.length]);
  async function submit(text=query){
    if((!text.trim()&&!flow.file)||busy)return;
    forceScrollRef.current=true;
    if(await flow.submit(text)){setQuery("");return;}
    console.info("prosight.query_submitted",{query_length:text.trim().length,role:roles[role]});
    forceScrollRef.current=true;
    const assistantId=`pending-${Date.now()}-${Math.random()}`;
    setMessages(current=>[...current,{role:"user",content:text},{role:"assistant",content:"Thinking",pending:true,id:assistantId}]);
    setQuery("");setLoading(true);
    const history=messages.filter(message=>["user","assistant"].includes(message.role)&&!message.error&&!message.intro)
      .slice(-10).map(({role:messageRole,content})=>({role:messageRole,content}));
    try{
      const result=await askAgentStream(text,roles[role],selectedProject||null,history,{
        onStatus:status=>setMessages(current=>current.map(message=>message.id===assistantId?{...message,content:status}:message)),
      });
      console.info("prosight.response_rendered",{request_id:result.request_id,provider:result.mode,duration_ms:result.duration_ms});
      setMessages(current=>current.map(message=>message.id===assistantId?{...message,pending:false,content:result.answer,citations:result.citations,
        route:result.agent_route,mode:result.mode,notice:result.notice,requestId:result.request_id,durationMs:result.duration_ms}:message));
    }catch(error){
      console.error("prosight.client_error",{request_id:error.requestId||null,error_type:error.name});
      setMessages(current=>current.map(message=>message.id===assistantId?{...message,pending:false,
        content:`I could not reach the ProSight service. Reference: ${error.requestId||"not available"}.`,error:true}:message));
    }finally{setLoading(false);}
  }
  const selected=projects.find(project=>project.code===selectedProject);
  const contextName=selected?.name||"All projects";
  const contextOptions=[{value:"",label:"All projects",description:"Portfolio-wide context"},
    ...projects.map(project=>({value:project.code,label:project.code,description:project.name}))];
  return <div className="assistant-page">
    <PageTitle eyebrow="Multi-agent project intelligence" title="AI Project Assistant" subtitle="Ask about structured project data or evidence from uploaded reports.">
      <div className="assistant-title-actions">
        <SmartSelect label="Analysis context" value={selectedProject} options={contextOptions} onChange={setSelectedProject}
          icon={Building2} className="assistant-project-select"/>
        <button className="new-chat-action primary" aria-label="Start a new chat" title="Start a new chat" disabled={busy} onClick={()=>{clearMessages();flow.reset();setQuery("");setSelectedProject("");clearInitial();forceScrollRef.current=true}}><RotateCcw size={15}/> New chat</button>
      </div>
    </PageTitle>
    <section className="chat card">
      <div className="messages" ref={messagesRef}>
        <div className="message assistant"><div className="avatar"><Sparkles size={18}/></div><div className="message-content"><AssistantText content={projects.length
          ?"Hello, I’m ProSight AI, your construction intelligence AI agent. Ask about your projects, describe a new project, or attach a file to review."
          :flow.permitted?"Hello, I’m ProSight AI, your construction intelligence AI agent. There are no projects in your organization yet. Would you like to create one? Describe your project in natural language, or upload an Excel sheet with details for one or more projects. I’ll prepare drafts for you to review."
          :"Hello, I’m ProSight AI, your construction intelligence AI agent. There are no approved projects in your organization yet. An Admin or Project Manager can create the first project; once approved, you can upload its files here."}/></div></div>
        {messages.filter(message=>!message.intro).map((message,index)=><div className={`message ${message.role} ${message.error?"error":""} ${message.pending?"pending":""}`} key={message.id||index}>
          <div className="avatar">{message.role==="assistant"?<Sparkles size={18}/>:<Users size={18}/>}</div>
          <div><div className="message-content">{message.role==="assistant"?(message.pending
            ?<div className="response-state"><span>{message.content}</span><i className="response-state-loader"><em/><em/><em/></i></div>
            :<AssistantText content={message.content}/>):<p>{message.content}</p>}</div>
            {message.role==="assistant"&&(message.mode||message.route?.length>0||message.requestId||message.notice)&&
              <details className="response-details"><summary>Response details</summary><div className="response-meta">
                {message.mode&&<div className={`mode-badge ${message.mode}`}>{message.mode==="openai"?"OpenAI reasoning":"Local data mode"}</div>}
                {message.route?.length>0&&<div className="agent-route">{message.route.map((agent,routeIndex)=><span key={`${agent}-${routeIndex}`}>{agent.replaceAll("_"," ")}</span>)}</div>}
                {message.requestId&&message.mode&&<div className="request-meta">Request {message.requestId.slice(0,8)} · {message.durationMs} ms</div>}
                {message.notice&&<div className="mode-notice">{message.notice}</div>}
              </div></details>}
            {message.citations?.length>0&&<details className="source-details"><summary>Sources used <span>{message.citations.length}</span></summary>
              {message.citations.map(citation=><span key={citation}>{citation}</span>)}</details>}
          </div>
        </div>)}
        <WorkflowMessages flow={flow}/>
        {flow.busy&&<div className="message assistant pending"><div className="avatar"><Sparkles size={18}/></div><div className="message-content"><div className="response-state"><span>Preparing your request…</span><i className="response-state-loader"><em/><em/><em/></i></div></div></div>}
      </div>
      <div className="composer-shell">
        <div className="composer-context"><span><Building2 size={13}/>{contextName}</span><small>Enter to send · Shift + Enter for a new line</small></div>
        <WorkflowComposer flow={flow} showConsent={!projects.length||!!flow.active||isCreation(query)}/>
        <div className="composer"><ChatUpload flow={flow} disabled={busy}/><textarea rows="1" value={query} onChange={event=>setQuery(event.target.value)}
          onKeyDown={event=>{if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();submit();}}}
          aria-label="Message ProSight AI" placeholder={!projects.length?"Describe your project, or attach an Excel project register…":"Ask about your projects, describe a new one, or attach a file…"}/>
          <button className="primary" aria-label="Send question" disabled={busy||(!query.trim()&&!flow.file)} onClick={()=>submit()}><Send size={18}/></button>
        </div>
      </div>
    </section>
  </div>;
}

/** Root component responsible for shared provider data, theme, and navigation state. */
const initialMessages=()=>[{role:"assistant",content:"Hello — I’m ProSight AI. Ask me about project progress, contacts, activities, resources, or milestones.",citations:[],intro:true}];

const workspacePages = new Set(["assistant", "dashboard", "projects", "resource-allocation"]);
function requestedPage(){return location.pathname.slice(1)}

export default function App(){
  const [user,setUser]=useState(null),[view,setView]=useState("loading"),[error,setError]=useState("");
  useEffect(()=>{
    let active=true, revision=0;
    async function verify(){
      const request=++revision;
      try {
        const current=await getCurrentUser();
        if(!active||request!==revision)return;
        setUser(current);setError("");
        setView(current?"app":location.pathname==="/"?"landing":"login");
        if(!current&&workspacePages.has(requestedPage())){
          sessionStorage.setItem("prosight:returnTo",location.pathname);
          history.replaceState(null,"","/login");
        }
      } catch(err){if(active&&request===revision){setUser(null);setError(err.message);setView("error")}}
    }
    verify();
    window.addEventListener("prosight:auth-changed",verify);
    window.addEventListener("popstate",verify);
    return()=>{active=false;window.removeEventListener("prosight:auth-changed",verify);window.removeEventListener("popstate",verify)};
  },[]);
  function signedIn(current){
    if(!current)return;
    setUser(current);setError("");setView("app");
    const next=sessionStorage.getItem("prosight:returnTo");sessionStorage.removeItem("prosight:returnTo");
    history.replaceState(null,"",workspacePages.has(next?.slice(1))?next:"/assistant");
  }
  async function signOut(){
    try{await logoutUser();setUser(null);setError("");setView("landing");history.replaceState(null,"","/")}
    catch(err){setError(err.message)}
  }
  if(view==="loading")return <div className="auth-loading" role="status">Checking your session…</div>;
  if(view==="error")return <div className="auth-loading"><p role="alert">{error}</p><button onClick={()=>window.location.reload()}>Retry</button><button onClick={signOut}>Sign out</button></div>;
  if(!user&&view==="landing")return <LandingPage onLogin={()=>{history.pushState(null,"","/login");setView("login")}}/>;
  if(!user)return <LoginPage onBack={()=>{history.pushState(null,"","/");setView("landing")}} onLoggedIn={signedIn}/>;
  return <>{error&&<div role="alert">{error}</div>}<Workspace key={user.id} user={user} onLogout={signOut}/></>;
}

function Workspace({user,onLogout}){
  const [page,updatePage]=useState(()=>workspacePages.has(requestedPage())?requestedPage():"assistant");
  function setPage(next){if(workspacePages.has(next)){history.pushState(null,"",`/${next}`);updatePage(next)}}
  useEffect(()=>{
    if(!workspacePages.has(requestedPage()))history.replaceState(null,"","/assistant");
    const navigate=()=>updatePage(workspacePages.has(requestedPage())?requestedPage():"assistant");
    window.addEventListener("popstate",navigate);return()=>window.removeEventListener("popstate",navigate);
  },[]);
  const[dark,setDark]=useState(()=>localStorage.theme==="dark");
  const role=user.role.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
  const[projects,setProjects]=useState([]),[loading,setLoading]=useState(true);
  const [collapsed,setCollapsed]=useState(false),[initialQuery,setInitialQuery]=useState("");
  const [messages,setMessages]=useState(initialMessages),[dataRevision,setDataRevision]=useState(0);
  const [assistantProject,setAssistantProject]=useState(""),[explorerProject,setExplorerProject]=useState("");

  // Theme preference is local to the browser and does not affect server data.
  useEffect(()=>{document.documentElement.dataset.theme=dark?"dark":"light";localStorage.theme=dark?"dark":"light"},[dark]);
  // Changing roles refetches data so contact masking is enforced by Python.
  async function refreshProjects(showLoader=false){
    if(showLoader)setLoading(true);
    try{setProjects(await getProjects(roles[role]))}finally{if(showLoader)setLoading(false)}
  }
  useEffect(()=>{refreshProjects(true).catch(()=>{})},[role]);
  async function activityCleared(item){
    if(item.event_type==="change_approved"){
      await refreshProjects();
      setDataRevision(value=>value+1);
    }
  }
  function projectDeleted(code){
    setProjects(current=>current.filter(project=>project.code!==code));
    setExplorerProject("");setAssistantProject("");setMessages(initialMessages());setInitialQuery("");
    setDataRevision(value=>value+1);
  }
  function goToAssistant(q){setInitialQuery(q);setPage("assistant")}
  return <div className="app-shell"><Sidebar key={dataRevision} {...{page,setPage,collapsed,setCollapsed,dark,setDark,refreshProjects,user,onLogout}}
    onActivityCleared={activityCleared}
    role={role}/><div className="main-shell">
    <main className={loading?"loading":""}>
      {loading?<div className="loader"><i/></div>:<>
      {page==="dashboard"&&projects.length>0&&<Dashboard projects={projects} role={role} goToAssistant={goToAssistant} onOpenResourceAllocation={()=>setPage("resource-allocation")}/>}
      {["dashboard","projects"].includes(page)&&projects.length===0&&<section className="empty-project-guide card"><span>Welcome to your project workspace</span><h1>No approved projects yet</h1><p>Start with a project description or a project workbook. Drafts awaiting approval stay separate from live projects.</p>{["admin","project_manager"].includes(roles[role])?<div className="attachment-actions"><button className="primary" onClick={()=>goToAssistant("Create a new project")}>Describe the first project</button><button className="secondary" onClick={()=>setPage("assistant")}>Upload workbook / review pending requests</button></div>:<p>An Admin or Project Manager can create the first project. You can add project documents once it is approved.</p>}</section>}
      {page==="resource-allocation"&&<ResourceAllocationDashboard projects={projects} role={role} onBack={()=>setPage("dashboard")}/>}
      {page==="projects"&&projects.length>0&&<ProjectExplorer projects={projects} role={role}
        refreshProjects={refreshProjects} dataRevision={dataRevision}
        selectedProject={explorerProject} setSelectedProject={setExplorerProject} onProjectDeleted={projectDeleted}/>}
      {page==="assistant"&&<Assistant userId={user.id} role={role} projects={projects} initialQuery={initialQuery} clearInitial={()=>setInitialQuery("")}
        messages={messages} setMessages={setMessages} clearMessages={()=>setMessages(initialMessages())}
        selectedProject={assistantProject} setSelectedProject={setAssistantProject} onDataChanged={async()=>{await refreshProjects();setDataRevision(value=>value+1)}}/>}
      </>}</main></div></div>;
}
