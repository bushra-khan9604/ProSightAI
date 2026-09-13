import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowLeft, BriefcaseBusiness, CalendarDays, Check,
  Download, Filter, FlaskConical, MapPin, Network, RotateCcw, Search,
  SlidersHorizontal, UserRoundCheck, UserRoundX, Users, X,
} from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { exportPortfolioManpower, getPortfolioManpower } from "./api";

const STATE_LABELS={allocated:"Allocated",on_leave:"On leave",not_allocated:"Not allocated"};
const STATE_COLORS={allocated:"#2878d0",on_leave:"#e49b27",not_allocated:"#94a3b8"};
const CATEGORY_COLORS=["#2878d0","#0f9d8a","#e49b27","#8b5cf6","#64748b"];
const FILTER_KEYS=["project","location","department","designation","category","state"];
const EMPTY_FILTERS={project:"",location:"",department:"",designation:"",category:"",state:"",search:""};

const clean=value=>String(value??"").trim();
const normalized=value=>clean(value).toLocaleLowerCase();
const hasAny=(value,terms)=>terms.some(term=>normalized(value).includes(term));

export function workforceState(item){
  const status=item.status,allocation=item.allocation,location=item.current_location;
  if(hasAny(status,["on leave","leave","vacation"])||hasAny(location,["on leave","leave","vacation"]))return "on_leave";
  if(!item.current_project_code||hasAny(status,["not allocated","unallocated","available","bench"])||hasAny(allocation,["not allocated","unallocated","available","bench"]))return "not_allocated";
  return "allocated";
}

export function hasException(item){
  const required=["emp_code","name","designation","department","category","current_location","allocation","status"];
  if(required.some(field=>!clean(item[field])))return true;
  if(Number(item.leave_balance)<0)return true;
  const leave=hasAny(item.status,["leave","vacation"])||hasAny(item.current_location,["leave","vacation"]);
  const explicitlyAllocated=normalized(item.allocation)==="allocated";
  const known=hasAny(`${item.status} ${item.allocation}`,["active","allocated","leave","vacation","available","bench","mobilized"]);
  return (leave&&explicitlyAllocated)||!known;
}

function decorate(rows,changes,projectNames){
  return rows.map(source=>{
    const baselineState=workforceState(source),change=changes[source.emp_code];
    const item={...source,_baseline_state:baselineState};
    if(change?.workforce_state==="allocated"){
      item.current_project_code=change.target_project_code;
      item.current_project=projectNames[change.target_project_code]||change.target_project_code;
      item.allocation="Allocated";
      if(baselineState==="on_leave")item.status="Active";
    }else if(change?.workforce_state==="on_leave"){
      item.status="On Leave";item.allocation="On Leave";
    }else if(change?.workforce_state==="not_allocated"){
      item.current_project_code="";item.current_project="Not allocated";
      item.status="Available";item.allocation="Not Allocated";
    }
    item.workforce_state=change?.workforce_state||baselineState;
    item.project_label=projectNames[item.current_project_code]||item.current_project||item.current_project_code||"Not allocated";
    item.is_direct=normalized(item.category)==="direct";
    item.is_indirect=normalized(item.category)==="indirect";
    item.is_offshore=hasAny(item.category,["offshore"])||hasAny(item.current_location,["offshore"]);
    item.has_exception=hasException(item);
    return item;
  });
}

function filterRows(rows,filters){
  const query=normalized(filters.search);
  return rows.filter(item=>(
    (!filters.project||item.current_project_code===filters.project)&&
    (!filters.location||clean(item.current_location)===filters.location)&&
    (!filters.department||clean(item.department)===filters.department)&&
    (!filters.designation||clean(item.designation)===filters.designation)&&
    (!filters.category||clean(item.category)===filters.category)&&
    (!filters.state||item.workforce_state===filters.state)&&
    (!query||Object.values(item).some(value=>normalized(value).includes(query)))
  ));
}

function metrics(rows){return {
  total:rows.length,
  allocated:rows.filter(item=>item.workforce_state==="allocated").length,
  on_leave:rows.filter(item=>item.workforce_state==="on_leave").length,
  not_allocated:rows.filter(item=>item.workforce_state==="not_allocated").length,
  direct:rows.filter(item=>item.is_direct).length,
  indirect:rows.filter(item=>item.is_indirect).length,
  offshore:rows.filter(item=>item.is_offshore).length,
  exceptions:rows.filter(item=>item.has_exception).length,
};}

