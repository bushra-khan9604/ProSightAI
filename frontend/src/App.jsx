import { useEffect, useRef, useState } from "react";
import {
  Activity, Bell, BookOpen, Bot, BriefcaseBusiness, Building2,
  ChevronRight, CircleDollarSign, Clock3, LayoutDashboard, Menu,
  FileSpreadsheet, FileText, Moon, Plus, RotateCcw, Send, Sun, Trash2,
  Upload, Users, Wrench, X,
} from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  askAgent, confirmDocumentDate, createProjectImportPreview, createProjectPreview,
  decideChange, deleteDocument, getChangeRequest, getDocuments, getIngestionJob,
  getApprovals, getInvoicePivot, getNotifications, getPortfolioInvoices,
  getPortfolioManpower, getProjectIngestionJobs, getProjects, markAllNotificationsRead,
  markNotificationRead, portfolioTemplateUrl, updateProject, updateProjectImport,
  uploadPortfolioWorkbook, uploadProjectFile,
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
    return <div className="assistant-prose" key={index}>{block.lines.map((line,lineIndex)=>
      line.startsWith("### ")?<h4 key={lineIndex}><InlineText content={line.slice(4)}/></h4>:
      <span key={lineIndex}><InlineText content={line}/>{lineIndex<block.lines.length-1&&<br/>}</span>)}</div>;
  })}</div>;
}

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
function Header({ dark, setDark, role, setRole, refreshProjects, onActivityCleared }) {
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
  return <header>
    <div className="header-actions">
      <select value={role} onChange={(e) => setRole(e.target.value)}>
        {Object.keys(roles).map((item) => <option key={item}>{item}</option>)}
      </select>
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
              <div className="notification-actions"><button onClick={()=>alert(JSON.stringify(item.preview,null,2))}>Preview</button>
                <button className="approve" onClick={()=>review(item.id,"approve")}>Approve</button>
                <button className="reject" onClick={()=>review(item.id,"reject")}>Reject</button></div>
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
function ProjectExplorer({ projects, role, refreshProjects, dataRevision }) {
  const [selected, setSelected] = useState(projects[0]?.code);
  const [tab, setTab] = useState("overview");
  const [createOpen,setCreateOpen]=useState(false);
  const [portfolioOpen,setPortfolioOpen]=useState(false),[portfolioRevision,setPortfolioRevision]=useState(0);
  const [portfolioManpower,setPortfolioManpower]=useState([]),[invoices,setInvoices]=useState([]),[pivot,setPivot]=useState([]);
  const project = projects.find((p)=>p.code===selected) || projects[0];
  const roleKey=roles[role];
  useEffect(()=>{
    if(projects.length&&!projects.some(item=>item.code===selected))setSelected(projects[0].code);
  },[projects,selected]);
  useEffect(()=>{
    if(!project)return;
    if(tab==="portfolio manpower")getPortfolioManpower(roleKey,project.code).then(setPortfolioManpower).catch(()=>setPortfolioManpower([]));
    if(tab==="project invoices")getPortfolioInvoices(roleKey,project.code).then(setInvoices).catch(()=>setInvoices([]));
    if(tab==="invoice pivot")getInvoicePivot(roleKey).then(setPivot).catch(()=>setPivot([]));
  },[tab,project?.code,roleKey,portfolioRevision]);
  if (!project) return null;
  const manpower = project.manpower.map((m)=>({name:m.designation,value:m.count}));
  return <>
    <PageTitle eyebrow="Project controls" title="Project Explorer" subtitle="Inspect schedules, teams, site operations, and supporting evidence.">
      <div className="project-title-actions">
        <select className="project-select" value={project.code} onChange={(e)=>setSelected(e.target.value)}>
          {projects.map((p)=><option key={p.code} value={p.code}>{p.code} — {p.name}</option>)}
        </select>
        <button className="primary create-project-action" onClick={()=>setPortfolioOpen(true)}>
          <FileSpreadsheet size={16}/> Portfolio Import
        </button>
        {["project_manager","admin"].includes(roleKey)&&<button className="primary create-project-action" onClick={()=>setCreateOpen(true)}><Plus size={16}/> Create Project</button>}
      </div>
    </PageTitle>
    <section className="project-hero card">
      <div><span className="status success">{project.status}</span><h2>{project.name}</h2><p>{project.location} · {project.client}</p></div>
      <div className="hero-metrics"><div><span>Contract value</span><strong>{money(project.contract_value_usd)}</strong></div>
        <div><span>Actual progress</span><strong>{project.actual_progress}%</strong></div>
        <div><span>Variance</span><strong className={project.variance_pct<0?"negative":""}>{project.variance_pct>0?"+":""}{project.variance_pct} pp</strong></div>
        <div><span>Delay</span><strong>{project.delay_days} days</strong></div></div>
    </section>
    <div className="tabs">{["overview","contacts","operations","milestones","portfolio manpower","project invoices","invoice pivot","update project"].map((item)=>
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
    <div hidden={tab!=="update project"}><UploadCenter
      open embedded workspaceMode="update" role={role} projects={projects} selectedProject={project.code}
      setSelectedProject={setSelected} refreshProjects={refreshProjects} dataRevision={dataRevision}
    /></div>
    <UploadCenter
      open={createOpen} workspaceMode="create" onClose={()=>setCreateOpen(false)}
      role={role} projects={projects} selectedProject={project.code}
      setSelectedProject={setSelected} refreshProjects={refreshProjects}
    />
    <PortfolioImport open={portfolioOpen} onClose={()=>setPortfolioOpen(false)} roleKey={roleKey}
      onImported={()=>setPortfolioRevision(value=>value+1)}/>
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

function PortfolioImport({open,onClose,roleKey,onImported}){
  const [result,setResult]=useState(null),[error,setError]=useState(""),[loading,setLoading]=useState(false);
  useEffect(()=>{if(open){setResult(null);setError("")}},[open]);
  useEffect(()=>{
    if(!open)return;
    const close=event=>{if(event.key==="Escape"&&!loading)onClose()};
    window.addEventListener("keydown",close);return()=>window.removeEventListener("keydown",close);
  },[open,loading,onClose]);
  async function upload(file){
    if(!file)return;
    setLoading(true);setError("");setResult(null);
    try{const imported=await uploadPortfolioWorkbook(file,roleKey);setResult(imported);onImported()}
    catch(uploadError){setError(uploadError.message)}
    finally{setLoading(false)}
  }
  if(!open)return null;
  return <div className="upload-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!loading)onClose()}}>
    <aside className="upload-center portfolio-import" role="dialog" aria-modal="true" aria-label="Portfolio Data Import">
      <div className="upload-head"><div><span>PORTFOLIO CONTROLS</span><h2>Portfolio Data Import</h2></div>
        <button disabled={loading} onClick={onClose}><X/></button></div>
      <p className="portfolio-help">Import canonical Manpower and Projects Invoices sheets. The complete workbook is validated before any records change, and the invoice pivot is generated from database records.</p>
      <a className="template-download" href={portfolioTemplateUrl(roleKey)}><FileSpreadsheet size={17}/> Download XLSX template</a>
      <label className="drop-zone"><Upload size={28}/><b>{loading?"Validating and importing…":"Choose portfolio XLSX workbook"}</b>
        <span>Maximum file size 20 MB</span><input disabled={loading} type="file" accept=".xlsx" onChange={event=>upload(event.target.files[0])}/></label>
      {loading&&<progress className="portfolio-progress" max="100"/>}
      {error&&<div className="upload-error"><b>Import failed</b><span>{error}</span></div>}
      {result&&<div className="portfolio-result"><b>Portfolio import completed</b>
        <span>Manpower: {result.summary?.manpower?.inserted||0} inserted, {result.summary?.manpower?.updated||0} updated</span>
        <span>Invoices: {result.summary?.invoices?.inserted||0} inserted, {result.summary?.invoices?.updated||0} updated</span></div>}
    </aside>
  </div>;
}

/** Project-scoped upload, ingestion status, review, and document management drawer. */
function UploadCenter({ open, onClose=()=>{}, role, projects, selectedProject, setSelectedProject, refreshProjects, returnFocusRef, embedded=false, workspaceMode="update", dataRevision=0 }) {
  const [documents,setDocuments]=useState([]),[jobs,setJobs]=useState([]),[error,setError]=useState("");
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
      {job.status!=="failed"&&<progress value={job.progress} max="100"/>}</div>
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
function Assistant({ role, projects, initialQuery, clearInitial, messages, setMessages, clearMessages }) {
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
      .slice(-20).map(({role,content})=>({role,content}));
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
      <div className="avatar">{m.role==="assistant"?<Bot size={18}/>:<Users size={18}/>}</div><div>
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

/** Root component responsible for shared provider data, theme, and navigation state. */
const initialMessages=()=>[{role:"assistant",content:"Hello — I’m ProSight AI. Ask me about project progress, contacts, activities, resources, or milestones.",citations:[],intro:true}];

export default function App(){
  const [page,setPage]=useState("assistant"),[dark,setDark]=useState(()=>localStorage.theme==="dark");
  const [role,setRole]=useState("Project Manager"),[projects,setProjects]=useState([]),[loading,setLoading]=useState(true);
  const [collapsed,setCollapsed]=useState(false),[initialQuery,setInitialQuery]=useState("");
  const [messages,setMessages]=useState(initialMessages),[dataRevision,setDataRevision]=useState(0);
  // Theme preference is local to the browser and does not affect server data.
  useEffect(()=>{document.documentElement.dataset.theme=dark?"dark":"light";localStorage.theme=dark?"dark":"light"},[dark]);
  // Changing roles refetches data so contact masking is enforced by Python.
  async function refreshProjects(showLoader=false){
    if(showLoader)setLoading(true);
    try{setProjects(await getProjects(roles[role]))}finally{if(showLoader)setLoading(false)}
  }
  useEffect(()=>{refreshProjects(true)},[role]);
  async function activityCleared(item){
    if(item.event_type==="change_approved"){
      await refreshProjects();
      setDataRevision(value=>value+1);
    }
  }
  function goToAssistant(q){setInitialQuery(q);setPage("assistant")}
  return <div className="app-shell"><Sidebar {...{page,setPage,collapsed,setCollapsed}}/><div className="main-shell">
    <Header dark={dark} setDark={setDark} role={role} refreshProjects={refreshProjects}
      onActivityCleared={activityCleared}
      setRole={nextRole=>{setRole(nextRole);setMessages(initialMessages())}}/><main className={loading?"loading":""}>
      {loading?<div className="loader"><i/></div>:<>
      {page==="dashboard"&&<Dashboard projects={projects} goToAssistant={goToAssistant}/>}
      {page==="projects"&&<ProjectExplorer projects={projects} role={role}
        refreshProjects={refreshProjects} dataRevision={dataRevision}/>}
      {page==="assistant"&&<Assistant role={role} projects={projects} initialQuery={initialQuery} clearInitial={()=>setInitialQuery("")}
        messages={messages} setMessages={setMessages} clearMessages={()=>setMessages(initialMessages())}/>}
      </>}</main></div></div>;
}
