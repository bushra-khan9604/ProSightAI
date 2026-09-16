import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE?pathToFileURL(process.env.PLAYWRIGHT_MODULE).href:'playwright');
const preview='frontend/refinements-preview.html';
const html=`<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><div id="root"></div><script type="module">
import React from 'react';import{createRoot}from'react-dom/client';import App from '/src/App.jsx';import'/src/styles.css';import'/src/auth.css';import'/src/upload.css';import'/src/theme-refresh.css';
createRoot(document.getElementById('root')).render(React.createElement(App,{profile:{id:'ui-refinements',role:'admin',display_name:'A very long member name for sidebar truncation verification',email:'test@example.invalid'},onSignOut:()=>{}}));</script></html>`;
await fs.writeFile(preview,html);let browser;
try{
 browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[],consoleErrors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',message=>{if(message.type()==='error')consoleErrors.push(message.text())});
 let mode='normal',reads=0,posts=0,manpowerMode='normal';
 const result={answer:'Verified specialist result.',dataset_version:'version-1',project_code:'P',run_id:'run-1',agent_route:['analyst','writer'],citations:[],mode:'local'};
 const p={code:'P',name:'Project example',status:'active',actual_progress:45.6789,baseline_progress:50,revised_progress:48,variance_pct:-2.3211,manpower:[],milestones:[],equipment:[],contacts:[],sources:[],planned_start:'2026-01-01',planned_finish:'2027-01-01',revised_finish:'2027-01-01',reporting_date:'2026-09-12',contract_value_usd:1000,delay_days:0};
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/portfolio/manpower'&&manpowerMode==='empty')return route.fulfill({json:[]});
  if(path==='/api/portfolio/manpower'&&manpowerMode==='error')return route.fulfill({status:500,json:{detail:'Test load failure'}});
  if(path==='/api/query/stream'){
   posts++;const body='event: status\ndata: '+JSON.stringify({run_id:'run-1',label:'Analyst is analyzing…'})+'\n\n'+(mode==='normal'?'event: final\ndata: '+JSON.stringify(result)+'\n\n':'');
   return route.fulfill({contentType:'text/event-stream',body});
  }
  if(path.endsWith('/cancel'))return route.fulfill({json:mode==='race'?{status:'completed',answer:result}:{status:'cancelled'}});
  if(path==='/api/agent-runs/run-1'){
   reads++;
   if(mode==='offline'&&reads===1)return route.abort();
   const status=mode==='failed'?'failed':mode==='cancel'||mode==='race'?'running':mode==='recover'&&reads===1?'queued':'completed';
   return route.fulfill({json:{status,kind:'analyst',input:{query:'Analyze progress'},error:'Test failure',...(status==='completed'?{answer:result}:{})}});
  }
  return route.fulfill({json:path==='/api/projects'?[p]:path==='/api/portfolio/manpower'?[{emp_code:'EMP-1',name:'Test Engineer',designation:'Engineer',department:'Engineering',category:'Direct',current_project_code:'P',current_location:'Site',workforce_state:'allocated',leave_balance:12}]:path.includes('notifications')||path.includes('approvals')?{items:[]}:[]});
 });
 async function reset(next){mode=next;reads=0;posts=0;await page.goto('http://127.0.0.1:5179/refinements-preview.html');await page.evaluate(()=>sessionStorage.clear());await page.reload();}
 async function ask(){await page.getByPlaceholder('Ask about invoices, manpower, schedules, risks or uploaded evidence…').fill('Analyze progress');await page.getByRole('button',{name:'Send question',exact:true}).click();}
 for(const scenario of ['normal','recover','offline','failed','cancel','race']){
  await reset(scenario);await ask();
  if(scenario==='offline')await page.getByRole('button',{name:'Check status',exact:true}).click();
  if(scenario==='race')await page.getByRole('button',{name:'Cancel',exact:true}).click();
  if(scenario==='cancel'){await page.getByRole('button',{name:'Cancel',exact:true}).click();await page.getByText('Task cancelled.',{exact:true}).waitFor();}
  else if(scenario==='failed')await page.getByText('Task failed. Test failure',{exact:true}).waitFor();
  else {await page.getByText(result.answer,{exact:true}).waitFor();assert.equal(await page.getByText(result.answer,{exact:true}).count(),1);}
  assert.equal(await page.getByRole('button',{name:'Cancel',exact:true}).count(),0);
  assert.equal(await page.getByRole('button',{name:'Check status',exact:true}).count(),0);
  assert.equal(posts,1);assert.equal(await page.evaluate(()=>Object.keys(sessionStorage).filter(k=>k.startsWith('prosight-runs:')).every(k=>JSON.parse(sessionStorage[k]).length===0)),true);
  console.log('PASS run',scenario);
 }
 await reset('cancel');await ask();await page.getByRole('button',{name:'Cancel',exact:true}).waitFor();mode='normal';await page.reload();await page.getByText(result.answer,{exact:true}).waitFor();assert.equal(posts,1);console.log('PASS refresh resumes without new query');consoleErrors.length=0;
 await page.getByRole('button',{name:'Command Center',exact:true}).click();await page.getByText('Sample S-curve — not live project history.',{exact:true}).waitFor();
 const rangeTrigger=page.getByRole('button',{name:/Last \d months/});
 assert.equal(await page.locator('.chart-panel .recharts-line-dots circle').count(),6);
 await rangeTrigger.click();let selectedRange=page.getByRole('menuitemradio',{name:'6 months',exact:true});
 assert.equal(await selectedRange.evaluate(el=>getComputedStyle(el).color),'rgb(255, 255, 255)');
 assert.equal(await selectedRange.locator('span').evaluate(el=>getComputedStyle(el).color),'rgb(255, 255, 255)');
 await page.getByRole('menuitemradio',{name:'3 months',exact:true}).click();assert.equal(await page.locator('.chart-panel .recharts-line-dots circle').count(),3);
 await rangeTrigger.click();await page.getByRole('menuitemradio',{name:'9 months',exact:true}).click();assert.equal(await page.locator('.chart-panel .recharts-line-dots circle').count(),9);await page.waitForTimeout(900);
 await fs.mkdir('outputs/ui-refinements',{recursive:true});await page.screenshot({path:'outputs/ui-refinements/command-center-light.png'});
 await page.evaluate(()=>document.documentElement.dataset.theme='dark');await rangeTrigger.click();selectedRange=page.getByRole('menuitemradio',{name:'9 months',exact:true});
 assert.equal(await selectedRange.evaluate(el=>getComputedStyle(el).color),'rgb(255, 255, 255)');await page.keyboard.press('Escape');
 await page.screenshot({path:'outputs/ui-refinements/command-center-dark.png'});await page.evaluate(()=>document.documentElement.dataset.theme='light');
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'outputs/ui-refinements/command-center-narrow.png'});await page.setViewportSize({width:1440,height:1000});
 console.log('PASS illustrative S-curve, 3/6/9 ranges and selected contrast');
 await page.getByRole('button',{name:'Project Explorer',exact:true}).click();await page.getByText('45.68%',{exact:true}).waitFor();await page.getByText('-2.32 pp',{exact:true}).waitFor();
 const formats=await page.evaluate(async()=>{const {formatProgress}=await import('/src/formatProgress.js');return [formatProgress(45),formatProgress(null),formatProgress(0),formatProgress(-.001,' pp',true)]});assert.deepEqual(formats,['45.00%','—','0.00%','0.00 pp']);
 await page.getByRole('button',{name:'Portfolio Import',exact:true}).click();await page.getByRole('combobox',{name:'Data to import'}).click();await page.getByRole('option',{name:/Mixed Project Files/}).click();
 const selector=page.getByRole('combobox',{name:'Target project'});await selector.focus();await page.keyboard.press('Home');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');assert.match(await selector.innerText(),/Project example/);
 await page.screenshot({path:'outputs/ui-refinements/light.png'});
 await page.evaluate(()=>document.documentElement.dataset.theme='dark');await page.waitForTimeout(400);
 assert.equal(await selector.evaluate(el=>getComputedStyle(el).color),'rgb(255, 255, 255)');await page.screenshot({path:'outputs/ui-refinements/dark.png'});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'outputs/ui-refinements/narrow.png'});
 await page.setViewportSize({width:1440,height:1000});await page.keyboard.press('Escape');
 await page.getByRole('button',{name:'Command Center',exact:true}).click();await page.getByRole('button',{name:/Manpower Allocation Dashboard/}).click();await page.getByText('Test Engineer',{exact:true}).waitFor();
 await page.screenshot({path:'outputs/ui-refinements/manpower-dark.png'});
 assert.equal(await page.getByRole('combobox').count(),6);
 const locationFilter=page.getByRole('combobox',{name:'Current location'});await locationFilter.focus();await page.keyboard.press('End');await page.keyboard.press('Enter');
 assert.match(await locationFilter.innerText(),/Site/);await locationFilter.focus();await page.keyboard.press('Home');await page.keyboard.press('Enter');assert.match(await locationFilter.innerText(),/All locations/);
 await page.getByRole('checkbox',{name:'Select Test Engineer'}).check();await page.getByRole('button',{name:'Build scenario (1)',exact:true}).click();
 const scenarioState=page.getByRole('combobox',{name:'Proposed state'}),scenarioTarget=page.getByRole('combobox',{name:'Target project'});
 await scenarioTarget.focus();await page.keyboard.press('Home');await page.keyboard.press('Enter');assert.match(await scenarioTarget.innerText(),/Project example/);
 await scenarioState.focus();await page.keyboard.press('End');await page.keyboard.press('Enter');assert.match(await scenarioState.innerText(),/Not allocated/);
 await page.getByRole('button',{name:'Apply to scenario',exact:true}).click();await page.getByText('Not allocated',{exact:true}).last().waitFor();
 const barThicknesses=await page.locator('.manpower-chart .recharts-bar-rectangle path').evaluateAll(elements=>elements.map(element=>{const box=element.getBBox();return Math.min(box.width,box.height)}));
 assert.ok(barThicknesses.length>0);assert.ok(barThicknesses.every(value=>value<=18.5),`Oversized bars: ${barThicknesses.join(', ')}`);
 console.log('PASS themed manpower filters, scenario selectors and 18px bar cap');
 const identity=page.locator('.role-identity');assert.match(await identity.getAttribute('title'),/A very long member name/);assert.ok(await identity.evaluate(el=>el.getBoundingClientRect().height)<=48);console.log('PASS compact sidebar and full-name tooltip');
 await page.evaluate(()=>document.documentElement.dataset.theme='light');await page.screenshot({path:'outputs/ui-refinements/manpower-light.png'});
 const manpowerNav=page.getByRole('button',{name:'Manpower Dashboard',exact:true});
 assert.match(await manpowerNav.getAttribute('class'),/active/);
 await page.locator('.back-link').click();await page.getByRole('heading',{name:'Project Command Center',exact:true}).waitFor();
 await manpowerNav.focus();await page.keyboard.press('Enter');await page.getByText('Test Engineer',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Collapse sidebar',exact:true}).click();assert.equal(await manpowerNav.getAttribute('title'),'Manpower Dashboard');
 await page.getByRole('button',{name:'AI Assistant',exact:true}).click();await manpowerNav.click();await page.getByText('Test Engineer',{exact:true}).waitFor();
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'outputs/ui-refinements/manpower-sidebar-narrow.png'});
 await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'Expand sidebar',exact:true}).click();
 assert.equal(consoleErrors.length,0,consoleErrors.join('\n'));console.log('PASS updated UI flow has no console errors');
 manpowerMode='empty';await page.getByRole('button',{name:'AI Assistant',exact:true}).click();await manpowerNav.click();await page.getByRole('heading',{name:'No manpower register is available'}).waitFor();
 await page.getByRole('button',{name:'Open Project Explorer',exact:true}).click();await page.getByRole('heading',{name:'Project Explorer',exact:true}).waitFor();
 manpowerMode='error';await manpowerNav.click();await page.getByRole('heading',{name:'Manpower data could not be loaded'}).waitFor();
 manpowerMode='normal';await page.getByRole('button',{name:'Try again',exact:true}).click();await page.getByText('Test Engineer',{exact:true}).waitFor();
 console.log('PASS direct manpower navigation, shortcut, Back, keyboard, collapsed/narrow, empty/import and error recovery');
 assert.equal(errors.length,0,errors.join('\n'));console.log('PASS percentages, dropdown keyboard control, themes and narrow layout');
}finally{await browser?.close();await fs.unlink(preview).catch(()=>{});}