function groupCount(rows,value){
  const counts=new Map();
  for(const row of rows){const key=clean(value(row))||"Not specified";counts.set(key,(counts.get(key)||0)+1)}
  return [...counts].map(([name,count])=>({name,count})).sort((a,b)=>b.count-a.count);
}

function leaveBands(rows){
  const bands=[
    ["0–10 days",value=>value>=0&&value<=10],["11–20 days",value=>value>=11&&value<=20],
    ["21–30 days",value=>value>=21&&value<=30],["31–45 days",value=>value>=31&&value<=45],
    ["46–60 days",value=>value>=46&&value<=60],["60+ days",value=>value>60],
    ["Negative",value=>value<0],["Unknown",value=>Number.isNaN(value)],
  ];
  const numeric=value=>clean(value)===""?Number.NaN:Number(value);
  return bands.map(([name,matches])=>({name,count:rows.filter(row=>matches(numeric(row.leave_balance))).length})).filter(item=>item.count);
}

function categoryByProject(rows){
  const categories=[...new Set(rows.map(item=>clean(item.category)||"Not specified"))].slice(0,5);
  const projects=new Map();
  for(const item of rows){
    const name=item.project_label,record=projects.get(name)||{name};
    const category=clean(item.category)||"Not specified";record[category]=(record[category]||0)+1;projects.set(name,record);
  }
  return {categories,data:[...projects.values()].sort((a,b)=>categories.reduce((sum,key)=>sum+(b[key]||0)-(a[key]||0),0)).slice(0,8)};
}

function MetricCard({icon:Icon,label,value,baseline,tone="blue"}){
  const delta=value-baseline;
  return <article className="manpower-kpi card">
    <i className={`kpi-icon ${tone}`}><Icon size={20}/></i>
    <div><span>{label}</span><strong>{value}</strong>{delta!==0?<small className={delta>0?"metric-up":"metric-down"}>{delta>0?"+":""}{delta} in scenario</small>:<small>No scenario change</small>}</div>
  </article>;
}

function ChartCard({title,children}){return <article className="card manpower-chart"><h2>{title}</h2>{children}</article>}

function Filters({filters,setFilters,options,open,setOpen}){
  const update=(key,value)=>setFilters(current=>({...current,[key]:value}));
  const labels={project:"Current project",location:"Current location",department:"Department",designation:"Designation",category:"Category",state:"Workforce state"};
  return <aside className={`card manpower-filters ${open?"open":""}`} aria-label="Manpower filters">
    <div className="filter-heading"><span><SlidersHorizontal size={17}/> Filters</span><button onClick={()=>setFilters(EMPTY_FILTERS)}>Clear all</button><button className="filter-close" aria-label="Close filters" onClick={()=>setOpen(false)}><X size={18}/></button></div>
    {FILTER_KEYS.map(key=><label key={key}><span>{labels[key]}</span><select value={filters[key]} onChange={event=>update(key,event.target.value)}>
      <option value="">All</option>{options[key].map(option=><option value={option.value} key={option.value}>{option.label}</option>)}
    </select></label>)}
    <button className="secondary reset-filters" onClick={()=>setFilters(EMPTY_FILTERS)}><RotateCcw size={15}/> Reset filters</button>
  </aside>;
}

function ScenarioPanel({selected,projects,state,setState,target,setTarget,onApply,onClose}){
  return <section className="card scenario-builder" aria-label="Temporary allocation scenario">
    <div><span className="scenario-kicker"><FlaskConical size={15}/> Temporary scenario</span><h2>Reallocate {selected} employee{selected===1?"":"s"}</h2><p>This preview does not change the manpower register.</p></div>
    <label><span>Proposed state</span><select value={state} onChange={event=>setState(event.target.value)}>
      <option value="allocated">Allocated</option><option value="on_leave">On leave</option><option value="not_allocated">Not allocated</option>
    </select></label>
    {state==="allocated"&&<label><span>Target project</span><select value={target} onChange={event=>setTarget(event.target.value)}>
      {projects.map(project=><option value={project.code} key={project.code}>{project.code} · {project.name}</option>)}
    </select></label>}
    <div className="scenario-actions"><button className="secondary" onClick={onClose}>Cancel</button><button className="primary" disabled={state==="allocated"&&!target} onClick={onApply}><Check size={15}/> Apply to scenario</button></div>
  </section>;
}

