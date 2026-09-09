import test from 'node:test';
import assert from 'node:assert/strict';
import {visibleWorkflows,clearWorkflowMessages,settleAttachmentMessages,readWorkflowView} from '../src/chatWorkflowState.js';

test('completed and rejected responses never return through polling',()=>{
  const items=[{id:'a',status:'completed'},{id:'b',status:'rejected'},{id:'c',status:'pending'}];
  assert.deepEqual(visibleWorkflows(items,{fresh:false,ids:[]}),[items[2]]);
});

test('new chat ignores old drafts but shows work created in the new chat',()=>{
  const items=[{id:'old',status:'draft'},{id:'new',status:'draft'}];
  assert.deepEqual(visibleWorkflows(items,{fresh:true,ids:[]}),[]);
  assert.deepEqual(visibleWorkflows(items,{fresh:true,ids:['new']}),[items[1]]);
});

test('terminal project removes its conversation and shared upload summary only',()=>{
  const general={role:'user',content:'Portfolio question'};
  const other={role:'assistant',content:'Other draft',workflowIds:['b']};
  const messages=[general,{content:'Upload',workflowIds:['a','b']},{content:'Review project a',workflowIds:['a']},other];
  assert.deepEqual(clearWorkflowMessages(messages,['a']),[general,other]);
  assert.equal(clearWorkflowMessages(messages,['unknown']),messages);
});

test('clean chat visibility survives remount and malformed storage is tolerated',()=>{
  assert.deepEqual(readWorkflowView({getItem:()=>'{"fresh":true,"ids":["new"]}'},'key'),{fresh:true,ids:['new']});
  assert.deepEqual(readWorkflowView({getItem:()=>'{broken'},'key'),{fresh:false,ids:[]});
  assert.deepEqual(readWorkflowView({getItem:()=>{throw new Error('blocked')}},'key'),{fresh:false,ids:[]});
});

test('attachment completion keeps the user prompt and reports completion once',()=>{
  const prompt={role:'user',content:'Upload report.pdf',workflowIds:['pdf']};
  const messages=[prompt,{role:'assistant',content:'Indexing PDF',workflowIds:['pdf']}];
  const completed=[{id:'pdf',status:'completed'}];
  const result=settleAttachmentMessages(messages,completed);
  assert.equal(result[0],prompt);
  assert.equal(result[1].content,'Upload/ingestion complete.');
  assert.equal(result.length,2);
  assert.equal(settleAttachmentMessages(result,completed),result);
  assert.deepEqual(settleAttachmentMessages([],completed),[]);
  assert.equal(settleAttachmentMessages(messages,[{id:'pdf',status:'indexing'}]),messages);
  assert.deepEqual(settleAttachmentMessages(messages,[{id:'pdf',status:'rejected'}]),[prompt]);
});
