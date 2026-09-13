import {pathToFileURL} from 'node:url';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE ? pathToFileURL(process.env.PLAYWRIGHT_MODULE).href : 'playwright');
import fs from 'node:fs/promises';
const previewPath='frontend/controls-preview.html';
await fs.writeFile(previewPath,"<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"></head><body><div id=\"root\"></div><script type=\"module\">\nimport React from 'react';import {createRoot} from 'react-dom/client';import App from '/src/App.jsx';\nimport '/src/styles.css';import '/src/upload.css';import '/src/theme-refresh.css';\ncreateRoot(document.getElementById('root')).render(React.createElement(App,{profile:{id:'test-ui',role:'admin',display_name:'Test Admin',email:'test@example.invalid'},onSignOut:()=>{}}));\n</script></body></html>\n");
let browser;
try {
browser=await chromium.launch({headless:true,channel:"msedge"});const page=await browser.newPage({viewport:{width:1440,height:1000}});
const project={code:'PRJ-2024-001',name:'Marina Heights Residential Tower',status:'active',client:'Test client',location:'Dubai',contract_value_usd:84500000,planned_start:'2024-02-01',planned_finish:'2026-11-30',revised_finish:'2027-02-27',reporting_date:'2026-09-12',actual_progress:94.5,baseline_progress:95.3,revised_progress:94.5,variance_pct:-.8,delay_days:89,sources:[],contacts:[],activities:[],milestones:[],manpower:[],equipment:[]};
await page.route('**/api/**',async route=>{const u=new URL(route.request().url());let data=[];if(u.pathname==='/api/projects')data=process.env.TEST_EMPTY_PROJECTS==='1'?[]:[project];if(u.pathname.includes('notifications')||u.pathname.includes('approvals'))data={items:[]};await route.fulfill({json:data})});
const errors=[];page.on('pageerror',e=>errors.push(e.stack));
await page.goto('http://127.0.0.1:5179/controls-preview.html');await page.getByRole('button',{name:'Project Explorer',exact:true}).click();
if(process.env.TEST_EMPTY_PROJECTS==='1'){
await page.getByRole('heading',{name:'No projects available'}).waitFor();
await page.getByRole('button',{name:'Create Project',exact:true}).click();
await page.getByRole('heading',{name:'New project details'}).waitFor();
await page.locator('input[type=file]').waitFor({state:'attached'});
console.log('PASS empty Project Explorer displays Create Project and workbook upload');
} else {
await page.getByRole('button',{name:/Portfolio Import/}).click();
await page.getByRole('combobox',{name:'Data to import'}).click();await page.getByRole('option',{name:/Mixed Project Files/}).click();
await fs.mkdir('outputs/controls-ui-qa',{recursive:true});
await page.screenshot({path:'outputs/controls-ui-qa/import-light.png',fullPage:true});
await page.evaluate(()=>document.documentElement.dataset.theme='dark');await page.waitForTimeout(600);await page.screenshot({path:'outputs/controls-ui-qa/import-dark.png',fullPage:true});
await page.setViewportSize({width:390,height:844});await page.screenshot({path:'outputs/controls-ui-qa/import-narrow.png',fullPage:true});
}
if(errors.length)throw Error(errors.join('\n'));
console.log('PASS import options and screenshots');
} finally {await browser?.close();await fs.unlink(previewPath).catch(()=>{});}