export default function ManpowerDashboard({projects,onBack,onOpenImport}){
  const [rows,setRows]=useState([]),[loading,setLoading]=useState(true),[error,setError]=useState("");
  const [filters,setFilters]=useState(EMPTY_FILTERS),[filterOpen,setFilterOpen]=useState(false);
  const [changes,setChanges]=useState({}),[selected,setSelected]=useState(new Set());
  const [scenarioOpen,setScenarioOpen]=useState(false),[scenarioState,setScenarioState]=useState("allocated"),[scenarioTarget,setScenarioTarget]=useState(projects[0]?.code||"");
  const [sort,setSort]=useState({key:"name",direction:"asc"}),[exporting,setExporting]=useState(false),[exportError,setExportError]=useState("");
  const projectNames=useMemo(()=>Object.fromEntries(projects.map(project=>[project.code,project.name])),[projects]);

  async function load(){setLoading(true);setError("");try{setRows(await getPortfolioManpower())}catch(cause){setError(cause.message||"Could not load manpower") }finally{setLoading(false)}}
  useEffect(()=>{load()},[]);

  const baselineRows=useMemo(()=>decorate(rows,{},projectNames),[rows,projectNames]);
  const scenarioRows=useMemo(()=>decorate(rows,changes,projectNames),[rows,changes,projectNames]);
  const visible=useMemo(()=>filterRows(scenarioRows,filters),[scenarioRows,filters]);
  const baselineVisible=useMemo(()=>filterRows(baselineRows,filters),[baselineRows,filters]);
  const currentMetrics=useMemo(()=>metrics(visible),[visible]),baselineMetrics=useMemo(()=>metrics(baselineVisible),[baselineVisible]);
  const projectData=useMemo(()=>groupCount(visible,item=>item.project_label).slice(0,10),[visible]);
  const locationData=useMemo(()=>groupCount(visible,item=>item.current_location).slice(0,10),[visible]);
  const stateData=useMemo(()=>groupCount(visible,item=>STATE_LABELS[item.workforce_state]).map(item=>({...item,key:Object.keys(STATE_LABELS).find(key=>STATE_LABELS[key]===item.name)})),[visible]);
  const designationData=useMemo(()=>groupCount(visible,item=>item.designation).slice(0,10),[visible]);
  const leaveData=useMemo(()=>leaveBands(visible),[visible]);
  const categoryData=useMemo(()=>categoryByProject(visible),[visible]);
  const sortedRows=useMemo(()=>[...visible].sort((left,right)=>{
    const a=clean(left[sort.key]),b=clean(right[sort.key]);return a.localeCompare(b,undefined,{numeric:true})*(sort.direction==="asc"?1:-1);
  }),[visible,sort]);
  const options=useMemo(()=>({
    project:projects.map(project=>({value:project.code,label:`${project.code} · ${project.name}`})),
    location:groupCount(scenarioRows,item=>item.current_location).map(item=>({value:item.name,label:item.name})),
    department:groupCount(scenarioRows,item=>item.department).map(item=>({value:item.name,label:item.name})),
    designation:groupCount(scenarioRows,item=>item.designation).map(item=>({value:item.name,label:item.name})),
    category:groupCount(scenarioRows,item=>item.category).map(item=>({value:item.name,label:item.name})),
    state:Object.entries(STATE_LABELS).map(([value,label])=>({value,label})),
  }),[scenarioRows,projects]);

  function setChartFilter(key,value){setFilters(current=>({...current,[key]:current[key]===value?"":value}))}
  function toggleSelected(code){setSelected(current=>{const next=new Set(current);if(next.has(code))next.delete(code);else next.add(code);return next})}
  function toggleAll(){setSelected(current=>{const codes=visible.map(item=>item.emp_code);return codes.length&&codes.every(code=>current.has(code))?new Set():new Set(codes)})}
  function applyScenario(){
    setChanges(current=>{const next={...current};for(const empCode of selected)next[empCode]={emp_code:empCode,workforce_state:scenarioState,target_project_code:scenarioState==="allocated"?scenarioTarget:null};return next});
    setSelected(new Set());setScenarioOpen(false);
  }
  function removeChange(code){setChanges(current=>{const next={...current};delete next[code];return next})}
  function changeSort(key){setSort(current=>({key,direction:current.key===key&&current.direction==="asc"?"desc":"asc"}))}
  async function runExport(){
    setExporting(true);setExportError("");
    try{const visibleCodes=visible.map(item=>item.emp_code),visibleSet=new Set(visibleCodes);await exportPortfolioManpower(visibleCodes,Object.values(changes).filter(change=>visibleSet.has(change.emp_code)))}
    catch(cause){setExportError(cause.message||"Could not export manpower") }finally{setExporting(false)}
  }

  if(loading)return <div className="manpower-loading" aria-label="Loading manpower dashboard"><i/><span/><span/><span/></div>;
  if(error)return <section className="card manpower-empty"><AlertTriangle size={32}/><h2>Manpower data could not be loaded</h2><p>{error}</p><button className="primary" onClick={load}>Try again</button></section>;
  if(!rows.length)return <><button className="back-link" onClick={onBack}><ArrowLeft size={16}/> Command Center</button><section className="card manpower-empty"><Users size={36}/><h1>No manpower register is available</h1><p>Import the authorized manpower workbook from Project Explorer to populate this dashboard.</p><button className="primary" onClick={onOpenImport}>Open Project Explorer</button></section></>;

  const cards=[
    [Users,"Total employees","total","blue"],[UserRoundCheck,"Allocated employees","allocated","green"],
    [CalendarDays,"On leave employees","on_leave","purple"],[UserRoundX,"Not allocated","not_allocated","blue"],
    [BriefcaseBusiness,"Direct employees","direct","purple"],[Network,"Indirect employees","indirect","green"],
    [MapPin,"Offshore employees","offshore","blue"],[AlertTriangle,"Employees with exceptions","exceptions","red"],
  ];
  const chartHeight=245;
  return <div className="manpower-workspace">
    <div className="manpower-title-row"><div><button className="back-link" onClick={onBack}><ArrowLeft size={16}/> Command Center</button><span>Portfolio workforce</span><h1>Manpower Allocation Dashboard</h1><p>Current authorized workforce snapshot · {rows.length} employee records</p></div><div className="manpower-title-actions">
      <span className="temporary-badge"><FlaskConical size={14}/>{Object.keys(changes).length?`${Object.keys(changes).length} scenario changes`:"Baseline view"}</span>
      <button className="secondary mobile-filter" onClick={()=>setFilterOpen(true)}><Filter size={16}/> Filters</button>
      <button className="primary" disabled={!visible.length||exporting} onClick={runExport}><Download size={16}/>{exporting?"Exporting…":"Export filtered .xlsx"}</button>
    </div></div>
    {exportError&&<p className="manpower-alert" role="alert">{exportError}</p>}
    <section className="manpower-kpi-grid">{cards.map(([Icon,label,key,tone])=><MetricCard key={key} icon={Icon} label={label} value={currentMetrics[key]} baseline={baselineMetrics[key]} tone={tone}/>)}</section>
    <div className="manpower-layout"><div className="manpower-content">
      {scenarioOpen&&<ScenarioPanel selected={selected.size} projects={projects} state={scenarioState} setState={setScenarioState} target={scenarioTarget} setTarget={setScenarioTarget} onApply={applyScenario} onClose={()=>setScenarioOpen(false)}/>} 
      {Object.keys(changes).length>0&&<section className="card scenario-summary"><div><span>Temporary scenario</span><strong>{Object.keys(changes).length} proposed employee change{Object.keys(changes).length===1?"":"s"}</strong></div><div className="scenario-change-list">{Object.keys(changes).map(code=><button title="Undo this change" onClick={()=>removeChange(code)} key={code}>{code}<X size={13}/></button>)}</div><button className="secondary" onClick={()=>setChanges({})}><RotateCcw size={14}/> Reset scenario</button></section>}
      <section className="manpower-chart-grid">
        <ChartCard title="Employees by current project"><ResponsiveContainer width="100%" height={chartHeight}><BarChart data={projectData} layout="vertical" margin={{left:8,right:22}}><CartesianGrid strokeDasharray="3 3" horizontal={false}/><XAxis type="number" allowDecimals={false}/><YAxis dataKey="name" type="category" width={115} tick={{fontSize:10}}/><Tooltip/><Bar dataKey="count" fill="var(--chart-primary)" radius={[0,5,5,0]} onClick={entry=>{const name=entry?.payload?.name||entry?.name;const project=projects.find(item=>item.name===name);setChartFilter("project",project?.code||"")}}/></BarChart></ResponsiveContainer></ChartCard>
        <ChartCard title="Workforce state breakdown"><ResponsiveContainer width="100%" height={chartHeight}><PieChart><Pie data={stateData} dataKey="count" nameKey="name" innerRadius={58} outerRadius={88} paddingAngle={2} onClick={entry=>setChartFilter("state",entry?.payload?.key||entry?.key)}>{stateData.map(item=><Cell key={item.key} fill={STATE_COLORS[item.key]}/>)}</Pie><Tooltip/><Legend/></PieChart></ResponsiveContainer></ChartCard>
        <ChartCard title="Employees by current location"><ResponsiveContainer width="100%" height={chartHeight}><BarChart data={locationData} margin={{left:0,right:8}}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="name" tick={{fontSize:9}} interval={0}/><YAxis allowDecimals={false}/><Tooltip/><Bar dataKey="count" fill="var(--chart-primary)" radius={[5,5,0,0]} onClick={entry=>setChartFilter("location",entry?.payload?.name||entry?.name)}/></BarChart></ResponsiveContainer></ChartCard>
        <ChartCard title="Current project by category"><ResponsiveContainer width="100%" height={chartHeight}><BarChart data={categoryData.data}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="name" tick={{fontSize:9}} interval={0}/><YAxis allowDecimals={false}/><Tooltip/><Legend/>{categoryData.categories.map((category,index)=><Bar dataKey={category} stackId="category" fill={CATEGORY_COLORS[index]} key={category} onClick={entry=>setChartFilter("category",category)}/>)}</BarChart></ResponsiveContainer></ChartCard>
        <ChartCard title="Top designations"><ResponsiveContainer width="100%" height={chartHeight}><BarChart data={designationData} layout="vertical" margin={{left:8,right:22}}><CartesianGrid strokeDasharray="3 3" horizontal={false}/><XAxis type="number" allowDecimals={false}/><YAxis dataKey="name" type="category" width={120} tick={{fontSize:10}}/><Tooltip/><Bar dataKey="count" fill="#8b5cf6" radius={[0,5,5,0]} onClick={entry=>setChartFilter("designation",entry?.payload?.name||entry?.name)}/></BarChart></ResponsiveContainer></ChartCard>
        <ChartCard title="Leave balance band"><ResponsiveContainer width="100%" height={chartHeight}><BarChart data={leaveData}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="name" tick={{fontSize:9}} interval={0}/><YAxis allowDecimals={false}/><Tooltip/><Bar dataKey="count" fill="#22a447" radius={[5,5,0,0]}/></BarChart></ResponsiveContainer></ChartCard>
      </section>
      <section className="card employee-register"><div className="register-heading"><div><span>Interactive employee register</span><h2>All Employee Details</h2><p>{visible.length} of {scenarioRows.length} employees shown · select employees to build a temporary scenario</p></div><div className="register-actions"><label><Search size={16}/><input value={filters.search} onChange={event=>setFilters(current=>({...current,search:event.target.value}))} placeholder="Search all employee fields" aria-label="Search all employee fields"/></label><button className="primary" disabled={!selected.size} onClick={()=>setScenarioOpen(true)}><FlaskConical size={15}/> Build scenario ({selected.size})</button></div></div>
        <div className="manpower-table-wrap"><table><thead><tr><th><input type="checkbox" aria-label="Select all filtered employees" checked={Boolean(visible.length)&&visible.every(item=>selected.has(item.emp_code))} onChange={toggleAll}/></th>{[["emp_code","EMP Code"],["name","Name"],["designation","Designation"],["department","Department"],["category","Category"],["project_label","Current Project"],["current_location","Current Location"],["workforce_state","Workforce State"],["leave_balance","Leave Balance"]].map(([key,label])=><th key={key}><button onClick={()=>changeSort(key)}>{label}{sort.key===key?<span>{sort.direction==="asc"?"↑":"↓"}</span>:null}</button></th>)}</tr></thead><tbody>{sortedRows.map(item=><tr className={changes[item.emp_code]?"scenario-row":""} key={item.emp_code}><td><input type="checkbox" aria-label={`Select ${item.name||item.emp_code}`} checked={selected.has(item.emp_code)} onChange={()=>toggleSelected(item.emp_code)}/></td><td><b>{item.emp_code}</b></td><td>{item.name||"—"}</td><td>{item.designation||"—"}</td><td>{item.department||"—"}</td><td><button className="table-filter" onClick={()=>setChartFilter("category",clean(item.category))}>{item.category||"—"}</button></td><td><button className="table-filter" onClick={()=>setChartFilter("project",item.current_project_code)}>{item.project_label}</button></td><td><button className="table-filter" onClick={()=>setChartFilter("location",clean(item.current_location))}>{item.current_location||"—"}</button></td><td><span className={`workforce-pill ${item.workforce_state}`}>{STATE_LABELS[item.workforce_state]}</span></td><td className={Number(item.leave_balance)<0?"negative":""}>{item.leave_balance??"—"}</td></tr>)}</tbody></table>{!visible.length&&<p className="register-empty">No employees match the current filters.</p>}</div>
      </section>
    </div><Filters filters={filters} setFilters={setFilters} options={options} open={filterOpen} setOpen={setFilterOpen}/></div>
    {filterOpen&&<button className="filter-scrim" aria-label="Close filters" onClick={()=>setFilterOpen(false)}/>} 
  </div>;
}
